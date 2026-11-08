"""v1.0.10 aggressive latency + independent two-host diagnostics tests."""
import json
import tempfile
import time
from unittest.mock import Mock
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.models import Node, Speed
from iran_proxy_monitor import compare
from iran_proxy_monitor.engine import SingboxEngine
from iran_proxy_monitor import engine


class FakeSession:
    def __init__(self,*args):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass


class V110Tests(unittest.TestCase):
    def node(self):
        return Node('test','http',{'type':'http','server':'sample.invalid','server_port':1234},
                    'link','http://username:password@sample.invalid:1234')

    def test_aggressive_defaults(self):
        s=Settings()
        self.assertEqual((s.speed_candidates,s.probe_processes,s.probe_batch,s.probe_workers),
                         (250,4,128,128))
        self.assertEqual(s.budget_mib,256)

    def test_upgrade_exact_old_preset(self):
        from iran_proxy_monitor import settings
        with tempfile.TemporaryDirectory() as d:
            Path(d,'settings.json').write_text(json.dumps({'probe_batch':96,'probe_workers':96,
                'probe_processes':2,'speed_candidates':100,'budget_mib':128.0}),encoding='utf-8')
            with patch.object(settings,'DATA_DIR',Path(d)):
                s=Settings.load()
            self.assertEqual((s.probe_batch,s.probe_processes,s.speed_candidates,s.budget_mib),
                             (128,4,250,256.0))

    def test_custom_workers_are_not_overridden(self):
        from iran_proxy_monitor import settings
        with tempfile.TemporaryDirectory() as d:
            Path(d,'settings.json').write_text(json.dumps({'probe_batch':32,'probe_workers':15,
                'probe_processes':1,'speed_candidates':175,'budget_mib':90.0}),encoding='utf-8')
            with patch.object(settings,'DATA_DIR',Path(d)):
                s=Settings.load()
            self.assertEqual((s.probe_batch,s.probe_processes,s.speed_candidates,s.budget_mib),
                             (32,1,175,90.0))

    def test_comparison_uses_two_distinct_hosts_and_no_direct_fallback(self):
        calls=[]
        def fake_speed(n,port,urls,amount,seconds,cancel,min_seconds):
            calls.append((port,urls,amount,seconds,min_seconds))
            return Speed(n.id,2.0,amount,5.0,True,verified=True)
        with patch.object(compare,'find_singbox',return_value='fake-core'), \
             patch.object(compare,'available_ports',return_value=[34567]), \
             patch.object(compare,'check_core',return_value=True), \
             patch.object(compare,'CoreSession',FakeSession), \
             patch.object(compare,'speed_confirm_one',side_effect=fake_speed):
            result=compare.compare_node(self.node(),Settings(),threading.Event())
        self.assertEqual(len(result),2)
        self.assertEqual(len(calls),2)
        self.assertNotEqual(result[0][0],result[1][0])
        self.assertEqual({args[0] for args in calls},{34567})
        self.assertEqual(calls[0][2],4*1024*1024)
        summary=compare.format_comparison(result)
        self.assertIn('2.000 Mbps',summary)
        self.assertNotIn('password',summary)

    def test_comparison_requires_two_hosts(self):
        s=Settings(download_urls=['https://a.example/one','https://a.example/two'])
        with self.assertRaisesRegex(ValueError,'distinct hosts'):
            compare.compare_node(self.node(),s)

    def test_bursty_confirmation_not_verified_in_long_window(self):
        node=self.node()
        def burst(url,port,amount,seconds,cancel,measurements=None):
            measurements.update(active_span_seconds=6.0,active_seconds=3,stalled=False)
            return 4*1024*1024,9.0,300
        with patch.object(engine,'http_get',side_effect=burst):
            measured=engine.speed_confirm_one(node,12001,['https://a.example/down'],
                                              8*1024*1024,9.0,None,4.0)
        self.assertTrue(measured.ok)
        self.assertFalse(measured.verified)

    def test_distributed_confirmation_can_verify(self):
        node=self.node()
        def distributed(url,port,amount,seconds,cancel,measurements=None):
            measurements.update(active_span_seconds=7.0,active_seconds=8,stalled=False)
            return 4*1024*1024,9.0,300
        with patch.object(engine,'http_get',side_effect=distributed):
            measured=engine.speed_confirm_one(node,12001,['https://a.example/down'],
                                              8*1024*1024,9.0,None,4.0)
        self.assertTrue(measured.verified)

    def test_rejected_core_cache_does_not_store_credentials(self):
        n=self.node()
        engine=SingboxEngine.__new__(SingboxEngine)
        engine.binary='fake-core'
        engine.version='sing-box 1.14.4'
        engine.cancel=threading.Event()
        engine._cache_lock=threading.Lock()
        engine._cache_rejected={}
        with tempfile.TemporaryDirectory() as d:
            engine._cache_path=Path(d)/'core-compatibility.json'
            with patch('iran_proxy_monitor.engine.check_core',return_value=(False,'core-config-rejected')):
                ok,bad=engine.groups([n])
            self.assertFalse(ok)
            self.assertIn(n.id,engine._cache_rejected)
            engine.save_core_cache()
            contents=engine._cache_path.read_text()
            self.assertNotIn('password',contents)
            self.assertNotIn('sample.invalid',contents)
            with patch('iran_proxy_monitor.engine.check_core',side_effect=AssertionError('must use cache')):
                ok,bad=engine.groups([n])
            self.assertFalse(ok)
            self.assertEqual(len(bad),1)

    def test_compatibility_cache_expires_and_is_core_version_scoped(self):
        with tempfile.TemporaryDirectory() as d:
            from iran_proxy_monitor import engine as e
            cache_file=Path(d)/'core-compatibility.json'
            cache_file.write_text(json.dumps({'core_version':'sing-box version 1.14.4',
                'created_at':time.time()-10,'rejected':{'hash':'core-config-rejected'}}))
            fake_process=Mock(returncode=0,stdout=b'sing-box version 1.14.4\n')
            with patch.object(e,'DATA_DIR',Path(d)), \
                 patch.object(e,'find_singbox',return_value='fake-core'), \
                 patch.object(e.subprocess,'run',return_value=fake_process):
                core=e.SingboxEngine(Settings(),threading.Event())
            self.assertEqual(core._cache_rejected.get('hash'),'core-config-rejected')
            cache_file.write_text(json.dumps({'core_version':'sing-box version 1.14.4',
                'created_at':time.time()-7*3600,'rejected':{'hash':'core-config-rejected'}}))
            with patch.object(e,'DATA_DIR',Path(d)), \
                 patch.object(e,'find_singbox',return_value='fake-core'), \
                 patch.object(e.subprocess,'run',return_value=fake_process):
                expired=e.SingboxEngine(Settings(),threading.Event())
            self.assertFalse(expired._cache_rejected)
            cache_file.write_text(json.dumps({'core_version':'sing-box version 1.13.0',
                'created_at':time.time(),'rejected':{'hash':'core-config-rejected'}}))
            with patch.object(e,'DATA_DIR',Path(d)), \
                 patch.object(e,'find_singbox',return_value='fake-core'), \
                 patch.object(e.subprocess,'run',return_value=fake_process):
                changed=e.SingboxEngine(Settings(),threading.Event())
            self.assertFalse(changed._cache_rejected)

    def test_invalid_core_runtime_failure_not_cached(self):
        n=self.node(); e=SingboxEngine.__new__(SingboxEngine)
        e.binary='fake';e.cancel=threading.Event()
        e._cache_lock=threading.Lock();e._cache_rejected={}
        with patch('iran_proxy_monitor.engine.check_core',return_value=(False,'TimeoutExpired')):
            e.groups([n])
        self.assertFalse(e._cache_rejected)

if __name__=='__main__': unittest.main()
