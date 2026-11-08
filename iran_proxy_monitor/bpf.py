"""Official sing-box libbox ProfileContent v1 local (.bpf) envelope.

Reference: sing-box experimental/libbox/profile_import.go ProfileContent.Encode.
A single local profile contains a full sing-box JSON config with multiple outbounds.
"""
from __future__ import annotations

import gzip
import zlib
import io
import json
import struct

_HEADER = b'\x03\x01'  # MessageTypeProfileContent, version 1


def _uvarint(value: int) -> bytes:
    if value < 0:
        raise ValueError('Negative string length')
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def _string(value: str) -> bytes:
    data = value.encode('utf-8')
    return _uvarint(len(data)) + data


def create_bpf(name: str, config: dict) -> bytes:
    if not name or not isinstance(config, dict) or not isinstance(config.get('outbounds'), list):
        raise ValueError('A named sing-box configuration with outbounds is required')
    raw_json = json.dumps(config, ensure_ascii=False, indent=2)
    payload = _string(name) + struct.pack('>i', 0) + _string(raw_json)
    # A Go-style gzip header (mtime 0, XFL 0, OS 255) and default-level
    # DEFLATE stream. Compatible with libbox ProfileContent.Decode.
    compressor = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed = compressor.compress(payload) + compressor.flush(zlib.Z_FINISH)
    gzip_header = b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff'
    trailer = struct.pack('<II', zlib.crc32(payload) & 0xFFFFFFFF,
                          len(payload) & 0xFFFFFFFF)
    return _HEADER + gzip_header + compressed + trailer


def _read_string(buf):
    shift = 0
    length = 0
    for _ in range(10):
        b = buf.read(1)
        if not b:
            raise ValueError('Truncated BPF string length')
        length |= (b[0] & 127) << shift
        if b[0] < 128:
            break
        shift += 7
    else:
        raise ValueError('Oversized BPF varint')
    if length > 32 * 1024 * 1024:
        raise ValueError('BPF string too large')
    data = buf.read(length)
    if len(data) != length:
        raise ValueError('Truncated BPF string')
    return data.decode('utf-8')


def decode_bpf(data: bytes) -> tuple[str, dict]:
    """Roundtrip verifier for our local profiles, not a general-purpose BPF importer."""
    if not data.startswith(_HEADER):
        raise ValueError('Unrecognized BPF profile header')
    try:
        uncompressed = gzip.decompress(data[2:])
    except (OSError, EOFError) as exc:
        raise ValueError('Invalid BPF gzip payload') from exc
    reader = io.BytesIO(uncompressed)
    name = _read_string(reader)
    typ = reader.read(4)
    if len(typ) != 4 or struct.unpack('>i',typ)[0] != 0:
        raise ValueError('Expected local profile')
    cfg = json.loads(_read_string(reader))
    if reader.read(1):
        raise ValueError('Unexpected BPF trailing data')
    return name, cfg
