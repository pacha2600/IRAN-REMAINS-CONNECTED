"""Regression tests for live rows, rapid probing, concurrency, filtering, resume."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from iran_proxy_monitor import engine, monitor, exporter
from iran_proxy_monitor.parser import link_node
from iran_proxy_monitor.models import Probe, Speed
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.gui import copyable_config


def nodes(n):
    return [link_node(f'trojan://secret@node{i}.example:443?sni=example.com#N{i}') for i in range(n)]


class LiveWorkflowTests(unittest.TestCase):
    def test_defaults_full_scan_latency_first_and_concurrent_speed(self):
        s=Settings()
        self.assertTrue(s.scan_all)
        self.assertEqual(s.latency_cutoff_ms,1000)
        self.assertEqual(s.speed_workers,5)
        self.assertGreater(s.probe_workers,8)
        self.assertLess(s.speed_seconds,8)
        s.validate()

    def test_share_uri_copied_exactly_including_tls_and_reality(self):
        uri='vless://123e4567-e89b-12d3-a456-426614174000@server.example:443?security=reality&pbk=KEY&sid=AB&fp=chrome&sni=example.com#Name'
        self.assertEqual(copyable_config(link_node(uri)),uri)
        original=nodes(1)[0]
        original.source_kind='clash'
        self.assertIn('outbounds',copyable_config(original))
        self.assertNotIn('trojan://',copyable_config(original))

    def test_throughput_five_workers_obey_reservation_and_live_events(self):
        s=Settings(speed_workers=5,probe_batch=32)
        worker=engine.SingboxEngine.__new__(engine.SingboxEngine)
        worker.settings=s;worker.cancel=threading.Event();worker.binary='fake'
        candidates=nodes(18)
        worker.groups=lambda group: ([(group,[18000+i for i in range(len(group))])],[])
        lock=threading.Lock(); active=0; max_active=0
        def fake_speed(node,port,endpoints,amount,duration,cancel):
            nonlocal active,max_active
            with lock:
                active+=1;max_active=max(max_active,active)
            time.sleep(.015)
            with lock:active-=1
            return Speed(node.id,3.5,amount,.015,True)
        callbacks=[]
        with patch.object(engine,'CoreSession') as session,patch.object(engine,'speed_one',fake_speed):
            session.return_value.__enter__.return_value=object()
            result,spent=worker.throughput(candidates,4096,4096*18,callbacks.append)
        self.assertEqual(len(result),18)
        self.assertLessEqual(max_active,5)
        self.assertGreater(max_active,1)
        self.assertEqual(spent,4096*18)
        self.assertEqual(len([e for e in callbacks if e.get('event')=='speed-result']),18)
        self.assertTrue(all(e.get('node_id') for e in callbacks if e.get('event')=='speed-result'))

    def test_throughput_does_not_schedule_over_budget(self):
        s=Settings(speed_workers=5,probe_batch=32)
        worker=engine.SingboxEngine.__new__(engine.SingboxEngine)
        worker.settings=s;worker.cancel=threading.Event();worker.binary='fake'
        candidates=nodes(18)
        worker.groups=lambda group: ([(group,[18000+i for i in range(len(group))])],[])
        def fake_speed(node,port,endpoints,amount,duration,cancel):
            return Speed(node.id,1.5,amount,.4,True)
        with patch.object(engine,'CoreSession') as session,patch.object(engine,'speed_one',fake_speed):
            session.return_value.__enter__.return_value=object()
            result,spent=worker.throughput(candidates,4096,4096*5)
        self.assertEqual(len(result),5)
        self.assertEqual(spent,4096*5)

    def test_responsive_preference_and_exploration_fill_100(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            feed=base/'feed.txt'
            feed.write_text('\n'.join(f'trojan://secret@node{i}.example:443#N{i}' for i in range(115)),'utf-8')
            seen=[];events=[]
            class FakeEngine:
                def __init__(self,settings,cancel):self.binary='fake';self.version='sing-box fake'
                def connectivity(self,nodes,callback):
                    results={}
                    for i,node in enumerate(nodes):
                        # Lower latency at the *end* of subscription to prove proper sorting.
                        p=Probe(node.id,True,float(115-i)*10)
                        results[node.id]=p
                        callback({'event':'probe-result','node_id':node.id,'probe':p})
                    return results
                def baseline(self):return None
                def throughput(self,nodes,max_bytes,budget,callback,phase='preliminary',sizes=None):
                    if phase=='preliminary':seen.extend(nodes)
                    data={n.id:Speed(n.id,1.5,max_bytes,.2,True) for n in nodes}
                    return data,max_bytes*len(nodes)
            s=Settings(subscription_url=str(feed),scan_all=True,baseline_kib=0,
                       latency_cutoff_ms=1000,speed_candidates=100,budget_mib=48,
                       confirm_min_kib=128,confirm_max_kib=128)
            from iran_proxy_monitor.history import History
            with patch.object(monitor,'DATA_DIR',base), patch.object(monitor,'SNAPSHOT',base/'snapshot.dat'),\
                 patch.object(monitor,'History',lambda:History(base/'h.sqlite3')),\
                 patch.object(monitor,'SingboxEngine',FakeEngine),\
                 patch.object(exporter,'OUT',base),patch.object(exporter,'check_core',return_value=True):
                stats=monitor.run_cycle(s,threading.Event(),progress=events.append)
            # 115*10 down to 10; 99 under 1000ms, but also test one slow-ping node.
            self.assertEqual(len(seen),100)
            self.assertEqual(stats['latency_eligible'],99)
            self.assertLessEqual(len(seen),100)
            self.assertEqual(seen[0].name,'N114')
            self.assertTrue(any(int(n.name[1:])<16 for n in seen))
            self.assertTrue(all(e.get('event')=='probe-result' for e in events if e.get('event')=='probe-result'))
            self.assertEqual(len([e for e in events if e.get('event')=='nodes-loaded']),1)


class FakeResponse:
    def __init__(self,status,headers,body,interrupt=False):
        self.status=status;self.headers=headers;self.payload=BytesIO(body)
        self.interrupt=interrupt;self.reads=0
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):
        self.reads+=1
        if self.interrupt and self.reads>1:raise TimeoutError('fake timeout')
        return self.payload.read(4 if self.interrupt else n)


class RemoteResumeTests(unittest.TestCase):
    def test_timeout_retries_with_range_and_joins_only_matching_response(self):
        class Opener:
            def __init__(self):self.headers=[];self.count=0
            def open(self,req,timeout):
                self.headers.append(dict(req.header_items()));self.count+=1
                if self.count==1:
                    return FakeResponse(200,{'Content-Length':'10','ETag':'"abc"'},b'abcd',interrupt=True)
                return FakeResponse(206,{'Content-Length':'6','Content-Range':'bytes 4-9/10'},b'efghij')
        opener=Opener()
        with patch.object(monitor,'build_opener',return_value=opener),patch.object(monitor.time,'sleep'):
            got=monitor._fetch_remote_resume('https://example.com/sample.txt')
        self.assertEqual(got,b'abcdefghij')
        self.assertEqual(opener.headers[1]['Range'],'bytes=4-')
        self.assertEqual(opener.headers[1]['If-range'],'"abc"')

    def test_range_ignored_replaces_partial_body_never_appends(self):
        class Opener:
            def __init__(self):self.count=0
            def open(self,req,timeout):
                self.count+=1
                if self.count==1:return FakeResponse(200,{'Content-Length':'8'},b'abcd',interrupt=True)
                return FakeResponse(200,{'Content-Length':'4'},b'WXYZ')
        with patch.object(monitor,'build_opener',return_value=Opener()),patch.object(monitor.time,'sleep'):
            got=monitor._fetch_remote_resume('https://example.com/f')
        self.assertEqual(got,b'WXYZ')

    def test_settings_support_network_mode(self):
        self.assertEqual(Settings().subscription_proxy_mode,'system')
        Settings(subscription_proxy_mode='direct').validate()
        with self.assertRaises(ValueError):Settings(subscription_proxy_mode='bad').validate()


if __name__=='__main__':unittest.main()
