"""v1.0.18: static config security, recent table parity, and connected-mode handoff."""
import json
import tempfile
import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from iran_proxy_monitor import gui, monitor, parser
from iran_proxy_monitor.security import assess_outbound
from iran_proxy_monitor.connection_history import remember_connection, recent_connections
from iran_proxy_monitor.models import Node, Probe, Speed, Result

TLS={'enabled':True,'server_name':'example.org'}
VLESS={'type':'vless','uuid':'11111111-1111-1111-1111-111111111111',
       'server':'example.org','server_port':443,'tls':TLS}

class SecurityTests(unittest.TestCase):
    def test_vless_without_tls_is_clear_proxy_hop(self):
        clear={k:v for k,v in VLESS.items() if k!='tls'}
        self.assertFalse(assess_outbound(clear).encrypted)
        self.assertLess(assess_outbound(clear).score,assess_outbound(VLESS).score)
    def test_insecure_tls_penalty_and_explanation(self):
        secure=assess_outbound(VLESS)
        unsafe=assess_outbound({**VLESS,'tls':{**TLS,'insecure':True}})
        self.assertLess(unsafe.score,secure.score)
        self.assertIn('unverified cert',unsafe.encryption)
        self.assertIn('DISABLED',unsafe.explanation)
    def test_shadowsocks_aead_2022_legacy_none(self):
        base={'type':'shadowsocks','server':'e','server_port':443}
        modern=assess_outbound({**base,'method':'2022-blake3-aes-256-gcm'})
        aead=assess_outbound({**base,'method':'aes-256-gcm'})
        weak=assess_outbound({**base,'method':'aes-128-cfb'})
        unencrypted=assess_outbound({**base,'method':'none'})
        self.assertGreater(modern.score,aead.score)
        self.assertGreater(aead.score,weak.score)
        self.assertGreater(weak.score,unencrypted.score)
        self.assertTrue(aead.encrypted)
        self.assertFalse(unencrypted.encrypted)
    def test_unknown_not_mislabeled_unsafe_or_safe(self):
        unknown=assess_outbound({'type':'future-proxy','server':'x'})
        self.assertIsNone(unknown.score)
        self.assertIsNone(unknown.encrypted)
    def test_vm_and_plain_upstream(self):
        self.assertLess(assess_outbound({'type':'vmess','security':'none'}).score,
                        assess_outbound({'type':'vmess','security':'aes-128-gcm'}).score)
        self.assertFalse(assess_outbound({'type':'socks'}).encrypted)
        self.assertTrue(assess_outbound({'type':'http','tls':TLS}).encrypted)
    def test_overall_rank_penalizes_clear_hop_not_ping_speed(self):
        class FakeHistory:
            def recent(self,nodes):return {}
            def reliability(self,entry):return .5
        clear={k:v for k,v in VLESS.items() if k!='tls'}
        a=Node('Encrypted','vless',VLESS,'test')
        b=Node('Plain','vless',clear,'test')
        def result(n):
            return Result(n,Probe(n.id,True,110.0),
                          Speed(n.id,mbps=4.0,ok=True),
                          Speed(n.id,mbps=4.0,flow_mbps=4.0,verified=True,ok=True))
        r1,r2=result(a),result(b)
        fastest,ping,overall=monitor.ranking([r2,r1],FakeHistory())
        self.assertEqual(overall[0].node.id,a.id)
        self.assertGreater(r1.rank_score,r2.rank_score)
        self.assertEqual({r.node.id for r in ping},{a.id,b.id})
        self.assertEqual({r.node.id for r in fastest},{a.id,b.id})

class RecentMetricsTests(unittest.TestCase):
    def test_old_history_still_loads_and_new_metrics_do_not_include_creds(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'recent.json'
            out={**VLESS,'tag':'x'}
            remember_connection('Node',out,'manual',path,
                metrics={'latency':203.2,'mbps':2.33,'reliability':.66,
                         'password':'FORBIDDEN_EXTRA','status':'Consistent flow'})
            rows=recent_connections(path)
            self.assertEqual(rows[0]['metrics']['mbps'],2.33)
            self.assertNotIn('FORBIDDEN_EXTRA',path.read_text())
            self.assertEqual(len(rows),1)
            # v1.0.17 stored no metrics; still parse and show missing data as '—'.
            rows[0].pop('metrics')
            path.write_text(json.dumps(rows))
            self.assertNotIn('metrics',recent_connections(path)[0])

class FakeConnection:
    def __init__(self):
        self.active=True;self.connecting=False;self.mode='manual';self.port=20808
        self._stop_requested=threading.Event();self.starts=[];self.stops=0
        self.fail_mode=None
    def stop(self):
        self.active=False;self.mode=None;self.stops+=1
        self._stop_requested.set()
        return 'Disconnected'
    def start(self,binary,outbound,name,mode,port,progress=None):
        self.starts.append(mode)
        if mode==self.fail_mode:raise RuntimeError('simulated failure')
        self.active=True;self.mode=mode;self.port=port
        self._stop_requested.clear()
        return f'CONNECTED: {name} · {mode}'
    def reconcile(self):return False
    def traffic(self):return dict(available=False,down=0,up=0,up_bps=0,down_bps=0)
    def status(self):return f'CONNECTED: {self.mode}' if self.active else 'Disconnected'

class GuiModeAndColumnsTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.p1=patch.object(gui,'recent_connections',return_value=[])
        self.p2=patch.object(gui,'remember_connection',return_value=[])
        self.p1.start();self.p2.start()
        self.app=gui.App(self.root)
    def tearDown(self):
        try:self.app.close();self.root.update()
        except (tk.TclError,Exception):
            try:self.root.destroy()
            except tk.TclError:pass
        self.p2.stop();self.p1.stop()
    def test_all_pool_columns_present_in_recent(self):
        self.assertEqual(tuple(self.app.recent_tree['columns']),gui.RECENT_COLUMNS)
        self.assertEqual(set(gui.COLUMNS),set(gui.RECENT_COLUMNS)-{'connected_at','mode'})
        a=parser.link_node('trojan://pass@example.org:443#Example')
        self.app.load_rows([a]);self.root.update()
        self.assertEqual(len(self.app.row_values(a.id)),len(gui.COLUMNS))
        self.assertGreater(int(self.app.tree.set(a.id,'security')),70)
        self.assertTrue(self.app.tree.set(a.id,'encryption'))
    def test_reconnect_same_node_when_mode_selected(self):
        manager=FakeConnection();self.app.connection=manager
        self.app._active_connection=(VLESS,'Same node',{'latency':150.0})
        with patch.object(self.app,'save',return_value=True),\
             patch.object(gui,'check_core',return_value=True),\
             patch.object(gui,'find_singbox',return_value='fake-sb'):
            self.app.client_mode.set('Windows system proxy')
            self.app._mode_changed()
            self.app.client_thread.join(timeout=3)
            self.assertFalse(self.app.client_thread.is_alive())
            if self.app._poll_after_id is not None:
                self.app.root.after_cancel(self.app._poll_after_id)
            self.app.poll()
        self.assertEqual(manager.starts,['system'])
        self.assertEqual(manager.stops,1)
        self.assertEqual(manager.mode,'system')
        self.assertEqual(self.app._active_connection[1],'Same node')
    def test_switch_invalid_core_preserves_old_connection(self):
        manager=FakeConnection();self.app.connection=manager
        self.app._active_connection=(VLESS,'Same node',{})
        with patch.object(self.app,'save',return_value=True),\
             patch.object(gui,'check_core',return_value=False),\
             patch.object(gui,'find_singbox',return_value='fake-sb'):
            self.app.client_mode.set('Windows system proxy')
            self.app._mode_changed()
            self.app.client_thread.join(timeout=3)
            if self.app._poll_after_id is not None:
                self.app.root.after_cancel(self.app._poll_after_id)
            self.app.poll()
        self.assertTrue(manager.active)
        self.assertEqual(manager.stops,0)
        self.assertEqual(manager.mode,'manual')
        self.assertEqual(self.app.client_mode.get(),'Manual HTTP/SOCKS5')
    def test_switch_start_failure_rolls_back_previous_mode(self):
        manager=FakeConnection();manager.fail_mode='system'
        self.app.connection=manager
        self.app._active_connection=(VLESS,'Same node',{})
        with patch.object(self.app,'save',return_value=True),\
             patch.object(gui,'check_core',return_value=True),\
             patch.object(gui,'find_singbox',return_value='fake-sb'):
            self.app.client_mode.set('Windows system proxy')
            self.app._mode_changed()
            self.app.client_thread.join(timeout=3)
            if self.app._poll_after_id is not None:
                self.app.root.after_cancel(self.app._poll_after_id)
            self.app.poll()
        self.assertEqual(manager.starts,['system','manual'])
        self.assertTrue(manager.active)
        self.assertEqual(manager.mode,'manual')
        self.assertEqual(self.app.client_mode.get(),'Manual HTTP/SOCKS5')
    def test_tun_without_admin_retains_active_connection(self):
        manager=FakeConnection();self.app.connection=manager
        self.app._active_connection=(VLESS,'Same node',{})
        with patch.object(gui,'is_administrator',return_value=False):
            self.app.client_mode.set('Device-wide TUN')
            self.app._mode_changed()
        self.assertTrue(manager.active)
        self.assertEqual(manager.stops,0)
        self.assertEqual(self.app.client_mode.get(),'Manual HTTP/SOCKS5')

if __name__=='__main__': unittest.main()
