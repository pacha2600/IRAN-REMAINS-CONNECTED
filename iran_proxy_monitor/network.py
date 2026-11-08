"""Conservative outbound-route detection for the GUI's automatic scheduler.

This detects *definite* missing IPv4/IPv6 network routes, NOT whether a given
website is reachable. A timeout, refused connection or censorship is treated
as route-present, so constrained networks are not incorrectly marked offline.
Never use this to mark individual proxy nodes as unreachable.
"""
from __future__ import annotations
import errno
import socket

# Both POSIX and Winsock error numbers. EHOSTUNREACH might be a gateway ICMP
# response on a functioning interface; requiring both different targets/AFs
# to report these explicit errors is intentionally conservative.
_NO_ROUTE = {
    errno.ENETDOWN, errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL,
    errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT,
    10050, 10051, 10065, 10049, 10047, 10043,
}


def outbound_route_present(timeout: float = 0.6) -> bool:
    """True on any routable attempt; False only when ALL probes have no route.

    TCP connect_ex requires no DNS and returns quickly when the OS has no route.
    Reaching (or being blocked by) the remote peer both count as a route, and
    a timeout is inconclusive (fail-open). No HTTP payload is requested.
    """
    endpoints = (
        (socket.AF_INET, ('1.1.1.1', 443)),
        (socket.AF_INET, ('9.9.9.9', 443)),
        (socket.AF_INET6, ('2606:4700:4700::1111', 443, 0, 0)),
    )
    for family, endpoint in endpoints:
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex(endpoint)
                if result not in _NO_ROUTE:
                    return True
        except socket.timeout:
            return True  # blocked or stalled != confirmed offline
        except OSError as exc:
            if exc.errno not in _NO_ROUTE:
                return True
    return False
