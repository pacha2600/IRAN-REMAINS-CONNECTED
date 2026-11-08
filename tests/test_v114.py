"""v1.0.14: flow-consistency statistics and single-source feed mode UI."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from iran_proxy_monitor import engine, monitor, gui
from iran_proxy_monitor.models import Probe, Speed, Result
from iran_proxy_monitor.parser import link_node
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.history import History


def candidate():
    return link_node('trojan://password@proxy.example:443#Stable')


class ConsistentFlowTests(unittest.TestCase):
    def test_continuous_traffic_has_strong_lower_quartile_rate(self):
        bins={i:65_536 for i in range(12)}
        p=engine.flow_profile(bins,12.0,786_432)
        self.assertGreater(p['floor_mbps'],0.5)
        self.assertEqual(p['active_ratio'],1.0)
        self.assertAlmostEqual(p['floor_fraction'],1.0)
        self.assertEqual(p['longest_quiet_seconds'],0)

    def test_spikes_with_long_silence_have_zero_flow_floor(self):
        # Same total bytes, very misleading mean Mbps compared with real flow.
        bins={0:262_144,4:262_144,8:262_144}
        p=engine.flow_profile(bins,12.0,786_432)
        self.assertEqual(p['floor_mbps'],0)
        self.assertLess(p['active_ratio'],0.30)
        self.assertGreaterEqual(p['longest_quiet_seconds'],3)

    def test_every_other_second_burst_is_not_consistent(self):
        bins={i:131_072 for i in range(0,12,2)}
        p=engine.flow_profile(bins,12.0,786_432)
        # A 2-second window average can look perfectly normal; the independent
        # one-second occupancy check still detects alternating silence.
        self.assertLess(p['active_ratio'],0.75)

    def test_a_few_tiny_drips_cannot_disguise_one_fast_burst(self):
        bins={i:500 for i in range(12)}
        bins[6]=500+786_432
        p=engine.flow_profile(bins,12.0,sum(bins.values()))
        self.assertLess(p['active_ratio'],0.20)
        self.assertLess(p['floor_fraction'],0.05)

    def test_actual_confirmation_requires_flow_floor_and_occupancy(self):
        n=candidate()
        def fake_get(url,port,amount,duration,cancel,measurements=None):
            bins={i:65_536 for i in range(12)}
            measurements.update(activity_buckets=bins,active_span_seconds=11.5,
                                longest_gap_ms=600,stalled=False)
            return sum(bins.values()),12.0,200
        with patch.object(engine,'http_get',side_effect=fake_get):
            result=engine.speed_confirm_one(n,11000,['https://example.invalid/down'],16*1024*1024,12,None,8)
        self.assertTrue(result.verified)
        self.assertGreater(result.flow_mbps,0.5)
        self.assertEqual(result.flow_active_ratio,1)

    def test_no_flow_confirmation_even_when_average_is_attractive(self):
        n=candidate()
        def fake_get(url,port,amount,duration,cancel,measurements=None):
            bins={i:500 for i in range(12)}
            bins[6]=786_432
            measurements.update(activity_buckets=bins,active_span_seconds=10.5,
                                longest_gap_ms=1000,stalled=False)
            return sum(bins.values()),12.0,200
        with patch.object(engine,'http_get',side_effect=fake_get):
            result=engine.speed_confirm_one(n,11000,['https://example.invalid/down'],16*1024*1024,12,None,8)
        self.assertFalse(result.verified)
        self.assertGreater(result.mbps,0.5)
        self.assertLess(result.flow_mbps,0.01)

    def test_ranking_uses_flow_floor_not_mean_burst(self):
        a,b=candidate(),link_node('trojan://password@second.example:443#Other')
        results=[
            Result(a,Probe(a.id,True,80),confirm=Speed(a.id,30,5_000_000,12,True,verified=True,
                                                       flow_mbps=0.15,flow_active_ratio=.8)),
            Result(b,Probe(b.id,True,250),confirm=Speed(b.id,1.7,2_000_000,12,True,verified=True,
                                                        flow_mbps=1.2,flow_active_ratio=1.0)),
        ]
        with tempfile.TemporaryDirectory() as td:
            h=History(Path(td)/'history.db')
            try:
                fast,ping,overall=monitor.ranking(results,h)
            finally:h.close()
        self.assertEqual(fast[0].node.id,b.id)
        self.assertAlmostEqual(results[0].best_validated_mbps,0.15)

    def test_legacy_confirmation_defaults_upgrade_without_touching_custom(self):
        from iran_proxy_monitor import settings as settings_module
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);file=base/'settings.json'
            file.write_text(json.dumps({'confirm_seconds':9.0,'confirm_min_seconds':4.0}))
            with patch.object(settings_module,'DATA_DIR',base):
                s=Settings.load()
            self.assertEqual((s.confirm_seconds,s.confirm_min_seconds),(12.0,8.0))
            file.write_text(json.dumps({'confirm_seconds':15.0,'confirm_min_seconds':6.0}))
            with patch.object(settings_module,'DATA_DIR',base):
                s=Settings.load()
            self.assertEqual((s.confirm_seconds,s.confirm_min_seconds),(15.0,6.0))


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','Tk UI test needs display')
class ProxyDialogTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.load_patch=patch.object(gui.Settings,'load',return_value=Settings())
        self.save_patch=patch.object(gui.Settings,'save',return_value=None)
        self.load_patch.start();self.save_patch.start()
        self.app=gui.App(self.root)
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.save_patch.stop();self.load_patch.stop()

    @staticmethod
    def children(widget):
        for child in widget.winfo_children():
            yield child
            yield from ProxyDialogTests.children(child)

    def interact(self,save):
        def action():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel))
            all_widgets=list(self.children(dialog))
            modes=[w for w in all_widgets if isinstance(w,ttk.Combobox)]
            self.assertEqual(len(modes),1)
            modes[0].set('manual-socks5')
            if save:
                btn=next(w for w in all_widgets if isinstance(w,ttk.Button) and w.cget('text')=='Save proxy settings')
                btn.invoke()
            else:
                btn=next(w for w in all_widgets if isinstance(w,ttk.Button) and w.cget('text')=='Cancel')
                btn.invoke()
        self.root.after(35,action)
        self.app.configure_feed_proxy()

    def test_only_modal_has_proxy_mode_selector_and_save_commits(self):
        # Connection mode and shortlist choice belong to the new client panel;
        # only FEED proxy mode must stay inside the modal.
        outside=[w for w in self.children(self.root) if isinstance(w,ttk.Combobox)]
        self.assertEqual(len(outside),2)
        self.assertTrue(all('manual-socks5' not in w.cget('values') for w in outside))
        self.interact(save=True)
        self.assertEqual(self.app.source_mode.get(),'manual-socks5')
        self.assertEqual(self.app.settings.subscription_proxy_mode,'manual-socks5')
        self.assertIn('manual-socks5',self.app.feed_mode_label.get())

    def test_cancel_discards_mode_change(self):
        self.interact(save=False)
        self.assertEqual(self.app.source_mode.get(),'system')
        self.assertEqual(self.app.settings.subscription_proxy_mode,'system')

if __name__=='__main__':unittest.main()
