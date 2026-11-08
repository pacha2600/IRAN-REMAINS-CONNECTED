"""Regression coverage for fast probing, stall-aware windows, and distinct exports."""
import threading
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from iran_proxy_monitor import engine, monitor, exporter
from iran_proxy_monitor.models import Probe, Speed, Result
from iran_proxy_monitor.parser import link_node
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.history import History


def node(i):
    return link_node(f'trojan://secret@n{i}.example:443#Test{i}')


class FastSustainedTests(unittest.TestCase):
    def test_fast_default_and_configurable_attempts(self):
        s=Settings()
        self.assertGreaterEqual(s.probe_workers,64)
        self.assertGreaterEqual(s.probe_batch,64)
        self.assertEqual(s.probe_endpoint_attempts,1)
        self.assertGreater(s.confirm_seconds,s.speed_seconds)
        self.assertGreaterEqual(s.confirm_min_kib,8192)
        s.validate()

    def test_probe_only_first_endpoint(self):
        urls=['https://one.invalid/204','https://two.invalid/204']
        n=node(0)
        with patch.object(engine,'http_get',side_effect=TimeoutError('simulated')) as fake:
            out=engine.probe_one(n,12345,urls,2,attempts=1)
        self.assertFalse(out.ok)
        self.assertEqual(fake.call_count,1)
        with patch.object(engine,'http_get',side_effect=[TimeoutError('simulated'),(0,.2,250)]) as fake:
            out=engine.probe_one(n,12345,urls,2,attempts=2)
        self.assertTrue(out.ok)
        self.assertEqual(fake.call_count,2)

    def test_confirmation_rejects_short_burst(self):
        n=node(1)
        def short(url,port,amount,seconds,cancel,measurements=None):
            measurements.update(time_to_first_byte_ms=75,stalled=False)
            return 192*1024,.2,75
        with patch.object(engine,'http_get',side_effect=short):
            out=engine.speed_confirm_one(n,19000,['https://e.invalid/down'],8*1024*1024,9,None,4)
        self.assertTrue(out.ok)
        self.assertFalse(out.verified)
        self.assertGreater(out.mbps,1)

    def test_confirmation_includes_long_stalls_and_validates_only_long_window(self):
        n=node(2)
        def slow(url,port,amount,seconds,cancel,measurements=None):
            measurements.update(time_to_first_byte_ms=2400,stalled=False,active_span_seconds=5)
            return 200*1024,8.5,2400
        with patch.object(engine,'http_get',side_effect=slow):
            out=engine.speed_confirm_one(n,19000,['https://e.invalid/down'],8*1024*1024,9,None,4)
        self.assertTrue(out.verified)
        self.assertLess(out.mbps,.3)
        self.assertEqual(out.seconds,8.5)

    def test_long_wait_then_single_fast_burst_not_verified(self):
        n=node(8)
        def fake(url,port,amount,seconds,cancel,measurements=None):
            measurements.update(stalled=False,active_span_seconds=.05)
            return 8*1024*1024,5.1,5000
        with patch.object(engine,'http_get',side_effect=fake):
            out=engine.speed_confirm_one(n,19000,['https://e.invalid/down'],8*1024*1024,9,None,4)
        self.assertGreater(out.mbps,10)
        self.assertFalse(out.verified)

    def test_stalled_confirmation_not_verified(self):
        n=node(3)
        def stalled(url,port,amount,seconds,cancel,measurements=None):
            measurements.update(stalled=True)
            return 192*1024,5.5,300
        with patch.object(engine,'http_get',side_effect=stalled):
            out=engine.speed_confirm_one(n,19000,['https://e.invalid/down'],8*1024*1024,9,None,4)
        self.assertTrue(out.ok)
        self.assertFalse(out.verified)

    def test_endpoint_retry_never_exceeds_single_node_budget(self):
        n=node(7);cap=64*1024
        calls=[]
        def fake_get(url,port,amount,duration,cancel,measurements=None):
            calls.append(amount)
            if len(calls)==1:
                measurements['bytes_received']=2048
                return 2048,1.0,300
            return amount,5.0,200
        with patch.object(engine,'http_get',side_effect=fake_get):
            out=engine.speed_one(n,18000,['https://a.invalid/1','https://b.invalid/2'],cap,6)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1],cap-2048)
        self.assertEqual(out.bytes_received,cap)

    def test_http_elapsed_includes_ttfb_not_only_fast_body(self):
        from unittest.mock import MagicMock
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read1(self,n):
                return b'x'*1024
        class Opener:
            def open(self,request,timeout):
                import time
                time.sleep(.13)  # simulated TLS + response headers
                return Response()
        with patch.object(engine,'build_opener',return_value=Opener()):
            n,elapsed,ttfb=engine.http_get('https://example.invalid/x',11111,1024,1)
        self.assertEqual(n,1024)
        self.assertGreater(elapsed,.11)
        self.assertGreater(ttfb,110)

    def test_history_and_exploration_includes_slower_latencies(self):
        with tempfile.TemporaryDirectory() as td:
            h=History(Path(td)/'h.sqlite')
            try:
                pairs=[(node(i),Probe(node(i).id,True,100+i*30)) for i in range(110)]
                output=monitor.select_download_candidates(pairs,60,1000,30,h)
                self.assertEqual(len(output),60)
                self.assertTrue(any(p.latency_ms>1000 for n,p in output))
            finally:h.close()

    def test_three_rankings_are_distinct_and_provisional_not_fastest(self):
        a,b,c=node(0),node(1),node(2)
        results=[
            Result(a,Probe(a.id,True,4000),Speed(a.id,12,192000,.2,True),Speed(a.id,3,3000000,7,True,verified=True)),
            Result(b,Probe(b.id,True,120),Speed(b.id,1,192000,2,True),Speed(b.id,2,2000000,7,True,verified=True)),
            Result(c,Probe(c.id,True,70),Speed(c.id,300,192000,.005,True)),
        ]
        with tempfile.TemporaryDirectory() as td:
            h=History(Path(td)/'h.sqlite')
            try:
                fast,ping,overall=monitor.ranking(results,h)
                self.assertEqual(fast[0].node.id,a.id)
                self.assertEqual(ping[0].node.id,c.id)
                self.assertNotIn(c.id,[x.node.id for x in overall])
                self.assertNotEqual(fast[0].node.id,overall[0].node.id)  # responsive / fast balance
            finally:h.close()

    def test_export_names_three_categories_and_secret_preserving_link(self):
        a=node(5)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(exporter,'OUT',Path(td)),patch.object(exporter,'check_core',return_value=True):
                for name in ('best-download-speed','best-ping','best-overall'):
                    files=exporter.export_shortlist([a],name,'fake')
                    self.assertTrue(Path(files['json']).is_file())
                    self.assertEqual(Path(files['links']).read_text('utf-8').strip(),a.source_text)

if __name__=='__main__':unittest.main()

class LegacyUpgradeTests(unittest.TestCase):
    def test_old_confirm_caps_migrate_without_losing_subscription(self):
        import json
        from iran_proxy_monitor import settings as module
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            (base/'settings.json').write_text(json.dumps({
                'subscription_url':'D:\\all_valid_proxies.txt',
                'confirm_min_kib':1024, 'confirm_max_kib':8192,
                'probe_workers':32, 'probe_batch':32}),encoding='utf-8')
            with patch.object(module,'DATA_DIR',base):
                loaded=module.Settings.load()
            self.assertEqual(loaded.confirm_min_kib,8192)
            self.assertEqual(loaded.confirm_max_kib,32768)
            self.assertEqual(loaded.probe_workers,32)  # custom speed choice preserved
            self.assertEqual(loaded.subscription_url,'D:\\all_valid_proxies.txt')
