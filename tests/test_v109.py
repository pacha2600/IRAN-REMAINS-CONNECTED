"""v1.0.9 regression coverage: slow body, cancel, file lock, partial resume, installer."""
from __future__ import annotations
import os
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from iran_proxy_monitor import monitor
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.diagnostics import LOG_FILE
from configure_subscription_source import configure


class SlowFeedHandler(BaseHTTPRequestHandler):
    payload=b'trojan://secret@example.com:443#Works\n' * 1000
    got_request=threading.Event()
    keep_open=threading.Event()
    def do_GET(self):
        data=self.payload
        self.send_response(200)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('ETag','"safe-test-etag"')
        self.end_headers()
        try:
            self.wfile.write(data[:1024])
            self.wfile.flush()
            self.got_request.set()
            self.keep_open.wait(10)
            self.wfile.write(data[1024:])
            self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,OSError):
            pass
    def log_message(self,*args):pass


class Release109Tests(unittest.TestCase):
    def test_cancel_interrupts_real_blocking_http_body(self):
        # A real HTTP response, not a mock returning immediately.
        stop=threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            SlowFeedHandler.got_request.clear()
            SlowFeedHandler.keep_open.clear()
            server=ThreadingHTTPServer(('127.0.0.1',0),SlowFeedHandler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            result=[]
            try:
                with patch.object(monitor,'DATA_DIR',Path(directory)):
                    def run():
                        try:monitor._fetch_remote_resume(
                            f'http://127.0.0.1:{server.server_port}/feed',
                            timeout=120,attempts=2,proxy_mode='direct',cancel=stop)
                        except Exception as e:result.append(e)
                    thread=threading.Thread(target=run,daemon=True)
                    thread.start()
                    self.assertTrue(SlowFeedHandler.got_request.wait(3),'request never opened')
                    time.sleep(.2)
                    started=time.monotonic()
                    stop.set()
                    thread.join(3)
                    self.assertFalse(thread.is_alive(),'Cancel left a 120-second read blocking')
                    self.assertLess(time.monotonic()-started,3)
                    self.assertEqual(len(result),1)
                    self.assertIsInstance(result[0],monitor.OperationCancelled)
                    # Incomplete bytes are a partial cache, not a valid subscription.
                    self.assertTrue((Path(directory)/'subscription-download.part').exists())
            finally:
                SlowFeedHandler.keep_open.set()
                server.shutdown();server.server_close()

    def test_cancel_polling_does_not_depend_on_cross_thread_socket_close(self):
        """Windows recv may ignore shutdown/close from the watcher thread."""
        stop=threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            SlowFeedHandler.got_request.clear()
            SlowFeedHandler.keep_open.clear()
            server=ThreadingHTTPServer(('127.0.0.1',0),SlowFeedHandler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            result=[]
            try:
                with patch.object(monitor,'DATA_DIR',Path(directory)), \
                     patch.object(monitor,'_interrupt_read_on_cancel',
                                  side_effect=lambda response, cancel: threading.Event()):
                    def run():
                        try:
                            monitor._fetch_remote_resume(
                                f'http://127.0.0.1:{server.server_port}/feed',
                                timeout=120, attempts=2, proxy_mode='direct', cancel=stop)
                        except Exception as exc:
                            result.append(exc)
                    worker=threading.Thread(target=run,daemon=True)
                    worker.start()
                    self.assertTrue(SlowFeedHandler.got_request.wait(3))
                    time.sleep(.2)
                    stop.set()
                    worker.join(3)
                    self.assertFalse(worker.is_alive(),
                                     'Stop must work even without Windows socket shutdown')
                    self.assertEqual(len(result),1)
                    self.assertIsInstance(result[0], monitor.OperationCancelled)
                    saved=Path(directory)/'subscription-download.part'
                    self.assertTrue(saved.exists(), 'The partially received feed is checkpointed')
                    self.assertGreater(saved.stat().st_size,0)
            finally:
                SlowFeedHandler.keep_open.set()
                server.shutdown();server.server_close()

    def test_lock_owner_can_be_cancelled_from_another_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(monitor,'DATA_DIR',Path(directory)), \
                 patch.object(monitor,'OWNER',Path(directory)/'owner.json'), \
                 patch.object(monitor,'CANCEL_REQUEST',Path(directory)/'cancel.json'):
                with monitor.single_cycle_lock() as token:
                    self.assertEqual(monitor.active_cycle_info()['run_id'],token)
                    signal=monitor.CombinedStop(threading.Event(),token)
                    self.assertFalse(signal.is_set())
                    self.assertTrue(monitor.request_cancel_active_cycle())
                    # Cross-process flag is cached for 250ms to avoid excessive IO.
                    time.sleep(.28)
                    self.assertTrue(signal.is_set())
                    with self.assertRaises(monitor.CycleBusy):
                        with monitor.single_cycle_lock():pass
                self.assertFalse(monitor.active_cycle_info())
                self.assertFalse((Path(directory)/'cancel.json').exists())
                # A failed/old cancellation cannot poison the next run.
                with monitor.single_cycle_lock() as new_token:
                    self.assertNotEqual(new_token,token)
                    self.assertFalse(monitor.CombinedStop(threading.Event(),new_token).is_set())

    def test_older_running_monitor_without_owner_is_detected_as_busy(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(monitor,'DATA_DIR',Path(directory)), \
                 patch.object(monitor,'OWNER',Path(directory)/'owner.json'), \
                 patch.object(monitor,'CANCEL_REQUEST',Path(directory)/'cancel.json'):
                lock=Path(directory)/'cycle.lock'
                f=lock.open('a+b')
                try:
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    self.assertFalse(monitor.active_cycle_info())
                    self.assertFalse(monitor.request_cancel_active_cycle())
                    with self.assertRaises(monitor.CycleBusy):
                        with monitor.single_cycle_lock():pass
                finally:
                    if os.name=='nt':
                        f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
                    else:fcntl.flock(f,fcntl.LOCK_UN)
                    f.close()

    def test_partial_http_body_resumes_across_application_restarts(self):
        from unittest.mock import MagicMock
        payload=(b'trojan://user@node.example:443#name\n'*2048)
        first_bytes=payload[:1234]
        requested=[]
        class Response:
            def __init__(self,chunk,status,headers,will_stall=False):
                self.status=status;self.headers=headers;self.chunk=chunk
                self.will_stall=will_stall;self.offset=0
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read1(self,n):
                if self.offset<len(self.chunk):
                    data=self.chunk[self.offset:self.offset+n];self.offset+=len(data)
                    return data
                if self.will_stall:raise socket.timeout('simulated interrupted HTTP stream')
                return b''
        def open_url(request,timeout):
            requested.append((request.get_header('Range'),request.get_header('If-range')))
            if len(requested)==1:
                return Response(first_bytes,200,{'Content-Length':str(len(payload)),
                                                  'ETag':'"expected-content-version"'},True)
            return Response(payload[len(first_bytes):],206,
                            {'Content-Range':f'bytes {len(first_bytes)}-{len(payload)-1}/{len(payload)}',
                             'Content-Length':str(len(payload)-len(first_bytes)),
                             'ETag':'"expected-content-version"'})
        with tempfile.TemporaryDirectory() as directory:
            fake_opener=MagicMock();fake_opener.open.side_effect=open_url
            with patch.object(monitor,'DATA_DIR',Path(directory)), \
                 patch.object(monitor,'build_opener',return_value=fake_opener):
                url='https://example.org/feed/safe-test.txt'
                with self.assertRaises(socket.timeout):
                    monitor._fetch_remote_resume(url,attempts=1)
                self.assertEqual((Path(directory)/'subscription-download.part').read_bytes(),first_bytes)
                meta=(Path(directory)/'subscription-download.meta.json').read_text('utf-8')
                self.assertNotIn('example.org',meta)
                completed=monitor._fetch_remote_resume(url,attempts=1)
                self.assertEqual(completed,payload)
                self.assertEqual(requested[0],(None,None))
                self.assertEqual(requested[1],(f'bytes={len(first_bytes)}-','"expected-content-version"'))
                self.assertFalse((Path(directory)/'subscription-download.part').exists())

    def test_installer_preserves_existing_source(self):
        s=Settings(subscription_url=r'C:\Users\User\Downloads\all_valid_proxies.txt')
        with patch.object(Settings,'load',return_value=s),patch.object(s,'save') as save:
            configure('https://example.com/feed',only_if_empty=True)
        self.assertEqual(s.subscription_url,r'C:\Users\User\Downloads\all_valid_proxies.txt')
        save.assert_not_called()
        self.assertIn('--if-empty',(Path(__file__).resolve().parents[1]/'install-local.ps1').read_text())

    def test_update_only_no_saved_results_overwrite_gui(self):
        source=(Path(__file__).resolve().parents[1]/'iran_proxy_monitor/gui.py').read_text('utf-8')
        self.assertIn('if not update_only:',source)
        self.assertIn('persist_stats(stats)',source)
        self.assertNotIn("('Why unsupported?'",source)


if __name__=='__main__':unittest.main()
