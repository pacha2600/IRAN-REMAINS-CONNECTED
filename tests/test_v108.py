"""Fixes for interrupted feeds and bounded, parallel HTTPS latency scanning."""
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
from pathlib import Path

from iran_proxy_monitor import engine, monitor
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.models import Probe
from iran_proxy_monitor.parser import link_node
from configure_subscription_source import configure

URL='https://raw.githubusercontent.com/sakha1370/OpenRay/refs/heads/main/output/all_valid_proxies.txt'


def node(i):
    return link_node(f'trojan://password@n{i}.example:443#Node{i}')


class V108Tests(unittest.TestCase):
    def test_stall_timeout_and_parallel_defaults(self):
        settings=Settings(subscription_url=URL)
        self.assertEqual(settings.subscription_timeout_seconds,300)
        self.assertEqual(settings.probe_processes,4)
        settings.validate()
        settings.subscription_timeout_seconds=9
        with self.assertRaises(ValueError):settings.validate()
        settings.subscription_timeout_seconds=601
        with self.assertRaises(ValueError):settings.validate()

    def test_local_installer_points_to_url_and_keeps_local_core(self):
        root=Path(__file__).resolve().parents[1]
        script=(root/'install-local.ps1').read_text('utf-8')
        self.assertIn(URL,script)
        self.assertIn("'D:\\sing-box.exe'",script)
        self.assertIn(' -NoDownload',script)
        self.assertIn('configure_subscription_source.py',script)
        self.assertIn('Downloading official sing-box', (root/'install.ps1').read_text('utf-8'))

    def test_local_installer_configurator_updates_source_and_timeout(self):
        s=Settings(subscription_url=r'D:\\all_valid_proxies.txt',refresh_minutes=180,
                   subscription_timeout_seconds=20)
        with patch.object(Settings,'load',return_value=s),patch.object(s,'save') as save:
            configure(URL)
        self.assertEqual(s.subscription_url,URL)
        self.assertEqual(s.subscription_timeout_seconds,300)
        self.assertEqual(s.refresh_minutes,180)
        save.assert_called_once()

    def test_feed_fetch_passes_requested_300s_timeout(self):
        with patch.object(monitor,'_fetch_remote_resume',return_value=b'fake') as get:
            x=monitor.fetch_subscription(URL,timeout=300,proxy_mode='direct')
        self.assertEqual(x,b'fake')
        self.assertEqual(get.call_args.kwargs['on_progress'],None)
        self.assertEqual(get.call_args.args[:3],(URL,300,'direct'))

    def test_https_probe_deadline_is_end_to_end(self):
        listener=socket.socket()
        listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        def stall():
            try:
                conn,_=listener.accept()
                with conn:
                    conn.recv(2048)
                    time.sleep(.7)
            finally:listener.close()
        t=threading.Thread(target=stall,daemon=True);t.start()
        start=time.monotonic()
        with self.assertRaises((TimeoutError,socket.timeout)):
            engine.strict_https_probe('https://example.com/generate_204',port,.20)
        elapsed=time.monotonic()-start
        self.assertLess(elapsed,.6)
        self.assertGreater(elapsed,.15)

    def test_https_probe_rejects_failed_connect_tunnel(self):
        listener=socket.socket()
        listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        def refuse():
            with listener:
                conn,_=listener.accept()
                with conn:
                    conn.recv(2048)
                    conn.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n')
        threading.Thread(target=refuse,daemon=True).start()
        with self.assertRaisesRegex(ConnectionError,'CONNECT'):
            engine.strict_https_probe('https://example.com/generate_204',port,1.0)

    def test_core_check_classification_safe(self):
        proc=Mock(returncode=1,stderr=b'config rejected unknown transport type and SECRET_URL')
        with patch.object(engine.subprocess,'run',return_value=proc):
            valid,why=engine.check_core('fake',engine.batch_config([node(1)],[19000]),details=True)
        self.assertFalse(valid)
        self.assertEqual(why,'unsupported-transport-type')
        self.assertNotIn('SECRET',why)

    def test_parallel_core_batches_merge_probe_results(self):
        settings=Settings(probe_batch=2,probe_processes=2,probe_workers=2)
        e=object.__new__(engine.SingboxEngine)
        e.settings=settings;e.cancel=threading.Event()
        items=[node(i) for i in range(8)]
        seen=[]
        lock=threading.Lock()
        active=0
        max_active=[0]
        def fake_batch(batch,cb):
            nonlocal active
            with lock:
                active+=1;max_active[0]=max(max_active[0],active)
            time.sleep(.05)
            with lock:active-=1
            out={n.id:Probe(n.id,True,100) for n in batch}
            for n in batch:cb({'event':'probe-result','node_id':n.id,'probe':out[n.id]})
            return out
        with patch.object(e,'_connectivity_batch',side_effect=fake_batch):
            r=e.connectivity(items,seen.append)
        self.assertEqual(len(r),8)
        self.assertEqual(max_active[0],2)
        self.assertEqual(len([x for x in seen if x.get('event')=='probe-result']),8)
        self.assertEqual([x for x in seen if x.get('phase')=='connectivity'][-1]['done'],8)

    def test_http_resume_recovers_truncated_response(self):
        payload=(b'vless://some-configuration\n'*1024)
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                field=self.headers.get('Range')
                calls.append(field)
                if field:
                    start=int(field.split('=')[1].split('-')[0])
                    self.send_response(206)
                    self.send_header('Content-Range',f'bytes {start}-{len(payload)-1}/{len(payload)}')
                    self.send_header('Content-Length',str(len(payload)-start))
                    self.end_headers()
                    self.wfile.write(payload[start:]);self.wfile.flush()
                else:
                    self.send_response(200)
                    self.send_header('Content-Length',str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload[:2000]);self.wfile.flush()
                    self.close_connection=True
            def log_message(self,*args):pass
        srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        try:
            received=monitor._fetch_remote_resume(
                f'http://127.0.0.1:{srv.server_port}/feed.txt',timeout=1,
                proxy_mode='direct',attempts=3)
        finally:
            srv.shutdown();srv.server_close()
        self.assertEqual(received,payload)
        self.assertEqual(calls,[None,'bytes=2000-'])

    def test_single_burst_cannot_verify_speed_even_after_nine_seconds(self):
        n=node(12)
        def just_one_burst(url,port,amount,duration,cancel,measurements=None):
            measurements.update(active_span_seconds=5.0,active_seconds=1,
                                stalled=False,time_to_first_byte_ms=300)
            return 2000000,9.0,300
        with patch.object(engine,'http_get',side_effect=just_one_burst):
            speed=engine.speed_confirm_one(n,12345,['https://example.com/down'],8000000,9,None,4)
        self.assertTrue(speed.ok)
        self.assertFalse(speed.verified)

    def test_multi_second_data_can_verify_speed(self):
        n=node(11)
        def spread_out(url,port,amount,duration,cancel,measurements=None):
            measurements.update(active_span_seconds=5.0,active_seconds=5,
                                stalled=False,time_to_first_byte_ms=300)
            return 2000000,8.0,300
        with patch.object(engine,'http_get',side_effect=spread_out):
            speed=engine.speed_confirm_one(n,12345,['https://example.com/down'],8000000,9,None,4)
        self.assertTrue(speed.verified)

    def test_gui_has_unsupported_diagnostics(self):
        source=(Path(__file__).resolve().parents[1]/'iran_proxy_monitor/gui.py').read_text('utf-8')
        self.assertIn('Explain selected result',source)
        self.assertNotIn('Why unsupported?',source)
        self.assertIn('node.problems',source)
        self.assertIn('Core startup error',source)

if __name__=='__main__':unittest.main()
