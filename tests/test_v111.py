"""v1.0.11 regressions: subscription identity and safe HTTP resumption."""
from __future__ import annotations
from io import BytesIO
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

from iran_proxy_monitor import monitor
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.diagnostics import CycleFailure

NODE_A = b'trojan://password@first.example:443#Feed_A\n'
NODE_B = b'trojan://password@second.example:443#Feed_B\n'


class Response:
    def __init__(self, status, headers, payload, interrupt=False):
        self.status = status
        self.headers = headers
        self.stream = BytesIO(payload)
        self.interrupt = interrupt
        self.first = True

    def __enter__(self): return self
    def __exit__(self, *unused): return False
    def read1(self, size):
        if self.interrupt and not self.first:
            raise socket.timeout('interrupted body')
        self.first = False
        return self.stream.read(min(size, 5) if self.interrupt else size)


class Release111Tests(unittest.TestCase):
    def test_new_url_never_inherits_nodes_from_last_successful_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a = root/'a.txt'
            b = root/'b.txt'
            a.write_bytes(NODE_A)
            with patch.object(monitor, 'SNAPSHOT', root/'last-good.dat'):
                report, origin = monitor.load_report(Settings(subscription_url=str(a)))
                self.assertEqual(report.total, 1)
                self.assertEqual(origin, 'local-file')
                self.assertEqual((root/'last-good.dat').read_bytes(), NODE_A)
                self.assertTrue(monitor.source_snapshot_path(str(a)).exists())
                with self.assertRaises(CycleFailure) as caught:
                    monitor.load_report(Settings(subscription_url=str(b)))
                self.assertIn('NOT loaded', str(caught.exception))
                # The old cache survives, but may not be substituted for source B.
                self.assertEqual((root/'last-good.dat').read_bytes(), NODE_A)
                self.assertFalse(monitor.source_snapshot_path(str(b)).exists())

    def test_legacy_global_snapshot_does_not_claim_new_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'last-good.dat').write_bytes(NODE_A)
            with patch.object(monitor, 'SNAPSHOT', root/'last-good.dat'):
                with self.assertRaises(CycleFailure):
                    monitor.load_report(Settings(subscription_url=str(root/'new.txt')))

    def test_same_source_cache_is_used_only_for_full_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'a.txt'
            source.write_bytes(NODE_A)
            with patch.object(monitor, 'SNAPSHOT', root/'last-good.dat'):
                monitor.load_report(Settings(subscription_url=str(source)))
                source.unlink()
                report, origin = monitor.load_report(Settings(subscription_url=str(source)))
                self.assertEqual(origin, 'cached-same-source')
                self.assertEqual(report.nodes[0].name, 'Feed_A')
                with self.assertRaises(CycleFailure) as issue:
                    monitor.load_report(Settings(subscription_url=str(source)), allow_cache=False)
                self.assertIn('NOT loaded', str(issue.exception))

    def test_cache_is_per_source_even_after_switching_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a = root/'a.txt'
            b = root/'b.txt'
            a.write_bytes(NODE_A)
            b.write_bytes(NODE_B)
            with patch.object(monitor, 'SNAPSHOT', root/'last-good.dat'):
                monitor.load_report(Settings(subscription_url=str(a)))
                monitor.load_report(Settings(subscription_url=str(b)))
                a.unlink()
                report, origin = monitor.load_report(Settings(subscription_url=str(a)))
                self.assertEqual(origin, 'cached-same-source')
                self.assertEqual(report.nodes[0].name, 'Feed_A')
                self.assertEqual((root/'last-good.dat').read_bytes(), NODE_B)

    def test_partial_from_source_a_is_not_resumed_for_source_b(self):
        calls = []
        def fake_open(request, timeout):
            calls.append((request.full_url, request.get_header('Range')))
            if len(calls) == 1:
                return Response(200, {'Content-Length': '10', 'ETag':'"a"'}, b'12345', interrupt=True)
            return Response(200, {'Content-Length': str(len(NODE_B))}, NODE_B)
        fake = MagicMock()
        fake.open.side_effect = fake_open
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(monitor, 'DATA_DIR', Path(directory)), \
                    patch.object(monitor, 'build_opener', return_value=fake):
                with self.assertRaises(socket.timeout):
                    monitor._fetch_remote_resume('https://one.example/feed', attempts=1)
                got=monitor._fetch_remote_resume('https://two.example/feed', attempts=1)
                self.assertEqual(got,NODE_B)
                self.assertEqual(calls[1][1],None)
                self.assertFalse((Path(directory)/'subscription-download.part').exists())

    def test_etag_change_during_range_restart_starts_fresh(self):
        calls=[]
        body1=b'abcdefghij'
        body2=b'0123456789'
        def fake_open(request, timeout):
            calls.append((request.get_header('Range'), request.get_header('If-range')))
            if len(calls)==1:
                return Response(200,{'Content-Length':'10','ETag':'"old"'},body1[:5],True)
            if len(calls)==2:
                return Response(206,{'Content-Range':'bytes 5-9/10','ETag':'"new"'},body2[5:])
            return Response(200,{'Content-Length':'10','ETag':'"new"'},body2)
        fake=MagicMock();fake.open.side_effect=fake_open
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(monitor, 'DATA_DIR', Path(directory)), \
                    patch.object(monitor, 'build_opener', return_value=fake), \
                    patch.object(monitor.time, 'sleep'):
                self.assertEqual(monitor._fetch_remote_resume('https://example.com/source',attempts=3),body2)
                self.assertEqual(calls,[(None,None),('bytes=5-','"old"'),(None,None)])
                self.assertFalse((Path(directory)/'subscription-download.meta.json').exists())

    def test_validator_mismatch_after_previous_session_no_permanent_valueerror(self):
        calls=[]
        def fake_open(request, timeout):
            calls.append(request.get_header('Range'))
            if len(calls)==1:
                return Response(200,{'Content-Length':'10','ETag':'"old"'},b'abcde',True)
            if len(calls)==2:
                return Response(206,{'Content-Range':'bytes 5-9/10','ETag':'"new"'},b'56789')
            return Response(200,{'Content-Length':'10','ETag':'"new"'},b'0123456789')
        fake=MagicMock();fake.open.side_effect=fake_open
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(monitor,'DATA_DIR',Path(directory)), \
                 patch.object(monitor,'build_opener',return_value=fake):
                with self.assertRaises(socket.timeout):
                    monitor._fetch_remote_resume('https://example.com/sub',attempts=1)
                self.assertEqual(monitor._fetch_remote_resume('https://example.com/sub',attempts=2),b'0123456789')
        self.assertEqual(calls,[None,'bytes=5-',None])

    def test_cache_metadata_and_logs_do_not_contain_secret_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'subscription.dat'
            path.write_bytes(NODE_A)
            with patch.object(monitor,'SNAPSHOT',root/'last-good.dat'):
                monitor.load_report(Settings(subscription_url=str(path)))
                metadata=(root/'subscription-last-good.meta.json').read_text()
                self.assertNotIn(str(path),metadata)
                self.assertEqual(json.loads(metadata)['source_key'],monitor.subscription_fingerprint(str(path)))
                self.assertEqual(len(monitor.subscription_fingerprint(str(path))),64)

    def test_gui_distinguishes_stale_and_active_subscription(self):
        text=(Path(__file__).resolve().parents[1]/'iran_proxy_monitor/gui.py').read_text()
        self.assertIn('Selected source NOT loaded',text)
        self.assertIn('Previous run stays visible until it succeeds',text)
        self.assertIn('STALE CACHE (same source; update failed)',text)


if __name__=='__main__':unittest.main()
