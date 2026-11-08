"""v1.0.16: combined pool, reliability floor, private traffic metrics, GUI tabs."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from iran_proxy_monitor import client, gui, monitor
from iran_proxy_monitor.models import Probe, Result, Speed
from iran_proxy_monitor.parser import link_node
from iran_proxy_monitor.settings import Settings, split_subscription_sources

A = 'trojan://password@a.example:443#A'
A_RENAMED = 'trojan://password@a.example:443#SameServerOtherLabel'
B = 'trojan://password@b.example:443#B'
C = 'trojan://password@c.example:443#C'


class SourcePoolTests(unittest.TestCase):
    def test_comma_newline_and_duplicate_sources(self):
        x = split_subscription_sources('https://x.example/a, https://y.example/b\nhttps://x.example/a\n')
        self.assertEqual(x, ['https://x.example/a', 'https://y.example/b'])
        self.assertEqual(monitor.pool_fingerprint(x), monitor.pool_fingerprint(list(reversed(x))))
        self.assertEqual(monitor.pool_fingerprint(x[:1]),monitor.subscription_fingerprint(x[0]))
        with self.assertRaisesRegex(ValueError, '40'):
            split_subscription_sources('\n'.join(f'https://e{i}.example/file' for i in range(41)))

    def test_settings_accept_multiple_absolute_files_and_urls(self):
        with tempfile.TemporaryDirectory() as td:
            source=f'https://example.org/feed\n{Path(td) / "proxy list.txt"}'
            Settings(subscription_url=source).validate()
            with self.assertRaisesRegex(ValueError,'absolute local file path'):
                Settings(subscription_url=source+'\nrelative-file.txt').validate()

    def test_merged_pool_deduplicates_supported_outbound_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            one=root/'one.txt';two=root/'two.txt'
            one.write_text(A+'\n'+B+'\n',encoding='utf-8')
            two.write_text(A_RENAMED+'\n'+C+'\n',encoding='utf-8')
            with patch.object(monitor,'SNAPSHOT',root/'last-good.dat'):
                s=Settings(subscription_url=str(one)+',\n'+str(two))
                s.validate()
                report,state=monitor.load_report(s)
                self.assertEqual(state,'combined-fresh')
                self.assertEqual(report.total,4)
                self.assertEqual(report.duplicates,1)
                self.assertEqual(report.usable,3)
                self.assertEqual(len(report.nodes),3)
                self.assertEqual(len(report.source_statuses),2)
                self.assertNotIn(str(one),str(report.source_statuses))
                self.assertNotIn(str(two),str(report.source_statuses))

    def test_one_failed_feed_is_explicit_and_not_cross_cached(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);one=root/'one.txt';bad=root/'missing.txt'
            one.write_text(A+'\n',encoding='utf-8')
            notices=[]
            with patch.object(monitor,'SNAPSHOT',root/'last-good.dat'):
                report,state=monitor.load_report(Settings(subscription_url=f'{one}\n{bad}'),notices.append,
                                                  allow_cache=False)
            self.assertEqual(state,'combined-incomplete')
            self.assertEqual(report.usable,1)
            self.assertEqual(report.source_statuses[1]['state'],'failed')
            self.assertTrue(any('INCOMPLETE pool' in x for x in notices))
            self.assertFalse(monitor.source_snapshot_path(str(bad)).exists())

    def test_partial_pool_uses_only_exact_source_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'a.txt';b=root/'b.txt'
            a.write_text(A);b.write_text(B)
            with patch.object(monitor,'SNAPSHOT',root/'cache.dat'):
                monitor.load_report(Settings(subscription_url=f'{a}\n{b}'))
                a.unlink()
                report,state=monitor.load_report(Settings(subscription_url=f'{a},{b}'))
            self.assertEqual(state,'combined-incomplete')
            self.assertEqual(report.usable,2)
            self.assertEqual([r['state'] for r in report.source_statuses],
                             ['cached-same-source','local-file'])

    def test_update_only_reports_multi_source_pool_without_starting_core(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            a=root/'a.txt';b=root/'b.txt'
            a.write_text(A+'\n'+B);b.write_text(A_RENAMED+'\n'+C)
            with patch.object(monitor,'DATA_DIR',root),patch.object(monitor,'SNAPSHOT',root/'latest.dat'):
                stats=monitor._unlocked_run_cycle(Settings(subscription_url=f'{a}\n{b}'),threading.Event(),
                                                  update_only=True)
            self.assertEqual(stats['source_count'],2)
            self.assertEqual(stats['total'],4)
            self.assertEqual(stats['parsed'],3)
            self.assertEqual(stats['duplicates'],1)
            self.assertEqual(stats['subscription'],'combined-fresh')
            self.assertTrue(stats['update_only'])

    def test_source_download_checkpoints_isolate_multiple_urls(self):
        # This is important on networks where one source stalls for minutes:
        # subsequent sources must not erase its partial bytes.
        class Incomplete:
            status=200
            headers={'Content-Length':'100','ETag':'"fixed"'}
            def __init__(self):self.reads=0
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read1(self,n):
                self.reads+=1
                if self.reads==1:return b'hello'
                raise socket.timeout('stalled')
        class Opener:
            def open(self,*a,**kw):return Incomplete()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(monitor,'DATA_DIR',Path(td)),patch.object(monitor,'build_opener',return_value=Opener()):
                for name in ('first','second'):
                    with self.assertRaises(socket.timeout):
                        monitor._fetch_remote_resume('https://example.org/'+name,attempts=1,keyed_partial=True)
                staging=Path(td)/'subscription-downloads'
                self.assertEqual(len(list(staging.glob('*.part'))),2)
                self.assertTrue(all(p.read_bytes()==b'hello' for p in staging.glob('*.part')))


class ReliableTests(unittest.TestCase):
    def result(self, url, flow, reliability, verified=True, avg=9.0):
        n=link_node(url)
        p=Probe(n.id,True,100)
        conf=Speed(n.id,mbps=avg,seconds=12,bytes_received=10000,ok=True,
                   verified=verified,flow_mbps=flow)
        return Result(n,p,confirm=conf,reliability=reliability)

    def test_reliability_wins_when_both_have_at_least_one_mbps_floor(self):
        fast=self.result(A,3.0,.60)
        reliable=self.result(B,1.1,.92)
        selected=monitor.reliable_shortlist([fast,reliable])
        self.assertEqual(selected[0].node.id,reliable.node.id)
        self.assertEqual(selected[1].node.id,fast.node.id)

    def test_bursty_and_subthreshold_and_unverified_nodes_are_excluded(self):
        burst=self.result(A,.001,.99,True,avg=80.0)
        marginal=self.result(B,.999,.99)
        unverified=self.result(C,4.0,.99,False)
        just_ok=self.result('trojan://password@d.example:443#D',1.000,.60)
        self.assertEqual(monitor.reliable_shortlist([burst,marginal,unverified,just_ok]),[just_ok])
        self.assertEqual(client.KINDS[-1],'best-reliable')


class SavedWorkingTests(unittest.TestCase):
    def test_working_snapshot_contains_all_successful_nodes_and_is_recoverable(self):
        a=link_node(A);b=link_node(B)
        good=Result(a,Probe(a.id,True,112),confirm=Speed(a.id,mbps=3.2,seconds=12,
                    ok=True,verified=True,flow_mbps=1.15),reliability=.78)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'working-latest.json'
            with patch.object(monitor,'WORKING_SNAPSHOT',path):
                n=monitor.save_working_snapshot([(a,good.probe),(b,Probe(b.id,True,180))],
                                                [good],'1234567890')
                self.assertEqual(n,2)
                snapshot=monitor.read_working_snapshot()
                self.assertEqual(snapshot['source_id'],'1234567890')
                self.assertEqual(len(snapshot['nodes']),2)
                self.assertTrue(snapshot['nodes'][0]['confirmed'])
                self.assertFalse(snapshot['nodes'][1]['confirmed'])
                # A failed following cycle cannot erase the existing working pool.
                self.assertTrue(path.exists())

    def test_untrusted_bad_working_snapshot_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'working-latest.json';path.write_text('{broken')
            with patch.object(monitor,'WORKING_SNAPSHOT',path):
                self.assertEqual(monitor.read_working_snapshot(),{})


class TrafficTests(unittest.TestCase):
    def test_security_warning_for_tls_insecure_or_plaintext_proxy(self):
        self.assertEqual(client.connection_warnings({'type':'vless','tls':{'insecure':False}}),[])
        self.assertEqual(len(client.connection_warnings({'type':'vless','tls':{'insecure':True}})),1)
        self.assertEqual(len(client.connection_warnings({'type':'socks'})),1)
        self.assertEqual(len(client.connection_warnings({'type':'http','tls':{'enabled':True}})),0)

    def test_config_private_loopback_api_with_unique_secret(self):
        outbound={'type':'trojan','server':'some.example','server_port':443,'password':'secret'}
        cfg=client.client_config(outbound,'manual',20808,api_port=20909,api_secret='private-token')
        self.assertEqual(cfg['experimental']['clash_api']['external_controller'],'127.0.0.1:20909')
        self.assertEqual(cfg['experimental']['clash_api']['secret'],'private-token')
        self.assertEqual(len(cfg['outbounds']),1)
        self.assertNotIn('direct',str(cfg['route']))
        self.assertNotIn('experimental',client.client_config(outbound,'manual',20808))
        with self.assertRaises(ValueError):
            client.client_config(outbound,'manual',20808,api_port=20808,api_secret='x')

    def test_api_fetches_real_cumulative_bytes_with_secret(self):
        tokens=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                tokens.append(self.headers.get('Authorization'))
                data=json.dumps({'uploadTotal':12345,'downloadTotal':54321}).encode()
                self.send_response(200)
                self.send_header('Content-Length',str(len(data)))
                self.end_headers();self.wfile.write(data)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            self.assertEqual(client._api_totals(server.server_port,'private-token'),(12345,54321))
            self.assertEqual(tokens,['Bearer private-token'])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

    def test_watcher_converts_cumulative_counters_to_byte_per_second_rates(self):
        class Running:
            def poll(self):return None
        manager=client.ClientManager()
        count=[0]
        def totals(*args,**kwargs):
            count[0]+=1
            return count[0]*1000,count[0]*3000
        try:
            with patch.object(client,'_api_totals',side_effect=totals):
                manager._start_traffic_watcher(Running(),32123,'token')
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and count[0]<2:
                    time.sleep(.05)
                observed=manager.traffic()
                self.assertTrue(observed['available'])
                self.assertGreaterEqual(observed['down'],6000)
                self.assertGreater(observed['down_bps'],1000)
                self.assertGreater(observed['up_bps'],300)
        finally:
            manager._stats_stop.set()
            if manager._stats_thread:manager._stats_thread.join(2)


class GuiPoolTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        self.root.withdraw()
        self.patch=patch.object(gui.Settings,'load',return_value=Settings())
        self.patch.start()
        self.app=gui.App(self.root)
        self.root.update()
    def tearDown(self):
        if hasattr(self,'app'):
            self.app.close()
            try:self.root.update()
            except tk.TclError:pass
        self.patch.stop()

    def test_multiline_field_and_browse_source_identity(self):
        self.app.url.set('https://a.example/sub\nhttps://b.example/sub')
        self.root.update()
        self.assertIn('https://b.example/sub',self.app.feed_sources_text.get('1.0','end'))
        self.app.feed_sources_text.insert('end','\nhttps://c.example/sub')
        self.root.update()
        self.assertEqual(len(split_subscription_sources(self.app.url.get())),3)

    def test_historical_working_pool_survives_restart_without_a_scan(self):
        n=link_node(A)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'working-latest.json'
            with patch.object(monitor,'WORKING_SNAPSHOT',path):
                monitor.save_working_snapshot([(n,Probe(n.id,True,140))],[], 'h'*10)
                self.app.working_tree.delete(*self.app.working_tree.get_children())
                self.app.working_ids.clear()
                self.app.load_previous_working()
                self.assertEqual(len(self.app.working_tree.get_children()),1)
                self.assertIn('Previous scan',self.app.results_tabs.tab(1,'text'))

    def test_working_tab_tracks_successful_https_only(self):
        nodes=[link_node(A),link_node(B)]
        self.app.load_rows(nodes)
        time.sleep(0.04);self.root.update()
        self.assertEqual(len(self.app.tree.get_children()),2)
        self.app.progress_event({'event':'probe-result','node_id':nodes[0].id,
                                 'probe':Probe(nodes[0].id,True,120)})
        self.app.progress_event({'event':'probe-result','node_id':nodes[1].id,
                                 'probe':Probe(nodes[1].id,False,error='timeout')})
        self.root.update()
        self.assertEqual(list(self.app.working_tree.get_children()),[nodes[0].id])
        self.app.results_tabs.select(1)
        self.app.working_tree.selection_set(nodes[0].id)
        self.assertEqual(self.app.selected_nodes()[0].id,nodes[0].id)
        self.assertIn('IRAN REMAINS CONNECTED',self.root.title())
        self.assertIn('best-reliable',self.app.client_category_selector['values'])


if __name__ == '__main__':unittest.main()
