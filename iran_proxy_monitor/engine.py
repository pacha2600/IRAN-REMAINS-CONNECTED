"""Actual HTTP CONNECT traffic through sing-box, isolated by inbound port.
No system-proxy changes. Each probe/download routes through exactly one tagged outbound.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
import socket
import ssl
from urllib.parse import urlsplit
import subprocess
import tempfile
import threading
import time
import sys
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import URLError, HTTPError

from .models import Node, Probe, Speed
from .settings import DATA_DIR, Settings
from .diagnostics import event, logger, record_failure, error_kind, safe_count_summary


def find_singbox(path: str = '') -> str:
    paths=[path, str(Path(sys.executable).resolve().parent / 'bin' / ('sing-box.exe' if os.name=='nt' else 'sing-box')),
           str(Path(__file__).resolve().parent.parent / 'bin' / ('sing-box.exe' if os.name=='nt' else 'sing-box')),
           str(DATA_DIR / 'bin' / ('sing-box.exe' if os.name=='nt' else 'sing-box')),
           shutil.which('sing-box') or '']
    for p in paths:
        if p and Path(p).is_file():return str(Path(p).resolve())
    raise FileNotFoundError('sing-box core not found. Run install.ps1 or configure the core path.')


def available_ports(n):
    # Small chance of a port race between release and subprocess binding; retry startup on failure.
    reservations=[]
    try:
        for _ in range(n):
            sock=socket.socket();sock.bind(('127.0.0.1',0));reservations.append(sock)
        return [s.getsockname()[1] for s in reservations]
    finally:
        for s in reservations:s.close()


def batch_config(nodes: list[Node], ports: list[int]) -> dict:
    assert len(nodes)==len(ports) and nodes
    ins=[{'type':'mixed','tag':f'in{i}','listen':'127.0.0.1','listen_port':port}
         for i,port in enumerate(ports)]
    outs=[n.labeled_outbound(f'node{i}') for i,n in enumerate(nodes)]
    # final=block ensures a missing rule does not accidentally make a direct connection.
    outs.append({'type':'block','tag':'block'})
    rules=[{'inbound':[f'in{i}'],'action':'route','outbound':f'node{i}'}
           for i in range(len(nodes))]
    return {'log':{'level':'error','timestamp':False},
            'dns':{'servers':[{'type':'local','tag':'local'}],'final':'local'},
            'inbounds':ins,'outbounds':outs,
            'route':{'rules':rules,'final':'block','default_domain_resolver':'local'}}


def _temporary_json(obj):
    (DATA_DIR/'tmp').mkdir(exist_ok=True)
    fd,path=tempfile.mkstemp(suffix='.json',prefix='core-',dir=DATA_DIR/'tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,ensure_ascii=False)
        try:os.chmod(path,0o600)
        except OSError:pass
        return path
    except Exception:
        os.unlink(path);raise


def classify_core_stderr(raw: bytes) -> str:
    """Map core stderr to a fixed category, never record raw credentials/configs."""
    msg = raw[:24000].decode('utf-8', 'replace').lower()
    kinds = (
        ('unknown outbound type', 'unsupported-outbound-type'),
        ('unknown inbound type', 'unsupported-inbound-type'),
        ('unknown transport type', 'unsupported-transport-type'),
        ('unknown field', 'unknown-config-field'),
        ('unknown server type', 'unknown-dns-server-type'),
        ('missing required', 'missing-required-value'),
        ('invalid field', 'invalid-config-field'),
        ('invalid character', 'invalid-json'),
        ('failed to parse', 'parse-failure'),
        ('deprecated', 'deprecated-field'),
        ('no such file', 'missing-file'),
        ('permission denied', 'permission-denied'),
        ('invalid', 'invalid-config'),
    )
    return next((category for needle, category in kinds if needle in msg), 'core-config-rejected')


def check_core(binary:str, config:dict, timeout=15, details=False):
    path=_temporary_json(config)
    try:
        command=[binary,'check','-c',path]
        p=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                         timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        reason=classify_core_stderr(p.stderr) if p.returncode else ''
        if p.returncode != 0:
            # Include only fixed error categories; stderr may reveal passwords.
            event('core-config-check-failed', kind=reason,
                  return_code=p.returncode, node_count=sum(x.get('type') not in ('block','selector') for x in config.get('outbounds',[])))
        return (p.returncode==0,reason) if details else p.returncode==0
    except (OSError,subprocess.TimeoutExpired) as exc:
        reason=error_kind(exc)
        event('core-config-check-exception', kind=reason)
        return (False,reason) if details else False
    finally:
        Path(path).unlink(missing_ok=True)


def endpoint_order(urls, key):
    if not urls:return []
    i=int(key[:8],16)%len(urls)
    return urls[i:]+urls[:i]


def strict_https_probe(url: str, local_port: int, deadline_seconds: float,
                       cancel: threading.Event | None = None,
                       measurements: dict | None = None) -> tuple[int, float, float]:
    """HTTPS response-header probe through one local sing-box HTTP CONNECT inlet.

    Unlike urllib's per-operation timeout, all TCP/CONNECT/TLS/request/header
    phases consume one wall-clock budget. This does not perform a direct
    origin-server connection; DNS of the origin happens beyond CONNECT.
    Return 0 response-body bytes and HTTPS response-header latency.
    """
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('HTTPS probe URL with a plain hostname is required')
    server=parts.hostname; origin_port=parts.port or 443
    address=f'[{server}]:{origin_port}' if ':' in server else f'{server}:{origin_port}'
    path=parts.path or '/'
    if parts.query: path+='?'+parts.query
    host_header=server if origin_port==443 else address
    expiry=time.monotonic()+deadline_seconds
    started=time.monotonic()
    def remaining():
        if cancel is not None and cancel.is_set():raise TimeoutError('cancelled')
        left=expiry-time.monotonic()
        if left <= 0:raise TimeoutError('HTTPS probe deadline exceeded')
        return left
    def send(sock,data,origin=False):
        sock.settimeout(remaining());sock.sendall(data)
        if origin and measurements is not None:
            measurements['http_sent_bytes']=measurements.get('http_sent_bytes',0)+len(data)
    def read_headers(sock,limit=32768,origin=False):
        collected=bytearray()
        while b'\r\n\r\n' not in collected:
            sock.settimeout(remaining())
            block=sock.recv(min(2048,limit-len(collected)))
            if not block:raise ConnectionError('Connection closed before HTTPS headers')
            collected.extend(block)
            if origin and measurements is not None:
                measurements['http_received_bytes']=measurements.get('http_received_bytes',0)+len(block)
            if len(collected)>=limit and b'\r\n\r\n' not in collected:
                raise ValueError('Oversized HTTPS headers')
        text=bytes(collected).split(b'\r\n',1)[0].split(b' ')
        if len(text)<2 or not text[0].startswith(b'HTTP/') or not text[1].isdigit():
            raise ValueError('Invalid HTTP status line')
        return int(text[1])
    with socket.create_connection(('127.0.0.1',local_port),timeout=remaining()) as sock:
        send(sock, f'CONNECT {address} HTTP/1.1\r\nHost: {address}\r\n'
                   f'Proxy-Connection: keep-alive\r\n\r\n'.encode('ascii'),origin=True)
        if read_headers(sock,origin=True)!=200:
            raise ConnectionError('HTTP CONNECT tunnel refused')
        # Complete TLS handshake inside the same wall-clock budget. Certificate
        # and hostname verification are mandatory to avoid false positives.
        context=ssl.create_default_context()
        sock.settimeout(remaining())
        with context.wrap_socket(sock,server_hostname=server,do_handshake_on_connect=False) as tls:
            tls.settimeout(remaining());tls.do_handshake()
            req=(f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\n'
                 'User-Agent: IranProxyMonitor/1.0.10\r\n'
                 'Accept-Encoding: identity\r\nRange: bytes=0-1023\r\n'
                 'Connection: close\r\n\r\n')
            send(tls,req.encode('ascii'),origin=True)
            status=read_headers(tls,origin=True)
            if status not in (200,204,206):raise ValueError('Unacceptable HTTPS response')
    elapsed=max(.0001,time.monotonic()-started)
    return 0,elapsed,elapsed*1000.0


def http_get(url: str, local_port: int | None, max_bytes: int, max_seconds: float,
             cancel:threading.Event | None = None, measurements:dict | None=None,
             strict_probe:bool=False) -> tuple[int, float, float]:
    if strict_probe and local_port is not None:
        return strict_https_probe(url, local_port, max_seconds, cancel, measurements)
    # All HTTPS proxy requests are CONNECT hostnames (remote resolution); no DNS-only false positives.
    proxy=f'http://127.0.0.1:{local_port}' if local_port is not None else None
    handler=ProxyHandler({'https':proxy,'http':proxy} if proxy else {})
    opener=build_opener(handler)
    request=Request(url,headers={'User-Agent':'IranProxyMonitor/1.0','Accept-Encoding':'identity',
                                  'Cache-Control':'no-cache','Range':f'bytes=0-{max(0,max_bytes-1)}'})
    start=time.monotonic()
    # urllib's timeout is per blocking socket operation, NOT a complete-request
    # deadline. Limit each idle read too, while checking a monotonic wall clock.
    per_socket_timeout=min(max_seconds,2.5)
    with opener.open(request, timeout=per_socket_timeout) as response:
        headers_at=time.monotonic()
        if response.status not in (200,204,206):raise ValueError('bad response status')
        content_type=getattr(response,'headers',{}).get('Content-Type','')
        if max_bytes>=16384 and 'text/html' in content_type.lower():
            raise ValueError('unexpected HTML download response')
        n=0;last_chunk=headers_at;first_chunk=None;longest_gap=0.0;stalled=False
        activity_buckets={}
        deadline=start+max_seconds
        while n < max_bytes and time.monotonic() < deadline:
            if cancel and cancel.is_set():break
            try:
                reader=getattr(response,'read1',None) or response.read
                block=reader(min(16384,max_bytes-n))
            except (TimeoutError, socket.timeout, ConnectionResetError, BrokenPipeError):
                if n < 4096:raise
                stalled=True
                break
            now=time.monotonic()
            if not block:break
            longest_gap=max(longest_gap,now-last_chunk)
            if first_chunk is None:first_chunk=now
            last_chunk=now
            n+=len(block)
            bucket=int(now-start)
            activity_buckets[bucket]=activity_buckets.get(bucket,0)+len(block)
            if measurements is not None:measurements['bytes_received']=n
        elapsed=max(0.0001,time.monotonic()-start)  # INCLUDE TTFB / TLS / stalls
        latency_ms=(headers_at-start)*1000
        if measurements is not None:
            longest_gap=max(longest_gap,time.monotonic()-last_chunk)
            measurements.update(time_to_first_byte_ms=latency_ms,
                                longest_gap_ms=longest_gap*1000,stalled=stalled,
                                active_span_seconds=(last_chunk-first_chunk) if first_chunk is not None else 0.0,
                                active_seconds=sum(1 for count in activity_buckets.values() if count>=1024),
                                activity_buckets=activity_buckets)
        return n,elapsed,latency_ms


def probe_one(node:Node, port:int, urls:list[str], timeout:float,
              cancel:threading.Event | None=None, attempts:int=1) -> Probe:
    failed=[]; sent=0; received=0
    for url in endpoint_order(urls,node.id)[:attempts]:
        if cancel and cancel.is_set():
            return Probe(node.id,False,error='cancelled',
                         http_sent_bytes=sent,http_received_bytes=received)
        details={}
        try:
            n,_,ms=http_get(url,port,1024,timeout,cancel,strict_probe=True,measurements=details)
            return Probe(node.id,True,round(ms,1),endpoint=url,bytes_received=n,
                         http_sent_bytes=sent+details.get('http_sent_bytes',0),
                         http_received_bytes=received+details.get('http_received_bytes',0))
        except (OSError,ValueError,URLError,HTTPError,TimeoutError) as e:
            failed.append(type(e).__name__)
        finally:
            sent+=details.get('http_sent_bytes',0)
            received+=details.get('http_received_bytes',0)
    return Probe(node.id,False,error='all endpoints failed: '+','.join(failed[:3]),
                 http_sent_bytes=sent,http_received_bytes=received)




def flow_profile(activity_buckets:dict[int,int],elapsed:float,bytes_received:int) -> dict:
    """Compute a *conservative*, burst-resistant floor for sustained traffic.

    The buckets are received HTTP response bytes by second, measured from the
    very start of connection establishment (so TLS/TTFB silence counts).
    Include zero-traffic seconds. Two-second sliding windows smooth harmless
    one-second scheduling jitter while the active ratio catches every-other-
    second bursts that a two-second average could otherwise conceal.

    Results are estimates for THIS test host, not guaranteed VPN throughput.
    """
    full_seconds=max(0,int(elapsed))
    if full_seconds < 2 or bytes_received <= 0:
        return {'floor_mbps':0.0,'active_ratio':0.0,'floor_fraction':0.0,
                'longest_quiet_seconds':float(full_seconds)}
    bins=[max(0,int(activity_buckets.get(i,0))) for i in range(full_seconds)]
    avg_bytes_per_second=bytes_received/max(.001,elapsed)
    active_threshold=max(256.0,0.15*avg_bytes_per_second)
    active_ratio=sum(b>=active_threshold for b in bins)/len(bins)
    quiet=0;longest=0
    for b in bins:
        if b<active_threshold:quiet+=1;longest=max(longest,quiet)
        else:quiet=0
    pairs=sorted((bins[i]+bins[i+1])/2.0 for i in range(len(bins)-1))
    # 25th percentile: long barren intervals push this toward zero, rather
    # than allowing the fastest one-second burst to dominate the mean.
    floor_bps=pairs[int((len(pairs)-1)*.25)]
    return {'floor_mbps':round(floor_bps*8/1_000_000,4),
            'active_ratio':round(active_ratio,4),
            'floor_fraction':round(min(1.0,floor_bps/max(1.0,avg_bytes_per_second)),4),
            'longest_quiet_seconds':float(longest)}

def _measure_download(node,port,endpoints,amount,duration,cancel,min_seconds=0.0):
    """Per-node cumulative body cap across ALL endpoint attempts.

    Even failed attempts count towards the download budget. A short confirmation
    can be shown but is never verified sustained throughput.
    """
    errors=[];spent=0
    for template in endpoint_order(endpoints,node.id):
        if cancel and cancel.is_set():return Speed(node.id,bytes_received=spent,error='cancelled')
        remaining=amount-spent
        if remaining < (16384 if min_seconds else 4096):break
        details={};counted=False
        try:
            url=template.replace('{bytes}',str(remaining))
            n,elapsed,_=http_get(url,port,remaining,duration,cancel,measurements=details)
            spent+=n;counted=True
            if n < (16384 if min_seconds else 4096):
                raise ValueError('response body too short')
            # Account for empty seconds and high burst-to-average ratios.
            active_span=details.get('active_span_seconds',0.0)
            buckets=details.get('activity_buckets')
            profile=flow_profile(buckets,elapsed,n) if buckets is not None else None
            if profile is not None:
                verified=bool(min_seconds and elapsed>=min_seconds and
                    active_span>=min(2.0,min_seconds*.5) and
                    profile['active_ratio']>=0.75 and
                    profile['floor_fraction']>=0.50 and
                    profile['longest_quiet_seconds']<=1 and
                    details.get('longest_gap_ms',0.0)<=2500.0 and
                    not details.get('stalled',False))
            else:
                # Only older mocked test paths omit activity buckets; actual
                # download streams always provide the flow profile.
                active_seconds=details.get('active_seconds')
                minimum_active_buckets=max(3,int(elapsed*.55+.999))
                verified=bool(min_seconds and elapsed>=min_seconds and
                    active_span>=min(2.0,min_seconds*.5) and
                    (active_seconds is None or active_seconds>=minimum_active_buckets) and
                    not details.get('stalled',False))
            return Speed(node.id,round(n*8/elapsed/1e6,4),spent,round(elapsed,3),True,
                         endpoint=template,verified=verified,
                         stalled=details.get('stalled',False),
                         time_to_first_byte_ms=details.get('time_to_first_byte_ms',0.0),
                         flow_mbps=profile['floor_mbps'] if profile else None,
                         flow_active_ratio=profile['active_ratio'] if profile else None,
                         max_idle_seconds=profile['longest_quiet_seconds'] if profile else 0.0)
        except (OSError,ValueError,URLError,HTTPError,TimeoutError) as e:
            if not counted:spent+=details.get('bytes_received',0)
            errors.append(type(e).__name__)
    return Speed(node.id,bytes_received=spent,
                 error=('confirmation' if min_seconds else 'preliminary')+
                       ' endpoints failed: '+','.join(errors[:3]))


def speed_one(node:Node, port:int, endpoints:list[str], amount:int,
              duration:float, cancel:threading.Event | None=None) -> Speed:
    """Short preliminary test: detects data transfer, never establishes sustained rate."""
    return _measure_download(node,port,endpoints,amount,duration,cancel)


def speed_confirm_one(node:Node, port:int, endpoints:list[str], amount:int,
                      duration:float, cancel:threading.Event | None=None,
                      min_seconds:float=8.0) -> Speed:
    """Long confirmation: reject fast bursts as verified measurements."""
    return _measure_download(node,port,endpoints,amount,duration,cancel,min_seconds)


class CoreSession:
    def __init__(self,binary,nodes,ports):
        self.binary=binary;self.nodes=nodes;self.ports=ports
        self.process=None;self.config_file=None

    def __enter__(self):
        config=batch_config(self.nodes,self.ports)
        self.config_file=_temporary_json(config)
        kwargs={'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL}
        if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
        try:
            self.process=subprocess.Popen([self.binary,'run','-c',self.config_file],**kwargs)
            deadline=time.monotonic()+7
            pending=set(self.ports)
            while time.monotonic()<deadline and pending:
                if self.process.poll() is not None:
                    event('core-early-exit', exit_code=self.process.returncode, nodes=len(self.nodes))
                    raise RuntimeError('sing-box stopped during startup')
                for port in list(pending):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.03):pending.discard(port)
                    except OSError:pass
                if pending:time.sleep(.09)
            if pending:
                event('core-listener-timeout', unavailable_ports=len(pending), nodes=len(self.nodes))
                raise RuntimeError('sing-box failed to bind local test listeners')
            return self
        except Exception:
            self.__exit__(None,None,None)
            raise

    def __exit__(self,*args):
        if self.process:
            try:
                self.process.terminate();self.process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired):
                try:self.process.kill();self.process.wait(timeout=2)
                except (OSError,subprocess.TimeoutExpired):pass
        if self.config_file:Path(self.config_file).unlink(missing_ok=True)


class SingboxEngine:
    def __init__(self, settings:Settings, cancel:threading.Event):
        self.settings=settings;self.cancel=cancel
        self.binary=find_singbox(settings.singbox_path)
        try:
            p=subprocess.run([self.binary,'version'],capture_output=True,timeout=8,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if p.returncode!=0:raise RuntimeError('sing-box --version unsuccessful')
            lines=p.stdout.decode(errors='replace').splitlines()
            self.version=lines[0] if lines else 'sing-box' 
        except OSError as e:raise RuntimeError('Cannot launch sing-box executable') from e
        self.baseline_data_bytes=0
        # Cache only definite, single-node configuration rejections. This saves
        # repeated bisection during later cycles without blacklisting a node for
        # network, timeout, or core-startup problems. The cache is invalidated
        # automatically when the sing-box version changes.
        self._cache_lock=threading.Lock()
        self._cache_path=DATA_DIR/'core-compatibility.json'
        self._cache_rejected={}
        self._cache_created=time.time()
        try:
            cache=json.loads(self._cache_path.read_text(encoding='utf-8'))
            created=cache.get('created_at',0)
            # Even core-check rejections are revisited every six hours. Changing
            # the core version invalidates entries immediately.
            if (cache.get('core_version')==self.version and
                isinstance(created,(int,float)) and 0 <= time.time()-created < 6*3600 and
                isinstance(cache.get('rejected'),dict)):
                self._cache_created=created
                self._cache_rejected={key:value for key,value in cache['rejected'].items()
                                      if isinstance(key,str) and isinstance(value,str)}
        except (OSError,ValueError,TypeError):pass

    def save_core_cache(self):
        if not hasattr(self,'_cache_lock'):return
        with self._cache_lock:
            # No original node names, raw subscription addresses, or credentials.
            payload={'core_version':self.version,'created_at':getattr(self,'_cache_created',time.time()),
                     'rejected':dict(self._cache_rejected)}
        dest=self._cache_path
        temp=dest.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps(payload,sort_keys=True),encoding='utf-8')
            os.replace(temp,dest)
        except OSError:
            temp.unlink(missing_ok=True)

    def groups(self,nodes):
        """Bisect invalid configs, so one malformed node never poisons a full group."""
        if self.cancel.is_set():return [],[(n,'cancelled') for n in nodes]
        if not nodes:return [],[]
        known = getattr(self,'_cache_rejected',{})
        cached=[(n,'core rejected: '+known[n.id]) for n in nodes if n.id in known]
        nodes=[n for n in nodes if n.id not in known]
        if not nodes:return [],cached
        ports=available_ports(len(nodes))
        if len(nodes)==1:
            ok, reason=check_core(self.binary,batch_config(nodes,ports),details=True)
            if ok:return [(nodes,ports)],cached
            event('core-check-rejected-node', protocol=nodes[0].protocol, kind=reason)
            # A timed out or missing core is not a definite unsupported config.
            if reason not in ('timeout','TimeoutExpired','FileNotFoundError',
                              'PermissionError','OSError','missing-file','permission-denied'):
                if hasattr(self,'_cache_lock'):
                    with self._cache_lock:self._cache_rejected[nodes[0].id]=reason
            return [],cached+[(nodes[0],'core rejected: '+reason)]
        if check_core(self.binary,batch_config(nodes,ports)):
            return [(nodes,ports)],cached
        # Wide groups with bad configs can cause extremely slow recursive
        # sing-box checks. Jump directly to 32-node groups when 128 fails;
        # this preserves testing of EVERY candidate while avoiding failed
        # intermediate configurations at 64 nodes.
        if len(nodes)>64:
            pieces=[nodes[i:i+32] for i in range(0,len(nodes),32)]
        else:
            middle=len(nodes)//2
            pieces=[nodes[:middle],nodes[middle:]]
        good=[];rejected=list(cached)
        for piece in pieces:
            a,b=self.groups(piece);good.extend(a);rejected.extend(b)
        return good,rejected

    def _probe_group(self, group, ports, results, on_progress):
        """Recover from sing-box runtime startup failure by splitting the group."""
        if self.cancel.is_set():return
        try:
            with CoreSession(self.binary,group,ports):
                with ThreadPoolExecutor(max_workers=min(self.settings.probe_workers,len(group))) as pool:
                    jobs={pool.submit(probe_one,n,p,self.settings.connectivity_urls,
                                      self.settings.probe_timeout,self.cancel,
                                      self.settings.probe_endpoint_attempts):n
                          for n,p in zip(group,ports)}
                    for f in as_completed(jobs):
                        n=jobs[f]
                        try:results[n.id]=f.result()
                        except Exception:results[n.id]=Probe(n.id,False,error='probe exception')
                        on_progress({'event':'probe-result','node_id':n.id,'probe':results[n.id]})
        except (OSError,RuntimeError) as exc:
            record_failure(exc,'sing-box-batch-startup',warning=True)
            if len(group)>1 and not self.cancel.is_set():
                middle=len(group)//2
                event('core-startup-recover-split', group_size=len(group))
                for sub in (group[:middle],group[middle:]):
                    self._probe_group(sub,available_ports(len(sub)),results,on_progress)
            else:
                for n in group:
                    results[n.id]=Probe(n.id,False,error='core runtime startup failed')
                    on_progress({'event':'probe-result','node_id':n.id,'probe':results[n.id]})

    def _connectivity_batch(self,batch,on_progress):
        started=time.monotonic()
        results={}
        if self.cancel.is_set():return results
        groups,bad=self.groups(batch)
        for n,reason in bad:
            results[n.id]=Probe(n.id,False,error=reason)
            on_progress({'event':'probe-result','node_id':n.id,'probe':results[n.id]})
        for group,ports in groups:
            if self.cancel.is_set():break
            self._probe_group(group,ports,results,on_progress)
        event('connectivity-batch', size=len(batch),ok=sum(p.ok for p in results.values()),
              elapsed_seconds=round(time.monotonic()-started,2),
              problems=safe_count_summary([p.error.split(':')[0] for p in results.values() if not p.ok]))
        return results

    def connectivity(self,nodes:list[Node], on_progress=lambda d:None):
        """Overlap core startups and HTTPS probes across independent port groups.

        Worker count applies *per group*; the UI shows group parallelism as a
        distinct setting so users can trade speed against resource pressure.
        """
        results={};batch_size=self.settings.probe_batch
        batches=[nodes[i:i+batch_size] for i in range(0,len(nodes),batch_size)]
        with ThreadPoolExecutor(max_workers=self.settings.probe_processes) as pool:
            jobs={pool.submit(self._connectivity_batch,batch,on_progress):batch for batch in batches}
            done=0;passed=0
            for f in as_completed(jobs):
                batch=jobs[f]
                try:partial=f.result()
                except Exception as exc:
                    record_failure(exc,'sing-box-batch',warning=True)
                    partial={n.id:Probe(n.id,False,error='unexpected batch error') for n in batch}
                    for n in batch:
                        on_progress({'event':'probe-result','node_id':n.id,'probe':partial[n.id]})
                results.update(partial)
                done+=len(batch)
                passed+=sum(p.ok for p in partial.values())
                on_progress({'phase':'connectivity','done':done,'total':len(nodes),'passed':passed})
        self.save_core_cache()
        return results

    def throughput(self,nodes:list[Node], max_bytes:int, budget_remaining:int,
                   on_progress=lambda d:None, phase='preliminary', sizes=None):
        """Per-node HTTPS measurements; up to speed_workers concurrent downloads.

        Reserve the full transfer cap *before* scheduling, so concurrent workers
        cannot exceed the response-payload budget. Never create a direct fallback.
        """
        results={};spent=0;done=0;reserved=0
        for i in range(0,len(nodes),self.settings.probe_batch):
            if self.cancel.is_set():break
            batch=nodes[i:i+self.settings.probe_batch]
            groups,bad=self.groups(batch)
            for n,reason in bad:
                results[n.id]=Speed(n.id,error=reason);done+=1
                on_progress({'event':'speed-result','node_id':n.id,'speed':results[n.id],
                             'speed_phase':phase})
            for group,ports in groups:
                if self.cancel.is_set():break
                try:
                    with CoreSession(self.binary,group,ports):
                        # Only launch work where the *maximum* body size fits budget.
                        chosen=[]
                        for n,port in zip(group,ports):
                            amount=(sizes or {}).get(n.id,max_bytes)
                            if self.cancel.is_set() or reserved+amount>budget_remaining:break
                            chosen.append((n,port,amount));reserved+=amount
                        with ThreadPoolExecutor(max_workers=self.settings.speed_workers) as pool:
                            if phase=='confirmation':
                                jobs={pool.submit(speed_confirm_one,n,port,self.settings.download_urls,amount,
                                                  self.settings.confirm_seconds,self.cancel,
                                                  self.settings.confirm_min_seconds):n for n,port,amount in chosen}
                            else:
                                jobs={pool.submit(speed_one,n,port,self.settings.download_urls,amount,
                                                  self.settings.speed_seconds,self.cancel):n for n,port,amount in chosen}
                            for f in as_completed(jobs):
                                n=jobs[f]
                                try:res=f.result()
                                except Exception:res=Speed(n.id,error='speed exception')
                                results[n.id]=res;spent+=res.bytes_received;done+=1
                                on_progress({'event':'speed-result','node_id':n.id,'speed':res,
                                             'speed_phase':phase})
                                on_progress({'phase':phase,'done':done,'total':len(nodes),'bytes':spent})
                        # Release unused reservation. Conservatively, a later batch
                        # can still use bytes unconsumed in this one.
                        reserved=spent
                except (OSError,RuntimeError) as exc:
                    record_failure(exc, 'sing-box-speed-startup', warning=True)
                    for n in group:
                        if n.id not in results:
                            results[n.id]=Speed(n.id,error='core failed to start')
                            done+=1
                            on_progress({'event':'speed-result','node_id':n.id,'speed':results[n.id],
                                         'speed_phase':phase})
        return results,spent

    def baseline(self):
        for template in self.settings.download_urls:
            try:
                n,seconds,_=http_get(template.replace('{bytes}',str(self.settings.baseline_kib*1024)),
                                        None,self.settings.baseline_kib*1024,4,self.cancel)
                self.baseline_data_bytes += n
                if n >= 4096:return round(n*8/seconds/1e6,3)
            except (OSError,ValueError,URLError,HTTPError,TimeoutError):pass
        return None
