import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

from iran_proxy_monitor.diagnostics import CycleFailure, error_kind, record_failure
from iran_proxy_monitor import diagnostics, monitor
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor.engine import classify_core_stderr

class DiagnosticsTests(unittest.TestCase):
    def test_http_failure_has_status_but_no_url_or_secret(self):
        fake = MagicMock()
        with patch.object(diagnostics, 'logger', return_value=fake):
            try:
                raise HTTPError('https://user:secret@example.org/file?key=token', 403,
                                'Authorization secret leaked', {}, None)
            except HTTPError as exc:
                issue = record_failure(exc, 'subscription-download')
        self.assertEqual(issue.phase, 'subscription-download')
        self.assertEqual(issue.reason, 'HTTP 403')
        self.assertNotIn('secret', str(issue))
        self.assertNotIn('example.org', str(issue))
        captured = ' '.join(str(arg) for arg in fake.log.call_args.args)
        self.assertNotIn('user:secret@', captured)
        self.assertNotIn('example.org', captured)
        self.assertIn(issue.incident_id, captured)

    def test_urlerror_never_logs_raw_reason(self):
        self.assertEqual(error_kind(URLError('https://host.example/?secret=123')), 'URL/network error')

    def test_failed_subscription_without_cache_explains_http_status(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory)/'no-cache.dat'
            notes=[]
            with patch.object(monitor, 'SNAPSHOT', saved), \
                 patch.object(monitor, 'fetch_subscription',
                    side_effect=HTTPError('https://example.org/?token=secret', 404, 'not found', {}, None)), \
                 patch.object(diagnostics, 'logger', return_value=MagicMock()):
                with self.assertRaises(CycleFailure) as raised:
                    monitor.load_report(Settings(subscription_url='https://example.org/?token=secret'), notes.append)
        self.assertIn('HTTP 404', str(raised.exception))
        self.assertNotIn('secret', str(raised.exception))
        self.assertTrue(any('HTTP 404' in note for note in notes))

    def test_core_messages_are_whitelist_labels(self):
        unsafe = b'FATAL config of password=secret\nunknown field: secret'
        self.assertEqual(classify_core_stderr(unsafe), 'unknown-config-field')
        self.assertNotIn('secret', classify_core_stderr(unsafe))

if __name__ == '__main__':
    unittest.main()
