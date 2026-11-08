"""Local, private configuration. No secrets are logged."""
from __future__ import annotations
import json
import os
import ntpath
import re
import sys
from pathlib import Path
from dataclasses import dataclass, asdict, field
from urllib.parse import urlsplit


def app_dir() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    p = base / 'IranProxyMonitor'
    p.mkdir(parents=True, exist_ok=True)
    return p

DATA_DIR = app_dir()


def is_local_subscription(value: str) -> bool:
    r"""Accept absolute filesystem paths, including Windows D:\... and UNC paths.

    Require an absolute path to avoid accidentally reading files from an
    unexpected working directory (GUI, PowerShell, Task Scheduler).
    """
    return bool(value) and (Path(value).is_absolute() or ntpath.isabs(value))


def split_subscription_sources(value: str) -> list[str]:
    """Newlines and commas separate subscription sources; preserve their order.

    Commas embedded in a URL/path are separators by design. Password-bearing
    source strings must never be printed or put in diagnostic events.
    """
    result = []
    seen = set()
    for raw in re.split(r'[,\r\n]+', value or ''):
        item = raw.strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    if len(result) > 40:
        raise ValueError('At most 40 subscription sources may be combined.')
    return result


@dataclass
class Settings:
    # Historical key retained to migrate earlier settings.json files automatically.
    # Value can now be an absolute local path as well as an HTTP(S) or file URL.
    subscription_url: str = ''
    singbox_path: str = ''
    refresh_minutes: int = 120
    client_listen_port: int = 20808
    client_mode: str = 'manual'
    probes_per_cycle: int = 320  # used only when scan_all=False
    scan_all: bool = True
    use_cached_subscription_for_tests: bool = False
    probe_batch: int = 128
    probe_processes: int = 4  # four parallel isolated sing-box processes
    probe_workers: int = 128
    probe_timeout: float = 2.5
    probe_endpoint_attempts: int = 1  # fast scan: one HTTPS destination; optional 2/3 to rescue
    latency_cutoff_ms: int = 1000  # zero disables cutoff
    speed_workers: int = 5
    speed_candidates: int = 250
    prelim_kib: int = 192
    confirm_min_kib: int = 8192
    confirm_max_kib: int = 32768
    speed_seconds: float = 3.5  # preliminary only
    confirm_seconds: float = 12.0  # longer observation catches sparse bursts
    confirm_min_seconds: float = 8.0  # four-second spikes cannot qualify
    exploratory_speed_pct: int = 30  # candidates sampled without ping cutoff
    budget_mib: float = 256.0
    shortlist_size: int = 10
    baseline_kib: int = 64
    subscription_timeout_seconds: int = 300  # inactivity timeout for each subscription read
    subscription_proxy_mode: str = 'system'  # system/direct/manual-http/manual-socks5
    subscription_proxy_host: str = '127.0.0.1'
    subscription_proxy_port: int = 3067
    subscription_proxy_username: str = ''  # never persisted
    subscription_proxy_password: str = ''  # never persisted
    connectivity_urls: list[str] = field(default_factory=lambda: [
        'https://www.gstatic.com/generate_204',
        'https://www.cloudflare.com/cdn-cgi/trace',
        'https://www.google.com/generate_204',
    ])
    download_urls: list[str] = field(default_factory=lambda: [
        'https://speed.cloudflare.com/__down?bytes={bytes}',
        'https://speed.hetzner.de/100MB.bin',
    ])

    def validate(self):
        for source in split_subscription_sources(self.subscription_url):
            if not (source.lower().startswith(('https://', 'http://', 'file://'))
                    or is_local_subscription(source)):
                raise ValueError('Each subscription must be an HTTP(S) URL or an absolute local file path.')
            if source.lower().startswith('file://') and not urlsplit(source).path:
                raise ValueError('file:// subscription requires a file path.')
        for k, a, b in [('refresh_minutes',5,10080), ('client_listen_port',1024,65535), ('probes_per_cycle',1,50000),
                         ('subscription_timeout_seconds',10,600), ('probe_batch',1,256), ('probe_processes',1,4), ('probe_workers',1,256), ('probe_endpoint_attempts',1,3), ('exploratory_speed_pct',0,75),
                         ('speed_workers',1,10), ('latency_cutoff_ms',0,60000),
                         ('speed_candidates',1,1000), ('prelim_kib',16,8192),
                         ('confirm_min_kib',32,65536), ('confirm_max_kib',32,65536),
                         ('shortlist_size',1,30), ('baseline_kib',0,4096)]:
            value = getattr(self, k)
            if not isinstance(value, int) or not a <= value <= b:
                raise ValueError(f'{k} must be between {a} and {b}')
        if type(self.scan_all) is not bool or type(self.use_cached_subscription_for_tests) is not bool:
            raise ValueError('Invalid scan_all or use_cached_subscription_for_tests')
        if self.client_mode not in ('manual','system','tun'):
            raise ValueError('Invalid connection mode')
        from .feed_proxy import validate_proxy_settings
        validate_proxy_settings(self.subscription_proxy_mode, self.subscription_proxy_host,
                                self.subscription_proxy_port, self.subscription_proxy_username,
                                self.subscription_proxy_password)
        if self.confirm_min_kib > self.confirm_max_kib:
            raise ValueError('Confirmation minimum exceeds maximum')
        if not 0.5 <= self.probe_timeout <= 30 or not 1 <= self.speed_seconds <= 30:
            raise ValueError('Invalid preliminary timeout')
        if not 3 <= self.confirm_seconds <= 45 or not 2 <= self.confirm_min_seconds <= self.confirm_seconds:
            raise ValueError('Invalid confirmation duration')
        if not 1 <= self.budget_mib <= 2048:
            raise ValueError('Bandwidth budget must be 1–2048 MiB')
        for item in self.connectivity_urls + self.download_urls:
            if not item.startswith('https://'):
                raise ValueError('Test endpoints must use HTTPS')

    @classmethod
    def load(cls):
        p = DATA_DIR / 'settings.json'
        if not p.exists():
            settings = cls()
            if getattr(sys, 'frozen', False):
                candidate = Path(sys.executable).resolve().parent / 'bin' / 'sing-box.exe'
                if candidate.is_file():
                    settings.singbox_path = str(candidate)
            return settings
        try:
            values = json.loads(p.read_text('utf-8'))
            # v1.0.6 used 1–8 MiB confirmations. Upgrade uncustomized caps,
            # otherwise short bursts would still dominate on existing installs.
            # An explicit custom choice outside those defaults is preserved.
            if 'probe_endpoint_attempts' not in values:
                if values.get('confirm_min_kib') == 1024:
                    values['confirm_min_kib'] = 8192
                if values.get('confirm_max_kib') == 8192:
                    values['confirm_max_kib'] = 32768
            # Upgrade only the exact v1.0.13 9/4 (Fast) or 10/4 (Default) presets.
            if (values.get('confirm_seconds'),values.get('confirm_min_seconds')) in ((9.0,4.0),(10.0,4.0)):
                values['confirm_seconds'] = 12.0
                values['confirm_min_seconds'] = 8.0
            # Upgrade the exact old fast-preset defaults; never alter a custom
            # batch/worker configuration. The user's requested candidate cap is 250.
            old_speed_default = values.get('speed_candidates') == 100
            if old_speed_default:
                values['speed_candidates'] = 250
                if values.get('budget_mib') == 128.0:
                    values['budget_mib'] = 256.0
            if (values.get('probe_batch'), values.get('probe_workers'), values.get('probe_processes')) == (96,96,2):
                values.update(probe_batch=128, probe_workers=128, probe_processes=4)
            known = cls.__dataclass_fields__
            settings = cls(**{k:v for k,v in values.items() if k in known})
            # Credentials are per-session and never read from legacy plaintext fields.
            settings.subscription_proxy_username = ''
            settings.subscription_proxy_password = ''
            if getattr(sys, 'frozen', False):
                candidate = Path(sys.executable).resolve().parent / 'bin' / 'sing-box.exe'
                if candidate.is_file():
                    settings.singbox_path = str(candidate)
            settings.validate()
            return settings
        except (OSError, ValueError, TypeError):
            settings = cls()
            if getattr(sys, 'frozen', False):
                candidate = Path(sys.executable).resolve().parent / 'bin' / 'sing-box.exe'
                if candidate.is_file():
                    settings.singbox_path = str(candidate)
            return settings

    def save(self):
        self.validate()
        p = DATA_DIR / 'settings.json'
        temp = p.with_suffix('.json.tmp')
        values = asdict(self)
        # Never save proxy passwords/usernames in readable settings.json.
        values.pop('subscription_proxy_username', None)
        values.pop('subscription_proxy_password', None)
        temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), 'utf-8')
        try: os.chmod(temp, 0o600)
        except OSError: pass
        temp.replace(p)
