"""Conservative, static *configuration* assessment of the proxy hop.

No network attack test or operator trust audit is performed here. The score is
NOT a measure of anonymity, leak resistance, legitimacy, or end-to-end HTTPS.
Never treat unknown protocols as confirmed cleartext.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SecurityAssessment:
    encryption: str
    score: int | None
    explanation: str
    encrypted: bool | None

    @property
    def ranking_factor(self) -> float:
        # Ranking penalty only; this does NOT modify latency/download evidence.
        if self.score is None:
            return 0.78  # unassessed is not assumed safe
        if self.score < 20:
            return 0.35
        if self.score < 50:
            return 0.60
        if self.score < 70:
            return 0.78
        if self.score < 85:
            return 0.91
        return 1.0


def assess_outbound(outbound: dict | None) -> SecurityAssessment:
    if not isinstance(outbound,dict) or not outbound.get('type'):
        return SecurityAssessment('Unassessed',None,'No usable sing-box outbound configuration.',None)
    protocol=str(outbound['type']).casefold()
    tls=outbound.get('tls') if isinstance(outbound.get('tls'),dict) else {}
    reality=tls.get('reality') if isinstance(tls.get('reality'),dict) else {}
    tls_on=bool(tls.get('enabled') is True or reality.get('enabled') is True)
    insecure=bool(tls.get('insecure') is True)
    name=''
    score=None
    encrypted=None
    reason=''
    if protocol in ('vless','trojan'):
        if tls_on:
            name='REALITY/TLS' if reality.get('enabled') else 'TLS'
            score=94 if reality.get('enabled') else 92
            encrypted=True
            reason='Configured TLS transport; VLESS alone does not encrypt its proxy hop.' if protocol=='vless' else 'Trojan configured with TLS transport.'
        else:
            name='No hop encryption'
            score=5
            encrypted=False
            reason=f'{protocol.upper()} outbound has no enabled TLS; HTTPS websites may still use their own encryption.'
    elif protocol=='shadowsocks':
        method=str(outbound.get('method','')).lower()
        if method=='none':
            name='None (Shadowsocks)';score=5;encrypted=False
            reason='Shadowsocks method none does not protect the proxy hop.'
        elif method.startswith('2022-blake3-'):
            name='Shadowsocks 2022 AEAD';score=91;encrypted=True
            reason='Modern Shadowsocks 2022 authenticated encryption is configured.'
        elif method in ('aes-128-gcm','aes-192-gcm','aes-256-gcm','chacha20-ietf-poly1305','xchacha20-ietf-poly1305'):
            name='Shadowsocks AEAD';score=84;encrypted=True
            reason='AEAD encryption configured. The node operator remains able to observe proxied destination traffic and metadata.'
        elif method:
            name='Legacy/unknown cipher';score=35;encrypted=None
            reason='Cipher is not on this assessment’s modern AEAD allowlist; avoid assuming adequate hop protection.'
        else:
            name='Unassessed cipher';score=None;encrypted=None
            reason='Shadowsocks cipher is missing; cannot grade the encryption configuration.'
    elif protocol=='vmess':
        method=str(outbound.get('security','auto')).casefold()
        if method in ('none','zero'):
            if tls_on:
                name='TLS (VMess cipher off)';score=86;encrypted=True
                reason='TLS provides the configured hop encryption, but VMess payload cipher is disabled.'
            else:
                name='No hop encryption';score=5;encrypted=False
                reason='VMess payload cipher disabled and no TLS transport configured.'
        elif method in ('auto','aes-128-gcm','chacha20-poly1305'):
            if tls_on:
                name='VMess AEAD + TLS';score=91;encrypted=True
                reason='VMess authenticated encryption with an additional TLS layer.'
            else:
                name='VMess AEAD';score=77;encrypted=True
                reason='VMess payload encryption configured without a separate TLS outer transport.'
        elif method in ('aes-128-ctr',):
            name='VMess legacy cipher'+(' + TLS' if tls_on else '')
            score=83 if tls_on else 42;encrypted=True
            reason='Legacy VMess payload cipher; TLS mitigates transport confidentiality concerns.'
        else:
            name='VMess cipher unassessed';score=None;encrypted=None
            reason='Unrecognized VMess security setting.'
    elif protocol in ('hysteria','hysteria2','tuic','naive','anytls'):
        name=f'{protocol.upper()} TLS';score=92;encrypted=True
        reason=f'{protocol} is a TLS-based proxy protocol; this checks configuration only.'
    elif protocol=='wireguard':
        name='WireGuard';score=94;encrypted=True
        reason='WireGuard uses authenticated encrypted tunneling; peer/operator trust is not verified.'
    elif protocol=='ssh':
        name='SSH';score=84;encrypted=True
        reason='SSH encrypts the hop; host-key checking must be reviewed separately.'
    elif protocol in ('socks','http'):
        if tls_on:
            name='TLS proxy';score=87;encrypted=True
            reason='TLS configured to the proxy server. Browser-to-site HTTPS is a separate layer.'
        else:
            name='Plain '+protocol.upper();score=5;encrypted=False
            reason='No encrypted tunnel to the upstream proxy. HTTPS websites remain encrypted to the origin.'
    else:
        name='Unassessed '+protocol;score=None;encrypted=None
        reason='Unknown proxy protocol: do not infer that its upstream link is encrypted or cleartext.'
    if insecure and tls_on:
        score=max(0,score-35) if score is not None else None
        name+=' (unverified cert)'
        reason+=' TLS certificate checking is DISABLED; impersonation is possible.'
    elif insecure:
        # Flag unsafe options even when TLS is disabled, for review.
        reason+=' TLS insecure=true is present but no active TLS was identified.'
    return SecurityAssessment(name,score,reason,encrypted)
