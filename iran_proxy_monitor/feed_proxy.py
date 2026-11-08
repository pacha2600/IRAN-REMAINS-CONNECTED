"""Subscription-only proxy transport. No proxy credentials are logged.

Supports direct, system, manual HTTP CONNECT and manual SOCKS5 with remote DNS.
The sing-box latency/download engine deliberately does not use this transport.
"""
from __future__ import annotations

import http.client
import socket
import ssl
from urllib.request import build_opener, ProxyHandler, HTTPHandler, HTTPSHandler
from urllib.parse import quote


MODES = ('system', 'direct', 'manual-http', 'manual-socks5')


def validate_proxy_settings(mode, host='', port=0, username='', password=''):
    if mode not in MODES:
        raise ValueError('Feed network must be system, direct, HTTP proxy, or SOCKS5 proxy.')
    if mode.startswith('manual-'):
        if not isinstance(host, str) or not host or any(c in host for c in '\r\n\t/@?#'):
            raise ValueError('Enter a valid proxy hostname/IP address (without a URL scheme).')
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError('Proxy port must be between 1 and 65535.')
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError('Invalid proxy authentication fields.')
        if len(username.encode('utf-8')) > 255 or len(password.encode('utf-8')) > 255:
            raise ValueError('Proxy username/password must each be at most 255 UTF-8 bytes.')
        if password and not username:
            raise ValueError('A proxy password needs a username.')


def _read_exact(sock, count):
    out = bytearray()
    while len(out) < count:
        chunk = sock.recv(count - len(out))
        if not chunk:
            raise OSError('SOCKS5 proxy closed the connection')
        out.extend(chunk)
    return bytes(out)


def socks5_connect(sock, target_host, target_port, username='', password=''):
    """SOCKS5 handshake using a domain-name target to avoid local DNS leakage."""
    methods = b'\x00\x02' if username else b'\x00'
    sock.sendall(b'\x05' + bytes([len(methods)]) + methods)
    version, method = _read_exact(sock, 2)
    if version != 5 or method == 255:
        raise OSError('SOCKS5 proxy refused authentication methods')
    if method == 2:
        if not username:
            raise OSError('SOCKS5 proxy requires authentication')
        u, p = username.encode('utf-8'), password.encode('utf-8')
        sock.sendall(b'\x01' + bytes([len(u)]) + u + bytes([len(p)]) + p)
        if _read_exact(sock, 2) != b'\x01\x00':
            raise OSError('SOCKS5 authentication failed')
    elif method != 0:
        raise OSError('Unsupported SOCKS5 authentication method')
    host = target_host.encode('idna')
    if len(host) > 255:
        raise ValueError('Target domain exceeds SOCKS5 limit')
    sock.sendall(b'\x05\x01\x00\x03' + bytes([len(host)]) + host + int(target_port).to_bytes(2,'big'))
    version, status, reserved, address_type = _read_exact(sock, 4)
    if version != 5 or status != 0:
        raise OSError(f'SOCKS5 proxy refused destination (code {status})')
    if address_type == 1:
        _read_exact(sock, 4)
    elif address_type == 3:
        _read_exact(sock, _read_exact(sock, 1)[0])
    elif address_type == 4:
        _read_exact(sock, 16)
    else:
        raise OSError('Malformed SOCKS5 proxy reply')
    _read_exact(sock, 2)


class _SocksMixin:
    def __init__(self, *args, proxy_host, proxy_port, proxy_username='', proxy_password='', **kwargs):
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._proxy_username = proxy_username
        self._proxy_password = proxy_password
        super().__init__(*args, **kwargs)

    def _connect_socks(self):
        sock = socket.create_connection((self._proxy_host, self._proxy_port),
                                        self.timeout, self.source_address)
        try:
            socks5_connect(sock, self.host, self.port, self._proxy_username, self._proxy_password)
            return sock
        except BaseException:
            sock.close()
            raise


class Socks5HTTPSConnection(_SocksMixin, http.client.HTTPSConnection):
    def connect(self):
        raw = self._connect_socks()
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class Socks5HTTPConnection(_SocksMixin, http.client.HTTPConnection):
    def connect(self):
        self.sock = self._connect_socks()


class Socks5HTTPSHandler(HTTPSHandler):
    def __init__(self, host, port, username='', password=''):
        super().__init__()
        self.proxy_settings = (host, port, username, password)

    def https_open(self, req):
        host, port, user, password = self.proxy_settings
        return self.do_open(lambda target, **kw: Socks5HTTPSConnection(
            target, proxy_host=host, proxy_port=port,
            proxy_username=user, proxy_password=password,
            # Python 3.13+ no longer exposes HTTPSHandler._check_hostname.
            # HTTPSConnection uses the supplied SSLContext for verification.
            # Avoid relying on private urllib handler attributes that change
            # between Windows Python releases (including Python 3.15).
            context=self._context, **kw), req)


class Socks5HTTPHandler(HTTPHandler):
    def __init__(self, host, port, username='', password=''):
        super().__init__()
        self.proxy_settings = (host, port, username, password)

    def http_open(self, req):
        host, port, user, password = self.proxy_settings
        return self.do_open(lambda target, **kw: Socks5HTTPConnection(
            target, proxy_host=host, proxy_port=port,
            proxy_username=user, proxy_password=password, **kw), req)


def build_feed_opener(mode='system', host='', port=0, username='', password=''):
    """Build a subscription-only urllib opener. No system settings are changed."""
    validate_proxy_settings(mode, host, port, username, password)
    if mode == 'direct':
        return build_opener(ProxyHandler({}))
    if mode == 'system':
        return build_opener(ProxyHandler())
    if mode == 'manual-socks5':
        return build_opener(ProxyHandler({}), Socks5HTTPHandler(host, port, username, password),
                            Socks5HTTPSHandler(host, port, username, password))
    authority = host if ':' not in host else f'[{host}]'
    if username:
        authority = f'{quote(username, safe="")}:{quote(password, safe="")}@{authority}'
    url = f'http://{authority}:{port}'
    return build_opener(ProxyHandler({'http':url, 'https':url}))
