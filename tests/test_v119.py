"""v1.0.19: feed refresh TTL, live HTTP-layer scan accounting, fixed footer and toolbar."""
from __future__ import annotations
import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from iran_proxy_monitor import gui, monitor, engine, __version__
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.models import Probe,Speed

URI='trojan://secure123@node.example:443#Validated'
URL='https://panel.example/feed?token=private'

class RefreshReceiptTests(unittest.TestCase):
    def test_regular_cycle_reuses_verified_feed_within_60_minutes(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(monitor,'SNAPSHOT',Path(td)/'last.dat'), \
                 patch.object(monitor,'fetch_subscription',return_value=URI.encode()) as fetch:
                settings=Settings(subscription_url=URL)
                first,state=monitor.load_report(settings,reuse_fresh_seconds=3600)
                second,second_state=monitor.load_report(settings,reuse_fresh_seconds=3600)
                self.assertEqual((first.usable,state,second.usable,second_state),(1,'fresh',1,'recent-cache'))
                self.assertEqual(fetch.call_count,1)
                self.assertEqual(second.source_statuses[0]['fetched_bytes'],0)
                meta=monitor.source_snapshot_metadata_path(URL)
                self.assertTrue(meta.is_file())
                receipt=json.loads(meta.read_text())
                self.assertNotIn(URL,meta.read_text())  # credential-safe source identity
                self.assertEqual(receipt['source_key'],monitor.subscription_fingerprint(URL))
                self.assertLess(time.time()-receipt['completed_at'],10)
    def test_explicit_update_always_fetches_and_refreshes_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(monitor,'SNAPSHOT',Path(td)/'latest.dat'), \
                 patch.object(monitor,'fetch_subscription',return_value=URI.encode()) as fetch:
                s=Settings(subscription_url=URL)
                monitor.load_report(s,reuse_fresh_seconds=3600)
                _,state=monitor.load_report(s,allow_cache=False,reuse_fresh_seconds=0)
                self.assertEqual(fetch.call_count,2)
                self.assertEqual(state,'fresh')
    def test_expired_receipt_forces_a_new_download(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(monitor,'SNAPSHOT',Path(td)/'latest.dat'), \
                 patch.object(monitor,'fetch_subscription',return_value=URI.encode()) as fetch:
                s=Settings(subscription_url=URL)
                monitor.load_report(s,reuse_fresh_seconds=3600)
                meta=monitor.source_snapshot_metadata_path(URL)
                data=json.loads(meta.read_text());data['completed_at']=time.time()-3601
                meta.write_text(json.dumps(data))
                _,state=monitor.load_report(s,reuse_fresh_seconds=3600)
                self.assertEqual(state,'fresh')
                self.assertEqual(fetch.call_count,2)
    def test_changed_url_can_never_inherit_another_source_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(monitor,'SNAPSHOT',Path(td)/'latest.dat'), \
                 patch.object(monitor,'fetch_subscription',return_value=URI.encode()) as fetch:
                monitor.load_report(Settings(subscription_url=URL),reuse_fresh_seconds=3600)
                _,state=monitor.load_report(Settings(subscription_url=URL+'2'),reuse_fresh_seconds=3600)
                self.assertEqual(state,'fresh')
                self.assertEqual(fetch.call_count,2)
    def test_cache_only_remains_explicit_even_when_receipt_aged(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(monitor,'SNAPSHOT',Path(td)/'latest.dat'), \
                 patch.object(monitor,'fetch_subscription',return_value=URI.encode()) as fetch:
                s=Settings(subscription_url=URL)
                monitor.load_report(s,reuse_fresh_seconds=3600)
                meta=monitor.source_snapshot_metadata_path(URL)
                data=json.loads(meta.read_text());data['completed_at']=time.time()-7200
                meta.write_text(json.dumps(data))
                _,state=monitor.load_report(s,cache_only=True,reuse_fresh_seconds=3600)
                self.assertEqual(state,'saved-no-download')
                self.assertEqual(fetch.call_count,1)

class LiveTrafficAndLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.app=gui.App(self.root)
    def tearDown(self):
        try:self.app.close();self.root.update()
        except Exception:
            try:self.root.destroy()
            except tk.TclError:pass
    def test_live_measurements_and_no_repeat_counting(self):
        app=self.app
        app.progress_event({'event':'scan-usage-feed','bytes':2048})
        probe=Probe('probe',False,http_sent_bytes=320,http_received_bytes=640)
        app.progress_event({'event':'probe-result','node_id':'probe','probe':probe})
        app.progress_event({'event':'probe-result','node_id':'probe','probe':probe})
        speed=Speed('speed',bytes_received=4096)
        app.progress_event({'event':'speed-result','node_id':'speed','speed':speed,'speed_phase':'preliminary'})
        app.progress_event({'event':'speed-result','node_id':'speed','speed':speed,'speed_phase':'preliminary'})
        app.progress_event({'event':'speed-result','node_id':'speed','speed':speed,'speed_phase':'confirmation'})
        app.progress_event({'event':'scan-usage-baseline','bytes':1000})
        self.assertEqual(app.scan_live,{'feed':2048,'latency':960,'speed':8192,'baseline':1000})
        self.assertIn('Latency 0.001',app.scan_usage_text.get())
        self.assertEqual(app.stat_vars[6].get(),f'{12200/1048576:.3f}')
    def test_fixed_footer_visible_at_minimum_window_height(self):
        self.root.deiconify();self.root.geometry('1060x700')
        self.root.update_idletasks();self.root.update()
        bar=self.app.footer_bar
        self.assertGreaterEqual(bar.winfo_height(),30)
        self.assertGreaterEqual(bar.winfo_y(),0)
        self.assertLessEqual(bar.winfo_y()+bar.winfo_height(),self.root.winfo_height()+2)
        self.assertTrue(any(f'v{__version__}' in x.cget('text') for x in bar.winfo_children()[1].winfo_children()))
        canvas=self.app.dashboard_canvas
        self.assertGreater(float(canvas.cget('height')),0)
        self.assertGreater(canvas.bbox('all')[3],canvas.winfo_height())
        canvas.yview_moveto(1);self.root.update()
        self.assertTrue(self.app.results_tabs.winfo_ismapped())
    def test_button_order_and_single_blue_action(self):
        controls=[]
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c,gui.ttk.Button):controls.append((c.cget('text'),c.cget('style')))
                walk(c)
        walk(self.root)
        ordered=[x for x in controls if x[0] in (
            'Update subscription','Run one cycle','Start auto monitoring','Run once + auto',
            'Stop','View logs','Copy selected','Save selected','Compare selected')]
        self.assertEqual([x[0] for x in ordered],[
            'Update subscription','Run one cycle','Start auto monitoring','Run once + auto',
            'Stop','View logs','Copy selected','Save selected','Compare selected'])
        self.assertEqual(dict(ordered)['Start auto monitoring'],'TButton')
        self.assertEqual(dict(ordered)['Run once + auto'],'Accent.TButton')
    def test_source_icon_assets_exist_for_titlebar_and_installer(self):
        assets=Path(gui.__file__).resolve().parent.parent/'assets'
        self.assertTrue((assets/'iran-remains-connected.ico').is_file())
        self.assertIsNotNone(self.app.app_icon)

class ProbeAccountingTests(unittest.TestCase):
    def test_latency_probe_records_http_connect_and_https_headers(self):
        # Test the bytes actually seen by strict_https_probe with a real local
        # proxy listener, avoiding network dependencies by deliberately rejecting
        # CONNECT before TLS (the CONNECT request/reply is still measurable).
        import socket,threading
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        def serve():
            c,_=listener.accept()
            try:
                c.recv(8192)
                c.sendall(b'HTTP/1.1 502 Rejected\r\nContent-Length: 0\r\n\r\n')
            finally:c.close();listener.close()
        th=threading.Thread(target=serve,daemon=True);th.start()
        m={}
        with self.assertRaises(ConnectionError):
            engine.strict_https_probe('https://example.org/anything',port,2,measurements=m)
        th.join(2)
        self.assertGreater(m.get('http_sent_bytes',0),30)
        self.assertGreater(m.get('http_received_bytes',0),30)

if __name__=='__main__':unittest.main()
