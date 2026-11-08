"""Regression tests for Windows subscription SOCKS5 and offline-safe scheduling."""
from __future__ import annotations
import json
import queue
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from iran_proxy_monitor import feed_proxy, monitor, exporter, network
from iran_proxy_monitor.scheduler import AutoScheduler
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.models import Node, Probe


class SchedulerTests(unittest.TestCase):
    def test_auto_waits_full_refresh_before_first_scan(self):
        t=AutoScheduler()
        t.arm(120,now=10000)
        self.assertFalse(t.ready(now=10000))
        self.assertEqual(t.remaining(now=10000),7200)
        self.assertFalse(t.ready(now=17199))
        self.assertTrue(t.ready(now=17200))

    def test_hibernation_is_wall_clock_and_no_catch_up_storm(self):
        t=AutoScheduler()
        t.arm(120,now=10000)
        # One hour sleeping does count; still one hour remains.
        self.assertEqual(t.remaining(now=13600),3600)
        # Wake after three hours: run once, then set next interval from end.
        self.assertTrue(t.ready(now=20800))
        t.cycle_finished(now=21100)
        self.assertFalse(t.ready(now=21100))
        self.assertEqual(t.remaining(now=21100),7200)
        self.assertTrue(t.ready(now=28300))

    def test_errors_retry_later_but_never_disarm_automatically(self):
        t=AutoScheduler()
        t.arm(120,now=0)
        t.defer_failed(now=100)
        self.assertEqual(t.remaining(now=100),300)
        self.assertFalse(t.ready(now=399))
        self.assertTrue(t.ready(now=400))
        t.disarm()
        self.assertFalse(t.ready(now=100000))

    def test_bad_interval_rejected(self):
        with self.assertRaises(ValueError):AutoScheduler().arm(0,now=0)


class NetworkRouteTests(unittest.TestCase):
    def test_all_unreachable_means_link_paused(self):
        fake=Mock()
        fake.__enter__=Mock(return_value=fake)
        fake.__exit__=Mock(return_value=None)
        fake.connect_ex.return_value=network.errno.ENETUNREACH
        with patch.object(network.socket,'socket',return_value=fake):
            self.assertFalse(network.outbound_route_present())
            self.assertEqual(fake.connect_ex.call_count,3)

    def test_timeout_is_not_mistaken_for_censored_network_offline(self):
        fake=Mock()
        fake.__enter__=Mock(return_value=fake)
        fake.__exit__=Mock(return_value=None)
        fake.connect_ex.return_value=network.errno.ETIMEDOUT
        with patch.object(network.socket,'socket',return_value=fake):
            self.assertTrue(network.outbound_route_present())
            fake.connect_ex.assert_called_once()


class ProxyRegressionTests(unittest.TestCase):
    def test_https_socks_constructor_does_not_access_removed_handler_attribute(self):
        handler=feed_proxy.Socks5HTTPSHandler('127.0.0.1',3067)
        # Python 3.13+ HTTPSHandler no longer has _check_hostname. It also must
        # work on Python 3.15 as used on the Windows workstation.
        if hasattr(handler,'_check_hostname'):
            del handler._check_hostname  # simulate Python 3.13+ on older CI runtimes
        made=[]
        def fake_do_open(factory, request):
            made.append(factory('example.org',timeout=3))
            return 'ok'
        handler.do_open=fake_do_open
        self.assertEqual(handler.https_open(object()),'ok')
        self.assertEqual(made[0].host,'example.org')
        self.assertEqual(made[0]._proxy_port,3067)

    def test_wrong_local_socks_port_causes_real_network_error_not_attributeerror(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        def reply():
            conn,_=listener.accept()
            with conn:conn.sendall(b'HTTP/1.1 400 Wrong Proxy Protocol\r\n')
            listener.close()
        thread=threading.Thread(target=reply,daemon=True);thread.start()
        with self.assertRaises(OSError):
            feed_proxy.build_feed_opener('manual-socks5','127.0.0.1',port).open(
                'https://example.invalid/feed',timeout=2)
        thread.join(3)

    @unittest.skipUnless(shutil.which('openssl'), 'Local TLS integration requires openssl CLI')
    def test_real_https_through_socks5_local_listener(self):
        """Local synthetic Karing SOCKS5 + HTTPS; no Internet connection needed."""
        with tempfile.TemporaryDirectory() as temp:
            cert=Path(temp)/'cert.pem';key=Path(temp)/'key.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes',
                           '-keyout',str(key),'-out',str(cert),'-days','1',
                           '-subj','/CN=localhost'],capture_output=True,check=True)
            tls_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_context.load_cert_chain(str(cert),str(key))
            listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
            port=listener.getsockname()[1]
            captured={};errors=queue.Queue()
            def proxy_server():
                try:
                    conn,_=listener.accept()
                    with conn:
                        self.assertEqual(feed_proxy._read_exact(conn,3),b'\x05\x01\x00')
                        conn.sendall(b'\x05\x00')
                        self.assertEqual(feed_proxy._read_exact(conn,4),b'\x05\x01\x00\x03')
                        count=feed_proxy._read_exact(conn,1)[0]
                        captured['host']=feed_proxy._read_exact(conn,count).decode()
                        captured['port']=int.from_bytes(feed_proxy._read_exact(conn,2),'big')
                        conn.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00')
                        with tls_context.wrap_socket(conn,server_side=True) as secure:
                            chunks=b''
                            while b'\r\n\r\n' not in chunks:
                                chunks+=secure.recv(2048)
                            captured['request']=chunks
                            secure.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 6\r\nConnection: close\r\n\r\nworked')
                except Exception as exc:
                    errors.put(exc)
                finally:
                    listener.close()
            t=threading.Thread(target=proxy_server,daemon=True)
            t.start()
            handler=feed_proxy.Socks5HTTPSHandler('127.0.0.1',port)
            handler._context=ssl._create_unverified_context()  # test-only self-signed cert
            from urllib.request import build_opener,ProxyHandler
            opener=build_opener(ProxyHandler({}),handler)
            with opener.open('https://localhost:443/feed',timeout=4) as response:
                self.assertEqual(response.read(),b'worked')
            t.join(3)
            if not errors.empty():raise errors.get()
            self.assertEqual(captured['host'],'localhost')
            self.assertEqual(captured['port'],443)
            self.assertIn(b'GET /feed',captured['request'])


class NoBlankOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.node=Node('Test','http',{'type':'http','server':'example.invalid','server_port':8080},'link',
                       'http://example.invalid:8080')
        self.report=Mock(nodes=[self.node], total=1,usable=1,unsupported=0,duplicates=0,format='uri-list',errors={})

    def test_no_connections_skips_without_persisting_or_exporting(self):
        class FakeHistory:
            recorded=[]
            def register(self,nodes):pass
            def select_probes(self,nodes,*args):return nodes
            def record(self,*args):self.recorded.append(args)
            def close(self):pass
        fake_engine=Mock()
        fake_engine.binary='dummy'
        fake_engine.version='sing-box version test'
        fake_engine.connectivity.return_value={self.node.id:Probe(node_id=self.node.id,ok=False,error='timeout')}
        settings=Settings(subscription_url='https://example.com/sub',singbox_path='dummy')
        with (patch.object(monitor,'load_report',return_value=(self.report,'cached-same-source')),
              patch.object(monitor,'SingboxEngine',return_value=fake_engine),
              patch.object(monitor,'History',FakeHistory),
              patch.object(monitor,'export_shortlist') as export_mock,
              patch.object(monitor,'persist_stats') as persist_mock,
              patch.object(monitor,'DATA_DIR',Path(tempfile.gettempdir()))):
            with self.assertRaises(monitor.NoUsableMeasurements):
                monitor._unlocked_run_cycle(settings,threading.Event())
            export_mock.assert_not_called()
            persist_mock.assert_not_called()
            self.assertEqual(FakeHistory.recorded,[])

    def test_empty_export_never_overwrites_previous(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(exporter,'OUT',Path(tmp)):
            existing=Path(tmp)/'best-overall-latest.json'
            existing.write_text('last-good',encoding='utf-8')
            with self.assertRaises(ValueError):
                exporter.export_shortlist([], 'best-overall', 'dummy', validate=False)
            self.assertEqual(existing.read_text(),'last-good')


if __name__=='__main__':unittest.main()
