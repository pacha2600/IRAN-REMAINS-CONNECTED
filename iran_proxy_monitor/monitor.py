"""Orchestrates bandwidth-aware discovery, real HTTPS transfer tests, and exports."""
from __future__ import annotations
import json
import hashlib
import csv
import gzip
from io import BytesIO
from collections import Counter
import math
import os
from pathlib import Path
import random
import re
import socket
import uuid
from urllib.error import URLError, HTTPError
import threading
import time
from urllib.request import Request, url2pathname, build_opener, ProxyHandler
from .feed_proxy import build_feed_opener
from urllib.parse import urlsplit
from .settings import DATA_DIR, Settings, is_local_subscription, split_subscription_sources
from .models import Node, Probe, Result
from .security import assess_outbound
from .parser import parse_subscription, ParseReport
from .engine import SingboxEngine
from .history import History
from .exporter import export_shortlist, export_all_working
from .diagnostics import stage, event, logger, record_failure, error_kind, CycleFailure, safe_count_summary

SNAPSHOT=DATA_DIR/'subscription-last-good.dat'
OWNER=DATA_DIR/'cycle.owner.json'
CANCEL_REQUEST=DATA_DIR/'cycle.cancel.json'
LAST_STATS=DATA_DIR/'last_stats.json'
WORKING_SNAPSHOT=DATA_DIR/'working-latest.json'


MAX_SUBSCRIPTION_BYTES = 25_000_000


def subscription_fingerprint(source: str) -> str:
    """Opaque source identity. Never store a subscription URL in diagnostic logs."""
    return hashlib.sha256(source.strip().encode('utf-8')).hexdigest()


def pool_fingerprint(sources: list[str]) -> str:
    """A stable identity for the same set of sources in any order."""
    if len(sources) == 1:
        return subscription_fingerprint(sources[0])
    return hashlib.sha256(json.dumps(sorted(subscription_fingerprint(x) for x in sources),
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def merge_source_reports(parts: list[ParseReport]) -> ParseReport:
    """Deduplicate on canonical parsed node ID across formats and subscriptions."""
    merged = ParseReport(format='Combined subscriptions' if len(parts) > 1 else parts[0].format)
    seen = set()
    for report in parts:
        merged.total += report.total
        merged.duplicates += report.duplicates
        merged.errors.update(report.errors)
        for node in report.nodes:
            if node.id in seen:
                merged.duplicates += 1
                continue
            seen.add(node.id)
            merged.nodes.append(node)
            merged.unsupported += int(not node.supported)
    return merged


def source_snapshot_path(source: str) -> Path:
    """A previous successful download is reusable ONLY for this exact source.

    Old v1.0.10 global snapshots have no trusted source identity and are not
    automatically attributed to the user's newly selected subscription.
    """
    return SNAPSHOT.parent / 'subscription-sources' / (subscription_fingerprint(source) + '.dat')


def source_snapshot_metadata_path(source: str) -> Path:
    return source_snapshot_path(source).with_suffix('.meta.json')


def recent_source_snapshot(source: str, max_age_seconds: float, now: float | None = None):
    """Return the last validated response only while its per-source TTL holds.

    This requires a successful-download receipt. Old fallback snapshots do not
    qualify as fresh, and a changed URL cannot inherit another URL's receipt.
    """
    if max_age_seconds <= 0 or source_type(source) == 'local-file':
        return None
    path = source_snapshot_path(source)
    try:
        meta = json.loads(source_snapshot_metadata_path(source).read_text(encoding='utf-8'))
        age = (time.time() if now is None else now) - float(meta['completed_at'])
        if meta.get('source_key') != subscription_fingerprint(source) or not 0 <= age < max_age_seconds:
            return None
        data = path.read_bytes()
        if len(data) != int(meta['bytes']):
            return None
        parsed = parse_subscription(data)
        if parsed.usable <= 0:
            return None
        return parsed, age
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


def save_source_snapshot(source: str, payload: bytes) -> None:
    target = source_snapshot_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    save_private(target, payload)
    _atomic_json(source_snapshot_metadata_path(source), {
        'source_key': subscription_fingerprint(source),
        'bytes': len(payload),
        'completed_at': time.time(),
    })
    # Keep the historic file for backwards compatibility/manual recovery, but
    # NEVER use it as an implicit fallback for a different subscription.
    save_private(SNAPSHOT, payload)
    _atomic_json(SNAPSHOT.parent / 'subscription-last-good.meta.json', {
        'source_key': subscription_fingerprint(source),
        'bytes': len(payload),
        'completed_at': time.time(),
    })


class InvalidResume(Exception):
    """A server has changed its representation; start a clean transfer."""


def source_type(source: str) -> str:
    """Never return/log the source string: it could contain secret credentials."""
    if source.lower().startswith('file://') or is_local_subscription(source):
        return 'local-file'
    return 'https' if source.lower().startswith('https://') else 'http'


def _bounded_read(stream, size=MAX_SUBSCRIPTION_BYTES):
    # Read in chunks so a single huge read does not block until the entire
    # response fits the requested size, while enforcing a maximum input size.
    data = bytearray()
    while len(data) <= size:
        block = stream.read(min(128 * 1024, size + 1 - len(data)))
        if not block:
            break
        data.extend(block)
    if len(data) > size:
        raise ValueError('Subscription exceeds 25 MB')
    return bytes(data)


def _local_path(source: str) -> Path:
    if source.lower().startswith('file://'):
        url = urlsplit(source)
        # url2pathname handles Windows drive prefixes and UNC shares on Windows.
        decoded = url2pathname(url.path)
        if url.netloc and url.netloc.lower() != 'localhost':
            decoded = (chr(92) * 2 + url.netloc + decoded) if os.name == 'nt' else ('//' + url.netloc + decoded)
        return Path(decoded)
    return Path(source)


class OperationCancelled(Exception):
    """Intentional stop; does not represent a broken subscription or proxy."""


class NoUsableMeasurements(RuntimeError):
    """No trusted network results; preserve prior statistics and exports."""


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise OperationCancelled('Operation cancelled')


def _readable_socket(response):
    """Find urllib's socket for non-blocking shutdown on Stop (no private bytes logged)."""
    try:
        return response.fp.raw._sock
    except (AttributeError, ValueError):
        return None


def _interrupt_read_on_cancel(response, cancel):
    """Background watcher interrupts a blocking SSL read without changing its timeout.

    This is preferable to reconnecting every few seconds on networks where a
    persistent HTTPS stream may legitimately stall for minutes between bursts.
    """
    finished = threading.Event()
    sock = _readable_socket(response)
    if cancel is None or sock is None:
        return finished

    def watch():
        while not finished.wait(0.25):
            if cancel.is_set():
                # On Windows, shutdown() alone does not always interrupt a
                # recv() already blocked in another thread. closesocket(),
                # called by socket.close(), also aborts pending socket I/O.
                # The response is being cancelled, so it must not be reused.
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                try: sock.close()
                except OSError: pass
                return

    threading.Thread(target=watch, daemon=True, name='feed-cancel-watcher').start()
    return finished


def _fetch_remote_resume(source: str, timeout=300, proxy_mode='system', attempts=5,
                         on_progress=None, cancel=None, proxy_host='', proxy_port=0,
                         proxy_username='', proxy_password='', keyed_partial=False, request_agent=None):
    """Safely resume an interrupted feed, restarting when the server changed it.

    ``timeout`` is an inactivity limit for each socket read, not the overall
    download deadline. Only a complete, validated HTTP body is returned.
    """
    # Keep system/direct opener behavior unchanged for legacy installations.
    opener = (build_feed_opener(proxy_mode, proxy_host, proxy_port, proxy_username, proxy_password)
              if proxy_mode.startswith('manual-')
              else build_opener(ProxyHandler({}) if proxy_mode == 'direct' else ProxyHandler()))
    received = bytearray()
    validator = None
    expected = None
    last_error = None
    cache_key = subscription_fingerprint(source + '\nAgent:' + (request_agent or 'default'))
    # Multi-feed runs keep partial transfers independently, rather than source B
    # destroying source A's five-minute-stall recovery. Preserve legacy paths
    # for single-feed setups and their existing checkpoints.
    if keyed_partial:
        staging = DATA_DIR / 'subscription-downloads'
        staging.mkdir(parents=True, exist_ok=True)
        partial = staging / (cache_key + '.part')
        partmeta = staging / (cache_key + '.meta.json')
    else:
        partial = DATA_DIR / 'subscription-download.part'
        partmeta = DATA_DIR / 'subscription-download.meta.json'
    metadata = _read_json(partmeta)

    # A new source must never inherit the previous feed's partial body.
    if metadata and metadata.get('key') != cache_key:
        old_count = metadata.get('received', 0)
        event('subscription-partial-discarded', kind='different-source',
              bytes=old_count if type(old_count) is int else 0)
        partial.unlink(missing_ok=True)
        partmeta.unlink(missing_ok=True)
        metadata = {}

    if (metadata.get('key') == cache_key and metadata.get('validator')
            and isinstance(metadata.get('expected'), int)
            and isinstance(metadata.get('received'), int)):
        try:
            saved = partial.read_bytes()
            if (len(saved) == metadata['received']
                    and 0 < len(saved) < metadata['expected'] <= MAX_SUBSCRIPTION_BYTES):
                received.extend(saved)
                validator = metadata['validator']
                expected = metadata['expected']
                event('subscription-partial-recovered', bytes=len(saved))
                if on_progress:
                    on_progress(f'Resuming this source at {len(saved):,} bytes.')
        except OSError:
            pass

    def checkpoint():
        if (validator and expected and 0 < len(received) < expected
                and len(received) <= MAX_SUBSCRIPTION_BYTES):
            save_private(partial, bytes(received))
            _atomic_json(partmeta, {'key': cache_key, 'validator': validator,
                                    'expected': expected, 'received': len(received)})

    def reset_partial(reason):
        nonlocal validator, expected
        old_bytes = len(received)
        received.clear()
        validator = None
        expected = None
        partial.unlink(missing_ok=True)
        partmeta.unlink(missing_ok=True)
        event('subscription-resume-restarted', kind=reason, discarded_bytes=old_bytes)
        if on_progress:
            on_progress('Remote feed version changed; retrying cleanly from byte 0.')

    for attempt in range(1, attempts + 1):
        _check_cancel(cancel)
        last_notice = 0.0
        offset = len(received)
        event('subscription-fetch-attempt', attempt=attempt, received=offset,
              stall_timeout_seconds=timeout, source_id=cache_key[:10])
        headers = {'User-Agent': request_agent or 'IranProxyMonitor/1.0.17',
                   'Accept': '*/*', 'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
            if validator:
                headers['If-Range'] = validator
        try:
            request = Request(source, headers=headers)
            with opener.open(request, timeout=min(timeout, 30)) as response:
                sock = _readable_socket(response)
                if sock is not None:
                    try:
                        sock.settimeout(timeout)
                    except OSError:
                        pass
                watcher = _interrupt_read_on_cancel(response, cancel)
                try:
                    status = response.status
                    content_range = response.headers.get('Content-Range', '')
                    if offset and status == 206:
                        match = re.fullmatch(r'bytes\s+(\d+)-(\d+)/(\d+|\*)',
                                             content_range.strip())
                        if not match or int(match.group(1)) != offset:
                            raise InvalidResume('range-mismatch')
                        if int(match.group(2)) < offset:
                            raise InvalidResume('invalid-range-end')
                        if match.group(3) != '*':
                            total = int(match.group(3))
                            if expected is not None and total != expected:
                                raise InvalidResume('size-changed')
                            expected = total
                        etag = response.headers.get('ETag', '')
                        modified = response.headers.get('Last-Modified', '')
                        if validator and validator.startswith('"') and etag and etag != validator:
                            raise InvalidResume('validator-changed')
                        if validator and not validator.startswith('"') and modified and modified != validator:
                            raise InvalidResume('validator-changed')
                    elif offset and status == 200:
                        # Some servers ignore Range. Their full response replaces
                        # the saved partial; NEVER append the bytes together.
                        reset_partial('range-ignored')
                    elif not offset and status == 206:
                        match = re.fullmatch(r'bytes\s+0-(\d+)/(\d+|\*)',
                                             content_range.strip())
                        if not match:
                            raise InvalidResume('unexpected-partial-response')
                        if match.group(2) != '*':
                            expected = int(match.group(2))
                    elif status != 200:
                        raise InvalidResume('unexpected-status')

                    if not validator:
                        etag = response.headers.get('ETag', '')
                        validator = (etag if etag and not etag.startswith('W/')
                                     else response.headers.get('Last-Modified'))
                    length = response.headers.get('Content-Length')
                    if expected is None and length and length.isdigit():
                        expected = len(received) + int(length)
                    if expected is not None and expected > MAX_SUBSCRIPTION_BYTES:
                        raise ValueError('Subscription exceeds 25 MB')

                    while len(received) <= MAX_SUBSCRIPTION_BYTES:
                        _check_cancel(cancel)
                        reader = getattr(response, 'read1', None) or response.read
                        block = reader(min(32 * 1024, MAX_SUBSCRIPTION_BYTES + 1 - len(received)))
                        _check_cancel(cancel)
                        if not block:
                            break
                        received.extend(block)
                        if len(received) % (128 * 1024) < len(block):
                            checkpoint()
                        if on_progress and time.monotonic() - last_notice >= 2:
                            last_notice = time.monotonic()
                            suffix = f' / {expected:,}' if expected is not None else ''
                            on_progress(f'Downloading selected feed: {len(received):,}{suffix} bytes '
                                        f'(attempt {attempt}); Stop cancels.')
                    if len(received) > MAX_SUBSCRIPTION_BYTES:
                        raise ValueError('Subscription exceeds 25 MB')
                    if expected is None or len(received) == expected:
                        event('subscription-fetch-complete', bytes=len(received),
                              attempts=attempt, proxy_mode=proxy_mode, source_id=cache_key[:10])
                        partial.unlink(missing_ok=True)
                        partmeta.unlink(missing_ok=True)
                        return bytes(received)
                    raise EOFError('Subscription response incomplete')
                finally:
                    watcher.set()
        except OperationCancelled:
            checkpoint()
            raise
        except InvalidResume as exc:
            # Common with live changing subscriptions and stale ETags.
            # Never merge bytes from two different revisions.
            reset_partial(str(exc))
            last_error = exc
            if attempt < attempts:
                continue
        except HTTPError as exc:
            if exc.code == 416 and offset:
                reset_partial('range-not-satisfiable')
                last_error = exc
                if attempt < attempts:
                    continue
            checkpoint()
            _check_cancel(cancel)
            last_error = exc
            event('subscription-fetch-retry', attempt=attempt, bytes=len(received),
                  kind=error_kind(exc), proxy_mode=proxy_mode)
            if exc.code in (400, 401, 403, 404, 410):
                break
        except (OSError, URLError, EOFError) as exc:
            checkpoint()
            _check_cancel(cancel)
            last_error = exc
            event('subscription-fetch-retry', attempt=attempt, bytes=len(received),
                  kind=error_kind(exc), proxy_mode=proxy_mode)

        if attempt < attempts:
            for _ in range(10):
                _check_cancel(cancel)
                time.sleep(.1)
    _check_cancel(cancel)
    checkpoint()
    if last_error:
        raise last_error
    raise RuntimeError('Subscription HTTP response did not complete')


def fetch_subscription(source: str, timeout=300, proxy_mode='system', on_progress=None, cancel=None,
                       proxy_host='', proxy_port=0, proxy_username='', proxy_password='', keyed_partial=False,
                       request_agent=None, attempts=5):
    _check_cancel(cancel)
    if source_type(source)=='local-file':
        with _local_path(source).open('rb') as stream:
            data=_bounded_read(stream)
    else:
        data=_fetch_remote_resume(source,timeout,proxy_mode,on_progress=on_progress,cancel=cancel,
                                  proxy_host=proxy_host,proxy_port=proxy_port,
                                  proxy_username=proxy_username,proxy_password=proxy_password,
                                  keyed_partial=keyed_partial,request_agent=request_agent,attempts=attempts)
    if data[:2]==b'\x1f\x8b':
        with gzip.GzipFile(fileobj=BytesIO(data)) as stream:
            data=_bounded_read(stream)
    return data


def save_private(path:Path,data:bytes):
    p=path.with_suffix(path.suffix+'.tmp')
    p.write_bytes(data)
    try:os.chmod(p,0o600)
    except OSError:pass
    p.replace(path)


def load_report(settings: Settings, notify=lambda m: None, cache_only=False, cancel=None,
                allow_cache=True, reuse_fresh_seconds: float=0):
    """Load one or more feeds; never cross-contaminate source-specific caches.

    A failed feed can use its own snapshot in monitoring mode, but Update-only
    never calls an old cached feed freshly updated. Successful sources are kept
    even if another fails, with an explicit per-source status and warning.
    """
    sources = split_subscription_sources(settings.subscription_url)
    if not sources:
        raise ValueError('Enter at least one subscription URL or absolute file path.')
    parts = []
    statuses = []
    incidents = []
    for index, source in enumerate(sources, 1):
        _check_cancel(cancel)
        source_kind = source_type(source)
        source_id = subscription_fingerprint(source)[:10]
        phase = 'subscription-local-file' if source_kind == 'local-file' else 'subscription-download'
        loaded = None
        state = 'failed'
        fetched_bytes = 0
        reason = None
        updated_at = None
        # Ordinary scans may reuse a successful response from the same URL for
        # 60 minutes. The explicit Update subscription button bypasses this.
        if allow_cache and not cache_only and reuse_fresh_seconds > 0:
            recent = recent_source_snapshot(source, reuse_fresh_seconds)
            if recent is not None:
                loaded, age = recent
                state = 'recent-cache'
                updated_at = time.time() - age
                notify(f'Source {index}/{len(sources)} #{source_id}: updated {age/60:.0f} minutes ago; '
                       'using its verified saved subscription without downloading again.')
                event('subscription-recent-reused', source_id=source_id, age_minutes=round(age/60,1))
        if loaded is None and not cache_only:
            stage(phase)
            notify(f'Loading subscription {index}/{len(sources)} (source #{source_id})…')
            try:
                payload = fetch_subscription(source, timeout=settings.subscription_timeout_seconds,
                                             proxy_mode=settings.subscription_proxy_mode,
                                             on_progress=notify, cancel=cancel,
                                             proxy_host=settings.subscription_proxy_host,
                                             proxy_port=settings.subscription_proxy_port,
                                             proxy_username=settings.subscription_proxy_username,
                                             proxy_password=settings.subscription_proxy_password,
                                             keyed_partial=len(sources)>1)
                try:
                    loaded = parse_subscription(payload)
                except ValueError:
                    loaded = ParseReport(format='Unrecognized response')
                if loaded.usable <= 0 and source_kind != 'local-file':
                    # Different providers select Base64 / Clash / sing-box from
                    # the client User-Agent. Never cache an unparseable HTML or
                    # incompatible format as a good subscription.
                    for agent in ('v2rayNG/1.10.0', 'v2rayN/7.0', 'ClashMeta/1.18', 'sing-box/1.14.4'):
                        _check_cancel(cancel)
                        notify(f'Source {index}/{len(sources)} returned no supported nodes; '
                               f'trying format negotiation ({agent.split("/")[0]}).')
                        try:
                            alternate = fetch_subscription(source, timeout=min(40,settings.subscription_timeout_seconds),
                                proxy_mode=settings.subscription_proxy_mode, on_progress=notify, cancel=cancel,
                                proxy_host=settings.subscription_proxy_host,
                                proxy_port=settings.subscription_proxy_port,
                                proxy_username=settings.subscription_proxy_username,
                                proxy_password=settings.subscription_proxy_password,
                                keyed_partial=True, request_agent=agent,attempts=1)
                            candidate = parse_subscription(alternate)
                            if candidate.usable > 0:
                                payload, loaded = alternate, candidate
                                break
                        except OperationCancelled:
                            raise
                        except (OSError,ValueError,URLError,HTTPError,EOFError):
                            continue
                if loaded.usable <= 0:
                    loaded = None  # Critical: a failed format must not be marked successful.
                    raise ValueError('Source delivered a response, but no supported proxy nodes were found '
                                     '(unsupported format, HTML page, or expired subscription).')
                fetched_bytes = len(payload) if source_kind != 'local-file' else 0
                save_source_snapshot(source, payload)
                updated_at = time.time()
                state = 'local-file' if source_kind == 'local-file' else 'fresh'
                event('subscription-source-ok', source_kind=source_kind, bytes=len(payload),
                      total=loaded.total, supported=loaded.usable, source_id=source_id)
            except OperationCancelled:
                raise
            except Exception as exc:
                reason = record_failure(exc, phase, warning=True)
                incidents.append(reason)
                notify(f'Subscription {index}/{len(sources)} FAILED (source #{source_id}); '+
                       f'{reason.reason}; incident {reason.incident_id}.')
        if loaded is None and allow_cache:
            backup = source_snapshot_path(source)
            if backup.is_file():
                try:
                    old = parse_subscription(backup.read_bytes())
                    if old.usable > 0:
                        loaded = old
                        state = 'saved-no-download' if cache_only else 'cached-same-source'
                        event('subscription-cache-used',total=old.total,supported=old.usable,
                              source_id=source_id,same_source=True)
                        notify(f'Source {index}/{len(sources)} #{source_id}: STALE same-source cache used.')
                except (OSError, ValueError):
                    pass
        if loaded is None:
            statuses.append({'id':source_id,'kind':source_kind,'state':'failed','nodes':0,'fetched_bytes':0})
        else:
            parts.append(loaded)
            statuses.append({'id':source_id,'kind':source_kind,'state':state,'nodes':loaded.usable,
                             'fetched_bytes':fetched_bytes, 'last_updated_at':updated_at})
    if not parts:
        if incidents:
            issue = incidents[-1]
            raise CycleFailure(issue.phase,
                               f'{issue.reason}; selected subscription was NOT loaded; old results preserved',
                               issue.incident_id)
        raise RuntimeError('Selected subscriptions unavailable; no verified same-source cache exists')
    report = merge_source_reports(parts)
    report.source_statuses = statuses
    report.pool_id = pool_fingerprint(sources)
    failed = sum(x['state'] == 'failed' for x in statuses)
    stale = sum(x['state'] == 'cached-same-source' for x in statuses)
    if failed or stale:
        notify(f'INCOMPLETE pool: {len(parts)}/{len(sources)} feeds available; '
               f'{failed} failed, {stale} cached. Results may omit unavailable sources.')
    if len(sources) == 1:
        origin = statuses[0]['state']
    else:
        origin = ('combined-incomplete' if failed or stale else
                  'combined-reused' if any(x['state'] in ('recent-cache','saved-no-download') for x in statuses)
                  else 'combined-fresh')
    event('subscription-pool-ready',sources=len(sources),loaded=len(parts),
          failed=failed,stale=stale,total=report.total,supported=report.usable)
    return report, origin


def select_download_candidates(connected, limit:int, cutoff:int, exploratory_pct:int,
                               history:History):
    """Prefer responsive nodes but reserve capacity for slower, possibly faster nodes.

    The cutoff is a preference, not a hard exclusion: 'best download speed'
    must be able to discover working nodes with high HTTPS latency.
    """
    if len(connected)<=limit:return connected[:]
    responsive=[pair for pair in connected if not cutoff or pair[1].latency_ms < cutoff]
    preferred_slots=max(0,round(limit*(100-exploratory_pct)/100))
    chosen=responsive[:preferred_slots];seen={n.id for n,p in chosen}
    others=[pair for pair in connected if pair[0].id not in seen]
    old=history.recent([n for n,p in others])
    # Reserve a portion for known sustained high performers, then spread remaining
    # experiments across the full latency range rather than feed order.
    historical=sorted(others,key=lambda pair:(-max(old.get(pair[0].id,{}).get('mbps',[]) or [0]),
                                              pair[1].latency_ms or float('inf')))
    hist_slots=min(len(others),max(0,round((limit-len(chosen))*0.5)))
    chosen.extend(historical[:hist_slots]);seen.update(n.id for n,p in historical[:hist_slots])
    others=[pair for pair in others if pair[0].id not in seen]
    slots=limit-len(chosen)
    if slots>0 and others:
        # Equally spaced latency strata includes both low/medium and very high ping.
        if slots>=len(others):chosen.extend(others)
        else:
            indices=sorted(set(min(len(others)-1,int((i+0.5)*len(others)/slots))
                               for i in range(slots)))
            chosen.extend(others[i] for i in indices)
    return chosen[:limit]


def ranking(results:list[Result],history:History):
    historical=history.recent([r.node for r in results])
    for r in results:
        old=historical.get(r.node.id)
        r.reliability=history.reliability(old)
        rate=r.best_validated_mbps
        if not rate:
            r.rank_score=0.0
            continue
        # Conservative floor rate, not burst-inflated average Mbps, is scored.
        # Balance 70% throughput floor, 25% HTTPS latency, 5% historical reliability.
        top=max((x.best_validated_mbps for x in results), default=0.0)
        speed_component=math.log1p(rate)/max(.001,math.log1p(top))
        responsive=1/(1+(r.probe.latency_ms or 10000)/600)
        r.rank_score=(.70*speed_component+.25*responsive+.05*r.reliability)*assess_outbound(r.node.outbound).ranking_factor
    # Never call a preliminary-only result the best verified download speed.
    verified=[r for r in results if r.verified]
    fastest=sorted(verified,key=lambda r:(-r.best_validated_mbps,r.probe.latency_ms or 999999,r.node.id))
    # Messaging needs genuine data transfer, but confirmation isn't necessary.
    ping=sorted(results,key=lambda r:(r.probe.latency_ms or float('inf'),-r.mbps,r.node.id))
    overall=sorted(verified,key=lambda r:(-r.rank_score,-r.best_validated_mbps,r.node.id))
    return fastest,ping,overall


def reliable_shortlist(results: list[Result], min_flow_mbps: float=1.0) -> list[Result]:
    """Historical HTTPS reliability first, only among currently verified flow nodes.

    Reliability is an estimate of HTTPS probe success, not an uptime SLA.
    The Mbps threshold is the conservative measured flow, not a bursty average.
    """
    return sorted([r for r in results if r.verified and r.best_validated_mbps >= min_flow_mbps],
                  key=lambda r:(-r.reliability,-r.best_validated_mbps,
                                r.probe.latency_ms or float('inf'),r.node.id))


def confirmation_selection(successful, prelim, history:History, limit:int):
    """Mix preliminary speed leaders with low-latency contenders to reduce lucky-burst bias."""
    sorted_speed=sorted(successful,key=lambda pair:-prelim[pair[0].id].mbps)
    sorted_ping=sorted(successful,key=lambda pair:pair[1].latency_ms or float('inf'))
    h=history.recent([n for n,p in successful])
    sorted_reliable=sorted(successful,key=lambda pair:-max(h.get(pair[0].id,{}).get('mbps',[]) or [0]))
    chosen=[];seen=set()
    for group in (sorted_speed[:max(1,round(limit*.6))],
                  sorted_ping[:max(1,round(limit*.25))],sorted_reliable,sorted_speed):
        for pair in group:
            if len(chosen)>=limit:return chosen
            if pair[0].id not in seen:
                chosen.append(pair);seen.add(pair[0].id)
    return chosen


def run_cycle(settings:Settings, stop:threading.Event, progress=lambda d:None,
              message=lambda m:None, all_nodes=False, update_only=False) -> dict:
    stage('settings-validation')
    settings.validate()
    started=time.time()
    event('cycle-started', all_nodes=all_nodes, update_only=update_only)
    stage('subscription-source')
    report,origin=load_report(settings,message,cancel=stop,allow_cache=not update_only,
                              cache_only=(settings.use_cached_subscription_for_tests and not update_only),
                              reuse_fresh_seconds=(3600 if not update_only else 0))
    stage('parsing-and-diagnostics')
    # Diagnostics reveal why configurations were excluded without exposing credentials.
    diagnostic=DATA_DIR/'unsupported-nodes.csv'
    with diagnostic.open('w',newline='',encoding='utf-8-sig') as fh:
        writer=csv.writer(fh);writer.writerow(['node_id','name','protocol','reason'])
        for n in report.nodes:
            if not n.supported:writer.writerow([n.id,n.name,n.protocol,'; '.join(n.problems)])
    stats={'time':started,'subscription':origin,
           'subscription_fresh':origin not in ('cached-same-source','combined-incomplete'),
           'source_id':(report.pool_id if isinstance(getattr(report,'pool_id',None),str) else pool_fingerprint(split_subscription_sources(settings.subscription_url)))[:10],
           'sources':getattr(report,'source_statuses',[]),
           'source_count':len(split_subscription_sources(settings.subscription_url)), 'total':report.total,
           'parsed':report.usable,'unsupported':report.unsupported,'duplicates':report.duplicates,
           'format':report.format,'feed_bytes':sum(x.get('fetched_bytes',0) for x in (getattr(report,'source_statuses',[]) if isinstance(getattr(report,'source_statuses',[]),list) else [])),
           'connectivity_tested':0,'connected':0,
           'speed_tested':0,'baseline_mbps':None,'fastest_mbps':0,
           'exports':{},'errors':dict(report.errors),'core_version':''}
    progress({'event':'nodes-loaded','nodes':report.nodes})
    progress({'event':'scan-usage-feed','bytes':stats['feed_bytes']})
    progress({'phase':'subscription','done':report.total,'total':report.total,'passed':report.usable})
    event('subscription-parsed', total=report.total, supported=report.usable,
          unsupported=report.unsupported, duplicates=report.duplicates)
    if update_only:
        stats.update(update_only=True,connected=None,speed_tested=None,
                     fastest_mbps=None,baseline_mbps=None)
        return stats
    if stop.is_set():return stats
    stage('sing-box-initialization')
    engine=SingboxEngine(settings,stop)
    event('core-ready', version=engine.version.splitlines()[0].replace(' ', '_')[:64])
    stats['core_version']=engine.version
    stage('history-database')
    with_history=History()
    try:
        supported=[n for n in report.nodes if n.supported]
        with_history.register(supported)
        stage('candidate-selection')
        candidates=with_history.select_probes(supported,settings.probes_per_cycle,all_nodes or settings.scan_all)
        stats['connectivity_tested']=len(candidates)
        progress({'event':'probe-start','node_ids':[n.id for n in candidates]})
        message(f'Probing {len(candidates)} nodes in sing-box batches; source contains {report.total}.')
        stage('proxy-connectivity')
        probes=engine.connectivity(candidates,progress)
        event('connectivity-finished', attempted=len(candidates),
              passed=sum(p.ok for p in probes.values()),
              failures=safe_count_summary([p.error.split(':')[0] for p in probes.values() if not p.ok]))
        stats['latency_http_sent_bytes']=sum(getattr(x,'http_sent_bytes',0) for x in probes.values())
        stats['latency_http_received_bytes']=sum(getattr(x,'http_received_bytes',0) for x in probes.values())
        stats['latency_http_bytes']=stats['latency_http_sent_bytes']+stats['latency_http_received_bytes']
        connected=[(n,probes[n.id]) for n in candidates if n.id in probes and probes[n.id].ok]
        connected.sort(key=lambda np:np[1].latency_ms if np[1].latency_ms is not None else float('inf'))
        progress({'event':'latency-finished','passed':len(connected)})
        stats['connected']=len(connected)
        if stop.is_set():return stats
        if not connected:
            event('cycle-skipped', kind='no-proxy-connectivity', probed=len(candidates))
            raise NoUsableMeasurements('No proxy returned a successful HTTPS response. Network may be offline or blocked')
        stage('direct-baseline')
        stats['baseline_mbps']=engine.baseline() if settings.baseline_kib else None
        progress({'event':'scan-usage-baseline','bytes':getattr(engine,'baseline_data_bytes',0)})
        stage('speed-candidate-selection')
        # Cutoff guides the responsive group, but exploratory quota includes
        # high-latency connections so top-throughput ranking is truly ping-agnostic.
        eligible=[(n,p) for n,p in connected if settings.latency_cutoff_ms==0 or
                  (p.latency_ms is not None and p.latency_ms < settings.latency_cutoff_ms)]
        selected=select_download_candidates(connected,settings.speed_candidates,
                                            settings.latency_cutoff_ms,
                                            settings.exploratory_speed_pct,with_history)
        stats['latency_eligible']=len(eligible)
        progress({'event':'speed-selection','node_ids':[n.id for n,p in selected],
                  'eligible':len(eligible),'cutoff_ms':settings.latency_cutoff_ms,
                  'exploratory':len([1 for n,p in selected if (n,p) not in eligible])})
        # Budget applies to speed-test HTTP response bodies; small latency and
        # baseline transfers are separately reported, not misrepresented as zero cost.
        budget=int(settings.budget_mib*1024*1024)
        # Reserve at least 60% of capacity for genuinely long confirmations.
        prelim_bytes=settings.prelim_kib*1024
        allowable=max(0,(budget*40//100)//prelim_bytes)
        selected=selected[:max(0,allowable)]
        if not selected:
            event('cycle-skipped', kind='no-download-candidates')
            raise NoUsableMeasurements('No download candidates were available; no ranking was replaced')
        message(f'Speed-testing {len(selected)} working proxies (limited by bandwidth budget).')
        stage('preliminary-throughput')
        prelim,used=engine.throughput([n for n,p in selected],prelim_bytes,budget,progress)
        stats['speed_attempted']=len(prelim)
        stats['speed_tested']=sum(int(x.ok) for x in prelim.values())
        event('preliminary-throughput-finished', tested=len(prelim), ok=stats['speed_tested'], bytes=used)
        if not stats['speed_tested'] and not stop.is_set():
            event('cycle-skipped', kind='no-throughput', tested=len(prelim))
            raise NoUsableMeasurements('No proxy delivered test traffic. Network may be offline or test hosts blocked')
        successful=[(n,p) for n,p in selected if n.id in prelim and prelim[n.id].ok]
        max_confirm=min(15,max(5,settings.shortlist_size+3))
        confirmation_group=confirmation_selection(successful,prelim,with_history,max_confirm)
        confirmations={}
        stage('confirmation-throughput')
        confirm_sizes={}
        # Process top candidates together, up to speed_workers simultaneous streams.
        # Confirmation size is adaptive per node and reservations keep the payload
        # cap across concurrent transfers.
        for n,p in confirmation_group:
            size=max(settings.confirm_min_kib*1024,
                     min(settings.confirm_max_kib*1024,
                         int(prelim[n.id].mbps*1e6/8*settings.confirm_seconds*1.4)))
            confirm_sizes[n.id]=size
        if not stop.is_set() and confirm_sizes:
            remaining=budget-used
            confirmations,cost=engine.throughput(
                [n for n,p in confirmation_group],
                settings.confirm_min_kib*1024,remaining,progress,
                phase='confirmation',sizes=confirm_sizes)
            used+=cost
        stats['bytes_downloaded']=used
        stats['speed_body_bytes']=used
        stats['baseline_body_bytes']=getattr(engine,'baseline_data_bytes',0)
        stats['scan_payload_bytes']=(used+int(stats['feed_bytes'])+
            stats['baseline_body_bytes']+stats.get('latency_http_bytes',0))
        stats['scan_payload_mib']=round(stats['scan_payload_bytes']/1048576,3)
        stats['scan_traffic_scope']=('Measured feed and speed-test response bytes, direct baseline bodies, '
            'and latency HTTP/CONNECT messages; TLS, proxy encryption overhead '
            'and unobserved failed transfer bytes are excluded')
        progress({'event':'scan-usage-final', 'feed':int(stats['feed_bytes']),
                  'latency':stats.get('latency_http_bytes',0),'speed':used,
                  'baseline':stats['baseline_body_bytes']})
        stage('history-update')
        results=[]
        for n,p in selected:
            pre=prelim.get(n.id)
            if pre and pre.ok:
                conf=confirmations.get(n.id)
                r=Result(n,p,pre,conf)
                results.append(r)
        successful_ids={r.node.id for r in results}
        for n in candidates:
            if n.id in probes:
                row=next((r for r in results if r.node.id==n.id),None)
                with_history.record(n,probes[n.id],row.best_validated_mbps if row and row.verified else None,
                                    (row.prelim.bytes_received+(row.confirm.bytes_received if row.confirm else 0)) if row else 0)
        if stop.is_set():return stats
        if not results:
            event('cycle-skipped', kind='no-successful-result')
            raise NoUsableMeasurements('No valid downloadable results; prior rankings and exports retained')
        stage('ranking')
        fastest,ping,overall=ranking(results,with_history)
        for index,r in enumerate(ping,1):
            progress({'event':'node-ranked','node_id':r.node.id,'rank':index,
                      'reliability':r.reliability,
                      'status':('Consistent flow (test host)' if r.verified else
                                'Intermittent confirmation' if r.confirm and r.confirm.ok else
                                'Preliminary only')})
        stats['fastest_mbps']=round(fastest[0].best_validated_mbps,3) if fastest else 0.0
        stage('export-validation')
        # Every named category is different. Old exports are never replaced by an
        # empty/unverified result. "Best ping" needs at least a real download.
        # Reliability-first: historically responsive, with a *confirmed* current
        # 1.000 Mbps conservative flow floor. Preliminary bursts never qualify.
        reliable = reliable_shortlist(results, min_flow_mbps=1.0)
        for kind,items in (('best-download-speed',fastest),('best-ping',ping),
                           ('best-overall',overall),('best-reliable',reliable)):
            if not items:
                message(f'No verified results for {kind}; previous shortlist retained.')
                continue
            chosen=[r.node for r in items[:settings.shortlist_size]]
            try:
                stats['exports'][kind]=export_shortlist(chosen,kind,engine.binary)
                event('shortlist-exported', kind=kind, nodes=len(chosen))
                message(f'Saved {kind} shortlist: {len(chosen)} nodes.')
            except (OSError,RuntimeError,ValueError) as e:
                incident=record_failure(e, f'export-{kind}', warning=True)
                message(f'{kind} export validation failed ({incident.reason}; incident {incident.incident_id}); older file kept.')
        # Working nodes are HTTPS-passers, not necessarily sustained-speed winners.
        try:
            stats['working_export']=export_all_working([n for n,p in connected],engine.binary)
            event('working-pool-exported',nodes=len(connected))
        except (OSError,RuntimeError,ValueError) as exc:
            issue=record_failure(exc,'export-all-working',warning=True)
            message(f'All-working export failed; older files retained (incident {issue.incident_id}).')
        stats['reliable_min_flow_mbps']=1.0
        stats['reliable_candidates']=len(reliable)
        stats['results']=[{'name':r.node.name,'protocol':r.node.protocol,
                           'encryption':assess_outbound(r.node.outbound).encryption,
                           'security_score':assess_outbound(r.node.outbound).score,
                           'mbps':round(r.mbps,3),
                           'latency_ms':r.probe.latency_ms,'reliability':round(r.reliability,3),
                           'status':'Consistent flow (test host)' if r.verified else 'Preliminary only',
                           'flow_mbps':r.confirm.flow_mbps if r.confirm else None,
                           'flow_active_ratio':r.confirm.flow_active_ratio if r.confirm else None,
                           'confirmed':r.verified,'sample_seconds':r.confirm.seconds if r.confirm else r.prelim.seconds}
                          for r in (fastest+[r for r in ping if not r.verified])[:100]]
        # Represent failed checks separately, without calling untested nodes dead.
        if len(stats['results'])<100:
            failed=[n for n in candidates if n.id in probes and not probes[n.id].ok]
            for n in failed[:100-len(stats['results'])]:
                stats['results'].append({'name':n.name,'protocol':n.protocol,
                    'encryption':assess_outbound(n.outbound).encryption,
                    'security_score':assess_outbound(n.outbound).score,
                    'mbps':0.0,
                    'latency_ms':None,'reliability':0.0,'status':'Unavailable this cycle',
                    'confirmed':False})
        try:
            stats['working_count']=save_working_snapshot(connected,results,stats['source_id'])
        except (OSError,TypeError,ValueError) as exc:
            record_failure(exc,'working-pool-save',warning=True)
            message('Working-node history could not be saved; previous snapshot retained.')
        try:
            from .scan_usage import record_scan_usage
            stats['scan_payload_today_mib']=record_scan_usage(
                stats['scan_payload_bytes'], started, stats['source_id'])
        except (OSError,ValueError,TypeError) as exc:
            record_failure(exc,'scan-usage-save',warning=True)
        stats['next_due']=time.time()+settings.refresh_minutes*60
        with_history.trim()
        event('cycle-finished', connected=stats['connected'], speed_tested=stats['speed_tested'],
              top_mbps=stats['fastest_mbps'], exports=len(stats['exports']))
        return stats
    finally:
        with_history.close()


def save_working_snapshot(connected, measured: list[Result], source_id: str):
    """Keep last completed HTTPS-successful pool, without overwriting on failures.

    This contains proxy credentials in original node configs, so the local file
    uses the same private permissions as source caches and saved shortlists.
    """
    known={r.node.id:r for r in measured}
    records=[]
    for node,probe in connected:
        row=known.get(node.id)
        records.append({'name':node.name,'protocol':node.protocol,
                        'outbound':node.outbound,'source_kind':node.source_kind,
                        'source_text':node.source_text,'id':node.id,
                        'latency':probe.latency_ms,
                        'mbps':row.mbps if row else None,
                        'flow_mbps':row.best_validated_mbps if row and row.verified else None,
                        'seconds':row.confirm.seconds if row and row.confirm else None,
                        'confirmed':bool(row and row.verified),
                        'reliability':row.reliability if row else None,
                        'status':('Consistent flow (test host)' if row and row.verified else
                                  'HTTPS passed · speed not confirmed')})
    payload=json.dumps({'schema':1,'time':time.time(),'source_id':source_id,
                        'nodes':records},ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(payload)>40_000_000:
        raise ValueError('Working-node snapshot exceeds 40 MB safety limit')
    save_private(WORKING_SNAPSHOT,payload)
    return len(records)


def read_working_snapshot() -> dict:
    try:
        if WORKING_SNAPSHOT.stat().st_size > 40_000_000:
            return {}
        data=json.loads(WORKING_SNAPSHOT.read_text('utf-8'))
        if data.get('schema') != 1 or not isinstance(data.get('nodes'),list):
            return {}
        return data
    except (OSError,TypeError,ValueError):
        return {}


def persist_stats(stats):
    temp=LAST_STATS.with_suffix('.json.tmp')
    temp.write_text(json.dumps(stats,ensure_ascii=False,indent=2),'utf-8')
    temp.replace(LAST_STATS)


def read_stats():
    try:return json.loads(LAST_STATS.read_text('utf-8'))
    except (OSError,ValueError):return {}

# One-at-a-time OS lock with a separate owner identity for cross-process Stop.
# A lock is released automatically by Windows/the OS when its owning process exits.
from contextlib import contextmanager


class CycleBusy(RuntimeError):
    """Another process holds the lock; this is not a monitoring test failure."""


def _atomic_json(path: Path, value: dict):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value),encoding='utf-8')
    try:os.chmod(temp,0o600)
    except OSError:pass
    temp.replace(path)


def _read_json(path: Path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):return {}


def active_cycle_info():
    """Owner info is advisory; OS file locking remains the authority."""
    data=_read_json(OWNER)
    if data.get('run_id') and isinstance(data.get('pid'),int):return data
    return {}


def request_cancel_active_cycle() -> bool:
    """Ask another v1.0.9+ instance to stop, without killing unrelated processes."""
    owner=active_cycle_info()
    if not owner:return False
    _atomic_json(CANCEL_REQUEST,{'run_id':owner['run_id']})
    event('cross-process-cancel-requested',pid=owner['pid'])
    return True


class CombinedStop:
    def __init__(self,local_event,run_id):
        self.local_event=local_event
        self.run_id=run_id
        self._next_check=0.0
        self._remote=False
        self._guard=threading.Lock()

    def is_set(self):
        if self.local_event.is_set() or self._remote:return True
        now=time.monotonic()
        if now<self._next_check:return False
        with self._guard:
            if now>=self._next_check:
                self._next_check=now+0.25
                self._remote=_read_json(CANCEL_REQUEST).get('run_id')==self.run_id
        return self._remote


@contextmanager
def single_cycle_lock():
    p=DATA_DIR/'cycle.lock'
    with p.open('a+b') as f:
        # Do not write into a lock byte before owning it (old versions did).
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as e:raise CycleBusy('Another Iran Proxy Monitor operation is active') from e
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as e:raise CycleBusy('Another Iran Proxy Monitor operation is active') from e
        identity={'run_id':uuid.uuid4().hex,'pid':os.getpid(),'started':time.time()}
        try:
            CANCEL_REQUEST.unlink(missing_ok=True)
            _atomic_json(OWNER,identity)
            yield identity['run_id']
        finally:
            if _read_json(OWNER).get('run_id')==identity['run_id']:
                OWNER.unlink(missing_ok=True)
            if _read_json(CANCEL_REQUEST).get('run_id')==identity['run_id']:
                CANCEL_REQUEST.unlink(missing_ok=True)
            if os.name=='nt':
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)


_unlocked_run_cycle=run_cycle
def run_cycle(settings,stop,progress=lambda d:None,message=lambda m:None,all_nodes=False,update_only=False):
    stage('cycle-lock')
    try:
        with single_cycle_lock() as run_id:
            return _unlocked_run_cycle(settings,CombinedStop(stop,run_id),progress,message,all_nodes,update_only)
    except (CycleFailure,CycleBusy,OperationCancelled):
        raise
    except Exception as exc:
        failure=record_failure(exc)
        raise failure from None
