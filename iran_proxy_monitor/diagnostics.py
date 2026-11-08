"""Local, rotating, credential-safe operational diagnostics.

Never log raw exceptions, URLs, proxy node details or sing-box output: those can
contain subscription tokens, passwords, proxy credentials and secret keys.
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from logging import Formatter, getLogger, INFO
from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging
import os
import secrets
import socket
import sqlite3
import ssl
import traceback
from urllib.error import HTTPError, URLError

from .settings import DATA_DIR

LOG_DIR = DATA_DIR / 'logs'
LOG_FILE = LOG_DIR / 'monitor.log'
CURRENT_STAGE = ContextVar('monitor_stage', default='startup')


def stage(value: str) -> None:
    """Set only hardcoded phase labels: never pass arbitrary user content."""
    CURRENT_STAGE.set(value)


def logger() -> logging.Logger:
    result = getLogger('iran_proxy_monitor')
    if not getattr(result, '_ipm_configured', False):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024,
                                      backupCount=3, encoding='utf-8')
        handler.setFormatter(Formatter('%(asctime)s %(levelname)s [pid=%(process)d] %(message)s'))
        result.addHandler(handler)
        result.setLevel(INFO)
        result.propagate = False
        result._ipm_configured = True
        try:
            if os.name != 'nt':
                os.chmod(LOG_DIR, 0o700)
                os.chmod(LOG_FILE, 0o600)
        except OSError:
            pass
    return result


def error_kind(exc: BaseException) -> str:
    """Classify failures without ever formatting exception text or its URL."""
    if type(exc).__name__ == 'InvalidResume':
        return 'subscription changed during HTTP Range resumption'
    if isinstance(exc, HTTPError):
        return f'HTTP {exc.code}'
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return error_kind(reason)
        # Deliberately avoid rendering URLError.reason strings: often hostnames/URLs.
        return 'URL/network error'
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return 'timeout'
    if isinstance(exc, socket.gaierror):
        return 'DNS lookup error'
    if isinstance(exc, ssl.SSLError):
        return 'TLS/SSL error'
    if isinstance(exc, ConnectionRefusedError):
        return 'connection refused'
    if isinstance(exc, ConnectionResetError):
        return 'connection reset'
    if isinstance(exc, PermissionError):
        return 'permission denied'
    if isinstance(exc, FileNotFoundError):
        return 'file not found'
    if isinstance(exc, sqlite3.Error):
        return 'SQLite ' + type(exc).__name__
    if isinstance(exc, CycleFailure):
        return exc.reason
    if isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], str):
        if exc.args[0] in ('No supported nodes in downloaded subscription; kept previous cache',
                           'No supported nodes in subscription; kept previous cache'):
            return 'zero supported nodes in subscription'
    if isinstance(exc, RuntimeError):
        # The only safe messages we display verbatim are authored constants.
        whitelisted = {
            'Another monitoring cycle is already running',
            'Subscription unavailable and no successful cached subscription exists',
            'sing-box stopped during startup',
            'sing-box failed to bind local test listeners',
            'sing-box --version unsuccessful',
            'Cannot launch sing-box executable',
        }
        if exc.args and isinstance(exc.args[0], str) and exc.args[0] in whitelisted:
            return exc.args[0]
    return type(exc).__name__


class CycleFailure(RuntimeError):
    def __init__(self, phase: str, reason: str, incident_id: str):
        self.phase = phase
        self.reason = reason
        self.incident_id = incident_id
        super().__init__(f'{phase}: {reason} (incident {incident_id})')


def record_failure(exc: BaseException, phase: str | None = None, *, warning=False) -> CycleFailure:
    if isinstance(exc, CycleFailure):
        return exc
    phase = phase or CURRENT_STAGE.get()
    reason = error_kind(exc)
    incident = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3)
    # Frames include local Python filename/function/line, but never source snippets or
    # exception values (which can leak credential-bearing URLs and node parameters).
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    where = ' > '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in frames[-10:]) or '(no stack)'
    logger().log(logging.WARNING if warning else logging.ERROR,
                 'incident=%s phase=%s kind=%s stack=%s', incident, phase, reason, where)
    return CycleFailure(phase, reason, incident)


def event(name: str, **numbers_or_labels: object) -> None:
    """Caller must pass only safe static labels/numeric counts, never node details."""
    extras = ' '.join(f'{key}={value}' for key, value in numbers_or_labels.items())
    logger().info('%s %s', name, extras)


def safe_count_summary(errors: list[str]) -> str:
    from collections import Counter
    counts = Counter(errors)
    return ', '.join(f'{key}:{count}' for key, count in counts.most_common(6)) or 'none'
