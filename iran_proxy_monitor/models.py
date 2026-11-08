from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json

@dataclass
class Node:
    name: str
    protocol: str
    outbound: dict
    source_kind: str
    source_text: str = ''
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    id: str = ''

    def __post_init__(self):
        if not self.id:
            canonical = ({k:v for k,v in self.outbound.items() if k != 'tag'}
                         if self.outbound else {'unsupported_source':self.source_text,'kind':self.source_kind})
            self.id = hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False,
                                                separators=(',',':')).encode('utf-8')).hexdigest()[:24]
        self.name = self.name[:125] or self.protocol

    @property
    def supported(self):
        return not self.problems and bool(self.outbound)

    def labeled_outbound(self, tag: str):
        return {**self.outbound, 'tag':tag}

@dataclass
class Probe:
    node_id: str
    ok: bool
    latency_ms: float | None = None
    error: str = ''
    endpoint: str = ''
    bytes_received: int = 0  # response BODY only (strict probes read no body)
    http_sent_bytes: int = 0  # origin-facing plaintext HTTPS request; excludes TLS
    http_received_bytes: int = 0  # HTTPS response headers (may be partial)

@dataclass
class Speed:
    node_id: str
    mbps: float = 0.0
    bytes_received: int = 0
    seconds: float = 0.0
    ok: bool = False
    error: str = ''
    endpoint: str = ''
    verified: bool = False  # long enough sustained observation, not just a short burst
    stalled: bool = False
    time_to_first_byte_ms: float = 0.0
    # Conservative lower-quartile two-second transfer rate, including empty
    # seconds. None is retained only for legacy/injected measurements.
    flow_mbps: float | None = None
    flow_active_ratio: float | None = None
    max_idle_seconds: float = 0.0

@dataclass
class Result:
    node: Node
    probe: Probe
    prelim: Speed | None = None
    confirm: Speed | None = None
    rank_score: float = 0.0
    reliability: float = 0.0

    @property
    def mbps(self):
        # Ranking never treats a brief preliminary burst as verified throughput.
        return self.confirm.mbps if self.confirm and self.confirm.ok else (self.prelim.mbps if self.prelim and self.prelim.ok else 0.0)

    @property
    def verified(self):
        return bool(self.confirm and self.confirm.ok and self.confirm.verified)

    @property
    def best_validated_mbps(self):
        if not self.verified:
            return 0.0
        # New real measurements are scored by their lower-percentile rate,
        # never the mean inflated by a short burst. Legacy injected Speed
        # objects without flow sampling retain their previous behavior.
        return self.confirm.flow_mbps if self.confirm.flow_mbps is not None else self.confirm.mbps
