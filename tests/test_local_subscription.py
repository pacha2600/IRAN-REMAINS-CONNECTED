"""The local .txt feed must work without network access or a sing-box core."""
from __future__ import annotations
import gzip
from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from iran_proxy_monitor import monitor, diagnostics
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.diagnostics import CycleFailure
from configure_local_source import configure

DATA = '\n'.join(
    f'trojan://secret@node{i}.example:443?sni=host.example#N{i}' for i in range(5)
).encode('utf-8')


class LocalSubscriptionTests(unittest.TestCase):
    def test_direct_absolute_txt_path_reads_without_web(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'Proxy downloads with spaces.txt'
            source.write_bytes(DATA)
            settings = Settings(subscription_url=str(source))
            settings.validate()
            snapshot = Path(directory) / 'cache.dat'
            with patch.object(monitor, 'SNAPSHOT', snapshot), \
                 patch.object(monitor, 'build_opener', side_effect=AssertionError('unexpected network call')):
                report, origin = monitor.load_report(settings)
                self.assertEqual(report.total, 5)
                self.assertEqual(report.usable, 5)
                self.assertEqual(origin, 'local-file')
                self.assertEqual(snapshot.read_bytes(), DATA)
            self.assertEqual(source.read_bytes(), DATA)

    def test_local_update_reads_new_file_contents_each_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'proxy.txt'
            snapshot = Path(directory) / 'cache.dat'
            source.write_bytes(DATA)
            s = Settings(subscription_url=str(source))
            with patch.object(monitor, 'SNAPSHOT', snapshot):
                first, origin = monitor.load_report(s)
                self.assertEqual(first.total, 5)
                source.write_bytes(DATA + b'\ntrojan://another@node6.example:443#New')
                second, origin = monitor.load_report(s)
                self.assertEqual(second.total, 6)
                self.assertEqual(snapshot.read_bytes(), source.read_bytes())

    def test_missing_local_source_uses_last_valid_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'not-yet-downloaded.txt'
            snapshot = Path(directory) / 'cache.dat'
            source.write_bytes(DATA)
            notifications = []
            with patch.object(monitor, 'SNAPSHOT', snapshot), \
                 patch.object(diagnostics, 'logger', return_value=MagicMock()):
                # Only a prior successful download of THIS source may be used.
                monitor.load_report(Settings(subscription_url=str(source)))
                source.unlink()
                report, origin = monitor.load_report(Settings(subscription_url=str(source)), notifications.append)
            self.assertEqual(report.total, 5)
            self.assertEqual(origin, 'cached-same-source')
            self.assertTrue(any('file not found' in n for n in notifications))

    def test_missing_local_source_without_cache_is_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'secret-subscription.txt'
            with patch.object(monitor, 'SNAPSHOT', Path(directory) / 'cache.dat'), \
                 patch.object(diagnostics, 'logger', return_value=MagicMock()):
                with self.assertRaises(CycleFailure) as caught:
                    monitor.load_report(Settings(subscription_url=str(missing)))
            self.assertEqual(caught.exception.phase, 'subscription-local-file')
            self.assertIn('file not found', str(caught.exception))
            self.assertNotIn('secret-subscription', str(caught.exception))

    def test_rejects_oversized_local_subscription_without_damaging_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'enormous.txt'
            snapshot = Path(directory) / 'cache.dat'
            source.write_bytes(DATA)
            with patch.object(monitor, 'SNAPSHOT', snapshot), \
                 patch.object(diagnostics, 'logger', return_value=MagicMock()):
                monitor.load_report(Settings(subscription_url=str(source)))
                source.write_bytes(b'x' * (monitor.MAX_SUBSCRIPTION_BYTES + 1))
                _, origin = monitor.load_report(Settings(subscription_url=str(source)))
            self.assertEqual(origin, 'cached-same-source')
            self.assertEqual(snapshot.read_bytes(), DATA)

    def test_file_url_still_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'feed percent%5B.txt'
            source.write_bytes(DATA)
            self.assertEqual(monitor.fetch_subscription(source.as_uri()), DATA)

    def test_gzip_expansion_is_size_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            compressed = Path(directory) / 'bomb.gz'
            compressed.write_bytes(gzip.compress(b'x' * (monitor.MAX_SUBSCRIPTION_BYTES + 1)))
            with self.assertRaisesRegex(ValueError, 'exceeds 25 MB'):
                monitor.fetch_subscription(str(compressed))

    def test_windows_drive_path_passes_validation_on_all_platforms(self):
        settings = Settings(subscription_url=r'D:\all_valid_proxies.txt')
        settings.validate()
        self.assertEqual(monitor.source_type(settings.subscription_url), 'local-file')
        with self.assertRaisesRegex(ValueError, 'absolute local file path'):
            Settings(subscription_url='all_valid_proxies.txt').validate()

    def test_local_configurator_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / 'sub.txt'
            src.write_bytes(DATA)
            settings = Settings(subscription_url='https://example.com/old', refresh_minutes=300)
            with patch.object(Settings, 'load', return_value=settings), \
                 patch.object(settings, 'save') as save:
                configure(str(src))
            save.assert_called_once()
            self.assertEqual(settings.subscription_url, str(src))
            self.assertEqual(settings.refresh_minutes, 300)
            self.assertEqual(src.read_bytes(), DATA)

    def test_parse_only_cycle_never_needs_core_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'feed.txt'
            source.write_bytes(DATA)
            snapshot = Path(directory) / 'cache.dat'
            with patch.object(monitor, 'SNAPSHOT', snapshot), \
                 patch.object(monitor, 'DATA_DIR', Path(directory)), \
                 patch.object(monitor, 'SingboxEngine', side_effect=AssertionError('core should not launch')), \
                 patch.object(monitor, 'build_opener', side_effect=AssertionError('no web')):
                stats = monitor.run_cycle(Settings(subscription_url=str(source)), threading.Event(), update_only=True)
            self.assertEqual(stats['total'], 5)
            self.assertEqual(stats['subscription'], 'local-file')
            self.assertEqual(stats['parsed'], 5)


if __name__ == '__main__':
    unittest.main()
