"""v1.0.17: format negotiation, late scan optimization, recent nodes, usage and sorting."""
import json
import tempfile
import time
import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from iran_proxy_monitor import engine, exporter, monitor, parser, gui
from iran_proxy_monitor.connection_history import remember_connection, recent_connections, clear_connections
from iran_proxy_monitor.scan_usage import record_scan_usage, daily_payload_bytes
from iran_proxy_monitor.models import Node
from iran_proxy_monitor.settings import Settings

URI='trojan://testpw@node.example:443#Example'

class FormatsAndRecoveryTests(unittest.TestCase):
    def test_unwrap_json_lists_and_nested_string_list(self):
        for payload in [json.dumps([URI]),json.dumps({'data':[URI]}),json.dumps({'data':{'nodes':[URI]}}),
                        json.dumps({'data':URI}), 'nodes:\n  - '+URI+'\n']:
            report=parser.parse_subscription(payload)
            self.assertEqual(report.usable,1,payload)

    def test_html_refused(self):
        with self.assertRaisesRegex(ValueError,'HTML'):
            parser.parse_subscription('<html><body>blocked</body></html>')

    def test_no_supported_after_download_never_triggers_unbound_local(self):
        with tempfile.TemporaryDirectory() as td:
            remote='https://panel.example/sub/token'
            with patch.object(monitor,'SNAPSHOT',Path(td)/'snapshot.dat'),patch.object(monitor,'fetch_subscription',return_value=b'<html>expired</html>') as fetch:
                with self.assertRaises(monitor.CycleFailure) as ctx:
                    monitor.load_report(Settings(subscription_url=remote),allow_cache=False)
            self.assertEqual(fetch.call_count,5)
            self.assertNotIn('UnboundLocalError',str(ctx.exception))

    def test_user_agent_negotiates_a_json_list(self):
        with tempfile.TemporaryDirectory() as td:
            remote='https://panel.example/sub/token'
            def fetch(*_args,**kwargs):
                if kwargs.get('request_agent','').startswith('v2rayNG'):
                    return json.dumps({'data':[URI]}).encode()
                return b'<html><body>Requires a subscription client</body></html>'
            with patch.object(monitor,'SNAPSHOT',Path(td)/'snapshot.dat'),patch.object(monitor,'fetch_subscription',side_effect=fetch) as f:
                report,state=monitor.load_report(Settings(subscription_url=remote),allow_cache=False)
            self.assertEqual((report.usable,state),(1,'fresh'))
            self.assertEqual(f.call_count,2)
            self.assertEqual(report.source_statuses[0]['fetched_bytes'],len(json.dumps({'data':[URI]}).encode()))

class RecentHistoryTests(unittest.TestCase):
    def test_recent_dedup_ten_limit_and_clear(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'recent.json'
            for i in range(12):
                remember_connection(f'node-{i}',{'type':'socks','server':f's{i}.example','server_port':1080},'manual',path)
            entries=recent_connections(path)
            self.assertEqual(len(entries),10)
            self.assertEqual(entries[0]['name'],'node-11')
            self.assertEqual(entries[-1]['name'],'node-2')
            remember_connection('same server renamed',entries[-1]['outbound'],'system',path)
            entries=recent_connections(path)
            self.assertEqual(len(entries),10)
            self.assertEqual(entries[0]['name'],'same server renamed')
            self.assertEqual(entries[0]['mode'],'system')
            self.assertNotIn('node-2',str(entries))
            clear_connections(path)
            self.assertEqual(recent_connections(path),[])

class WorkingExportTests(unittest.TestCase):
    def test_all_working_bpf_json_and_mixed_txt(self):
        with tempfile.TemporaryDirectory() as td:
            node=parser.link_node(URI)
            other=Node('YAML-node','socks',{'type':'socks','server':'socks.example','server_port':1080},
                       'clash',json.dumps({'name':'YAML-node','server':'socks.example'}))
            with patch.object(exporter,'OUT',Path(td)), patch.object(exporter,'check_core',return_value=True):
                result=exporter.export_all_working([node,other],'/unused')
                self.assertEqual(result['nodes'],2)
                self.assertEqual(result['uri_count'],1)
                json_out=json.loads(Path(result['json']).read_text())
                self.assertEqual(len(json_out['outbounds']),3)
                from iran_proxy_monitor.bpf import decode_bpf
                _,config=decode_bpf(Path(result['bpf']).read_bytes())
                self.assertEqual(config['outbounds'],json_out['outbounds'])
                lines=Path(result['txt']).read_text().splitlines()
                self.assertEqual(len(lines),2)
                self.assertEqual(lines[0],URI)
                self.assertEqual(json.loads(lines[1])['outbounds'][0]['server'],'socks.example')

class ScanUsageTests(unittest.TestCase):
    def test_daily_lower_bound_persisted(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'usage.json'
            self.assertEqual(record_scan_usage(1048576,time.time(),'abc',path),1.0)
            self.assertEqual(record_scan_usage(524288,time.time(),'def',path),1.5)
            self.assertEqual(daily_payload_bytes(path=path),1572864)

class GuiTabsTests(unittest.TestCase):
    def test_separate_sort_state_in_working_tab(self):
        root=tk.Tk();root.withdraw()
        app=None
        try:
            with tempfile.TemporaryDirectory() as td,patch('iran_proxy_monitor.gui.recent_connections',return_value=[]):
                app=gui.App(root)
                self.assertEqual(len(app.results_tabs.tabs()),3)
                a=parser.link_node('trojan://secret@a.example:443#A')
                b=parser.link_node('trojan://secret@b.example:443#B')
                app.load_rows([a,b]);root.update()
                for node,rate in [(a,2.0),(b,5.0)]:
                    app.row_state[node.id].update(latency=100,mbps=rate,flow_mbps=rate,confirmed=True)
                    app._mark_working(node.id)
                    app.update_row(node.id)
                app.sort('download',app.working_tree)
                order=app.working_tree.get_children('')
                self.assertEqual(order[0],b.id)
                self.assertEqual(app.working_table_sort,'download')
                self.assertEqual(app.table_sort,'latency')
                # resorting ALL nodes does not overwrite the Working table order
                app.sort('name',app.tree)
                self.assertEqual(app.working_tree.get_children('')[0],b.id)
        finally:
            if app:
                try:app.close()
                except Exception:root.destroy()
            else:root.destroy()

if __name__=='__main__':unittest.main()

class LateBatchTests(unittest.TestCase):
    def test_large_invalid_batch_splits_to_32_and_does_not_skip_nodes(self):
        from unittest.mock import patch
        nodes=[parser.link_node(f'trojan://password@server{i}.example:443#Node{i}') for i in range(128)]
        invalid=nodes[87].id
        e=engine.SingboxEngine.__new__(engine.SingboxEngine)
        e.binary='fake-bin';e.cancel=threading.Event()
        e._cache_rejected={};e._cache_lock=threading.RLock()
        sizes=[]
        def checker(binary,config,*args,**kwargs):
            size=len(config['outbounds'])-1
            sizes.append(size)
            valid=not any(outbound.get('server')=='server87.example' for outbound in config['outbounds'])
            return (valid,'core-config-rejected') if kwargs.get('details') else valid
        with patch.object(engine,'check_core',side_effect=checker):
            good,bad=e.groups(nodes)
        self.assertIn(128,sizes)
        self.assertNotIn(64,sizes)
        self.assertIn(32,sizes)
        self.assertEqual(sum(len(group) for group,_ in good),127)
        self.assertEqual([n.id for n,_ in bad],[invalid])
