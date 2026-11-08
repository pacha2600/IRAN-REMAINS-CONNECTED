"""On-demand single-node sing-box client, completely separate from scanner processes.

No automatic connection, no LAN listener, no direct-fallback outbound. Windows
system proxy is reversible; TUN is an explicit, administrator-only action.
"""
from __future__ import annotations

import copy
import secrets
import urllib.request
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from typing import Callable

from .engine import check_core, find_singbox
from .exporter import OUT
from .models import Node
from .settings import DATA_DIR
from .diagnostics import event
from .win_system_proxy import WindowsProxySwitch, is_administrator
from .win_job import WindowsKillJob

MODES = ('manual', 'system', 'tun')
KINDS = ('best-overall', 'best-download-speed', 'best-ping', 'best-reliable')


def connection_warnings(outbound: dict) -> list[str]:
    """High-impact privacy warnings; scanner still accepts source nodes unchanged."""
    notes=[]
    tls=outbound.get('tls')
    if isinstance(tls,dict) and tls.get('insecure') is True:
        notes.append('This node disables TLS certificate verification. A man-in-the-middle could impersonate the proxy server.')
    if outbound.get('type') in ('http','socks') and not (isinstance(tls,dict) and tls.get('enabled')):
        notes.append('This upstream HTTP/SOCKS connection is unencrypted between your device and the proxy server. HTTPS sites remain encrypted end-to-end, but HTTP traffic and metadata may be visible to the proxy or network. Choose a TLS-encrypted node if that is important.')
    return notes



def client_config(outbound: dict, mode: str, port: int, *, api_port: int | None=None, api_secret: str='') -> dict:
    """Single outbound; no selector fallback to direct; loopback-only local entry."""
    if mode not in MODES:
        raise ValueError('Select Manual proxy, Windows system proxy, or device TUN.')
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError('Local proxy port must be 1024–65535.')
    if not isinstance(outbound, dict) or not outbound.get('type') or outbound['type'] in (
        'direct', 'block', 'selector', 'urltest', 'dns', 'tun'):
        raise ValueError('A supported proxy outbound is required.')
    chosen = copy.deepcopy(outbound)
    chosen['tag'] = 'selected'
    inbounds = [{'type':'mixed', 'tag':'client-local', 'listen':'127.0.0.1',
                 'listen_port':port}]
    dns = {'servers':[{'type':'local','tag':'bootstrap'}], 'final':'bootstrap'}
    routing = {'final':'selected','default_domain_resolver':'bootstrap'}
    if mode == 'tun':
        # Windows native DNS interception with strict_route. The DNS used for
        # ordinary target hostnames is DoH *through* the selected proxy; only
        # bootstrap DNS for the proxy SERVER uses the host resolver.
        inbounds.append({'type':'tun','tag':'client-tun',
                         'address':['172.28.99.1/30'], 'auto_route':True,
                         'strict_route':True, 'dns_mode':'hijack'})
        dns = {'servers':[
            {'type':'local','tag':'bootstrap'},
            {'type':'https','tag':'tunnel-dns','server':'1.1.1.1',
             'server_port':443,'detour':'selected'}], 'final':'tunnel-dns'}
        routing['auto_detect_interface'] = True
    config = {'log':{'level':'warn','timestamp':False}, 'dns':dns,
              'inbounds':inbounds,'outbounds':[chosen], 'route':routing}
    if api_port is not None:
        if not (1024 <= api_port <= 65535) or api_port == port or not api_secret:
            raise ValueError('Private traffic API requires a separate port and secret.')
        config['experimental'] = {'clash_api':{
            'external_controller':f'127.0.0.1:{api_port}',
            'secret':api_secret}}
    return config


def saved_shortlist_node(kind: str, export_dir: Path = OUT, rank: int = 1) -> tuple[str, dict]:
    """Use the precise validated selected outbound from the saved category."""
    if kind not in KINDS:
        raise ValueError('Unknown shortlist category')
    path = export_dir / f'{kind}-latest.json'
    if not path.is_file():
        raise FileNotFoundError(f'No {kind} shortlist. Run a completed scan first.')
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Saved shortlist is unexpectedly large')
    if type(rank) is not int or not 1 <= rank <= 30:
        raise ValueError('Shortlist rank must be between 1 and 30')
    cfg = json.loads(path.read_text('utf-8'))
    if not isinstance(cfg, dict) or not isinstance(cfg.get('outbounds'), list):
        raise ValueError('Saved shortlist has no outbounds')
    candidates = [item for item in cfg['outbounds'] if isinstance(item, dict)
                  and item.get('type') not in ('selector','direct','block','urltest')]
    if rank > len(candidates):
        raise ValueError(f'{kind} contains only {len(candidates)} selectable nodes.')
    item = candidates[rank-1]
    return str(item.get('tag') or kind), copy.deepcopy(item)


def _private_port(exclude: int) -> int:
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
        if port == exclude:
            return _private_port(exclude)
        return port


def _api_totals(port: int, secret: str, timeout: float=0.7) -> tuple[int,int]:
    """Clash-compatible snapshot (bytes): upload and download since core startup."""
    request=urllib.request.Request(f'http://127.0.0.1:{port}/connections',
                 headers={'Authorization':'Bearer '+secret})
    # Never route the private controller query through the Windows system proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=timeout) as response:
        payload=response.read(2*1024*1024)
    data=json.loads(payload)
    def counter(*keys):
        for key in keys:
            value=data.get(key)
            if type(value) is int and value >= 0:
                return value
        raise ValueError('Traffic API did not supply a valid cumulative counter')
    return counter('uploadTotal','upload'),counter('downloadTotal','download')


def _port_free(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try: s.bind(('127.0.0.1', port))
        except OSError: raise OSError(f'Local port {port} is already occupied. Change the port or stop the other proxy.') from None


def _listener_ready(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.25):
            return True
    except OSError:
        return False


class ClientManager:
    def __init__(self, proxy_switch: WindowsProxySwitch | None=None):
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._job: WindowsKillJob | None = None
        self._owns_system_proxy=False
        self._config_path: Path | None = None
        self._proxy = proxy_switch if proxy_switch is not None else WindowsProxySwitch()
        self._stop_requested = threading.Event()
        self.mode: str | None = None
        self.node_name: str = ''
        self.port: int | None = None
        self._connecting = False
        self._api_port: int | None = None
        self._api_secret: str = ''
        self._stats_stop = threading.Event()
        self._stats_thread: threading.Thread | None = None
        self._traffic_session_id = 0
        self._traffic = {'up':0,'down':0,'up_bps':0.0,'down_bps':0.0,'available':False}

    @property
    def connecting(self) -> bool:
        with self._lock: return self._connecting

    @property
    def active(self) -> bool:
        with self._lock: return bool(self._process and self._process.poll() is None)

    def traffic(self) -> dict:
        with self._lock:
            return dict(self._traffic)

    def _start_traffic_watcher(self, process, api_port: int, api_secret: str):
        with self._lock:
            self._traffic_session_id += 1
            session_id = self._traffic_session_id
        self._stats_stop.clear()
        def watch():
            previous = None
            while not self._stats_stop.is_set() and process.poll() is None:
                with self._lock:
                    if session_id != self._traffic_session_id:
                        break
                try:
                    up,down = _api_totals(api_port,api_secret)
                    current = time.monotonic()
                    with self._lock:
                        if session_id != self._traffic_session_id:break
                        if previous is None:
                            up_bps=down_bps=0.0
                        else:
                            last_up,last_down,last_at=previous
                            elapsed=max(0.1,current-last_at)
                            up_bps=max(0,up-last_up)/elapsed
                            down_bps=max(0,down-last_down)/elapsed
                        self._traffic={'up':up,'down':down,'up_bps':up_bps,
                                       'down_bps':down_bps,'available':True}
                    previous=(up,down,current)
                except (OSError,ValueError,TimeoutError,KeyError):
                    with self._lock:
                        if session_id != self._traffic_session_id:break
                        self._traffic['available']=False
                        self._traffic['up_bps']=0.0
                        self._traffic['down_bps']=0.0
                    previous=None
                self._stats_stop.wait(1.0)
        self._stats_thread=threading.Thread(target=watch,daemon=True,name='client-traffic')
        self._stats_thread.start()

    def status(self) -> str:
        with self._lock:
            if self._connecting: return 'Connecting…'
            if self._process and self._process.poll() is None:
                return f'CONNECTED: {self.node_name} · {self.mode} · 127.0.0.1:{self.port}'
            return 'Disconnected'

    def start(self, binary: str, outbound: dict, name: str, mode: str,
              port: int=20808, startup_seconds: float=8.0,
              progress: Callable[[str],None] | None=None) -> str:
        with self._lock:
            if self._connecting or self._process is not None:
                raise RuntimeError('Disconnect the current client before switching nodes or modes.')
            self._connecting = True
            self._stop_requested.clear()
        temp: Path | None = None
        process = None
        job = None
        proxy_armed = False
        api_port = None
        api_secret = ''
        try:
            if mode == 'tun':
                if os.name != 'nt':
                    raise RuntimeError('Device-wide TUN in this release is supported only on Windows.')
                if not is_administrator():
                    raise PermissionError('TUN needs administrator rights. Close the app, right-click it, and choose Run as administrator.')
            api_port = _private_port(port)
            api_secret = secrets.token_urlsafe(32)
            cfg = client_config(outbound,mode,port,api_port=api_port,api_secret=api_secret)
            core = find_singbox(binary)
            _port_free(port)
            if progress: progress('Checking selected node configuration…')
            if not check_core(core,cfg):
                raise RuntimeError('sing-box rejected this node or TUN config; choose a different node or core.')
            directory = DATA_DIR / 'client'
            directory.mkdir(parents=True,exist_ok=True)
            # Separate from scanner's tmp configs. Never log these credentials.
            temp = directory / ('client-%d-%d.json' % (os.getpid(),time.time_ns()))
            with temp.open('x',encoding='utf-8') as file:
                json.dump(cfg,file,ensure_ascii=False)
            try: os.chmod(temp,0o600)
            except OSError: pass
            if self._stop_requested.is_set(): raise RuntimeError('Connection cancelled.')
            if progress: progress('Starting sing-box client…')
            process = subprocess.Popen([core,'run','-c',str(temp)],
                       stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            # If Windows crashes or the GUI gets forcibly killed, the OS Job
            # Object terminates the core instead of leaving TUN routes active.
            job = WindowsKillJob(process)
            deadline = time.monotonic()+startup_seconds
            while time.monotonic()<deadline:
                if self._stop_requested.is_set(): raise RuntimeError('Connection cancelled.')
                if process.poll() is not None:
                    raise RuntimeError(f'sing-box exited during client startup (exit code {process.returncode}).')
                if _listener_ready(port):
                    # Wait a moment to catch TUN initialization crashes after
                    # mixed inbound begins accepting connections.
                    time.sleep(.2)
                    if process.poll() is not None:
                        raise RuntimeError(f'sing-box failed during initialization (exit code {process.returncode}).')
                    if mode == 'system':
                        self._proxy.enable(port)
                        proxy_armed = True
                    with self._lock:
                        if self._stop_requested.is_set():raise RuntimeError('Connection cancelled.')
                        self._process=process;self._job=job;self._config_path=temp
                        self._owns_system_proxy=proxy_armed
                        self.mode=mode;self.port=port;self.node_name=name[:125]
                        self._api_port=api_port;self._api_secret=api_secret
                        self._traffic={'up':0,'down':0,'up_bps':0.0,'down_bps':0.0,'available':False}
                    self._start_traffic_watcher(process,api_port,api_secret)
                    event('client-connected',mode=mode,port=port)
                    return f'CONNECTED: {name[:125]} · {mode} · 127.0.0.1:{port}'
                time.sleep(.1)
            raise TimeoutError('Client did not open its loopback listener in time.')
        except Exception:
            if process is not None:
                _terminate(process)
            if job is not None:job.close()
            if proxy_armed:self._proxy.restore()
            if temp:temp.unlink(missing_ok=True)
            raise
        finally:
            with self._lock:self._connecting=False

    def stop(self) -> str:
        self._stop_requested.set()
        with self._lock:
            proc=self._process; temp=self._config_path; job=self._job
            owned=self._owns_system_proxy;self._owns_system_proxy=False
            self._process=None;self._job=None;self._config_path=None
            self.mode=None;self.port=None;self.node_name=''
            self._api_port=None;self._api_secret=''
            self._stats_stop.set()
            self._traffic_session_id += 1
            self._traffic={'up':0,'down':0,'up_bps':0.0,'down_bps':0.0,'available':False}
        if proc is not None: _terminate(proc)
        if job is not None:job.close()
        # Restores only if Windows still uses OUR proxy, not if another app
        # modified it meanwhile. Safe even after a crashed core.
        if owned:self._proxy.restore()
        if temp:temp.unlink(missing_ok=True)
        if proc is not None:event('client-disconnected')
        return 'Disconnected; previous system proxy settings restored if still owned by this app.'

    def reconcile(self) -> bool:
        """Detect unexpectedly exited core, restore system proxy, clear secrets."""
        with self._lock:
            died = self._process is not None and self._process.poll() is not None
        if died:
            self.stop()
        return bool(died)


def _terminate(proc: subprocess.Popen):
    if proc.poll() is not None:return
    try:
        proc.terminate()
        try:proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill();proc.wait(timeout=3)
    except (OSError,subprocess.TimeoutExpired):
        pass
