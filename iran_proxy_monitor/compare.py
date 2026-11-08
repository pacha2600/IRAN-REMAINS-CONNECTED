"""On-demand, two-destination check of ONE selected outbound.

Uses the same local sing-box routing as monitoring. Never bypasses the proxy or
changes shortlists/history. This checks destination-specific behavior, not Karing.
"""
from __future__ import annotations
from urllib.parse import urlsplit
import threading
from .settings import Settings
from .models import Node, Speed
from .engine import find_singbox, available_ports, CoreSession, check_core, batch_config, speed_confirm_one


def compare_node(node: Node, settings: Settings, cancel: threading.Event | None = None,
                 on_progress=lambda message: None, cap_mib: int = 4, seconds: float = 12.0):
    if not node.supported:
        raise ValueError('The selected configuration is unsupported by the parser.')
    endpoints=[]
    hosts=set()
    for template in settings.download_urls:
        host=urlsplit(template).hostname
        if host and host not in hosts:
            endpoints.append((host,template));hosts.add(host)
        if len(endpoints)==2: break
    if len(endpoints)<2:
        raise ValueError('Configure at least two download endpoints on distinct hosts in Test endpoints.')
    binary=find_singbox(settings.singbox_path)
    port=available_ports(1)[0]
    if not check_core(binary,batch_config([node],[port])):
        raise RuntimeError('sing-box rejected the selected configuration. See diagnostic log.')
    results=[]
    with CoreSession(binary,[node],[port]):
        for index,(host,template) in enumerate(endpoints,1):
            if cancel and cancel.is_set(): break
            on_progress(f'Comparing destination {index}/2 ({host}) …')
            speed=speed_confirm_one(node,port,[template],cap_mib*1024*1024,seconds,cancel,
                                    min_seconds=settings.confirm_min_seconds)
            results.append((host,speed))
    return results


def format_comparison(results):
    lines=['Same proxy, two different HTTPS download servers:', '']
    for host, speed in results:
        if speed.ok:
            label='consistent-flow sample' if speed.verified else 'intermittent or short; unverified'
            lines.append(f'{host}: {speed.mbps:.3f} Mbps, '
                         f'{speed.bytes_received / 1024:.0f} KiB in {speed.seconds:.1f}s ({label})')
        else:
            lines.append(f'{host}: download failed ({speed.error[:90]})')
    lines.extend(['', 'This measures only these destinations via the app’s sing-box core.',
                  'It does not prove how Karing, NekoBox, Telegram, or a browser will perform.',
                  'Retesting can consume up to 8 MiB of response data.'])
    return '\n'.join(lines)
