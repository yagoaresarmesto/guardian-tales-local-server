# SPDX-License-Identifier: Apache-2.0
"""Observed 3.57.0 packet transport. No outbound connections or game API stubs."""

import secrets
import struct
from dataclasses import dataclass

from .packet_reader import (
    MAX_PACKET,
    PacketError,
    checksum,
    parse_packet,
    unwrap_compression,
    unwrap_frame,
)


@dataclass(frozen=True)
class Packet:
    packet_type: int
    body: bytes = b""
    version: int = 1
    reliable_type: int = 0
    result_type: int = 0
    body_type: int = 0
    sequence_id: int = 0
    api: str = ""
    error: str = ""
    hint: str = ""


def encode_text(value):
    value = value.encode("utf-8")
    if len(value) > 65536:
        raise PacketError("String exceeds supported length")
    n = len(value)
    prefix = bytearray()
    while n >= 128:
        prefix.append((n & 127) | 128)
        n >>= 7
    prefix.append(n)
    return bytes(prefix) + value


def encode_packet(packet):
    if packet.body and not packet.body_type:
        raise PacketError("A body requires a nonzero BodyType")
    if len(packet.body) > MAX_PACKET - 32:
        raise PacketError("Body too large")
    out = bytearray(
        struct.pack(
            "<HBBBBI",
            packet.version,
            packet.packet_type,
            packet.reliable_type,
            packet.result_type,
            packet.body_type,
            packet.sequence_id,
        )
    )
    out += encode_text(packet.api)
    if packet.result_type in (1, 2):
        out += encode_text(packet.error)
    out += encode_text(packet.hint)
    if packet.body_type:
        out += struct.pack("<I", len(packet.body)) + packet.body
    return bytes(out)


def wrap_uncompressed(packet):
    return struct.pack("<I", len(packet) + 4) + packet + struct.pack("<I", len(packet))


def encode_frame(payload, counter, nonce=None):
    if not 0 < len(payload) <= MAX_PACKET:
        raise PacketError("Frame payload outside supported length")
    nonce = secrets.randbelow(65535) if nonce is None else nonce
    if not 0 <= nonce <= 65535:
        raise PacketError("Nonce outside UInt16 range")
    nonce = nonce or 0x2193
    encoded = (len(payload) ^ (~counter)) & 0xFFFFFFFF
    out = bytearray(struct.pack("<HIH", 0, encoded, nonce))
    shift = nonce % len(payload)
    rotated = payload[shift:] + payload[:shift]
    seed = (nonce + (nonce >> 8)) & 255
    seed = seed or 0x6B
    for i, b in enumerate(rotated):
        out.append(((b + seed + 8 + i) & 255) ^ out[-1])
    struct.pack_into("<H", out, 0, checksum(out[2:]))
    return bytes(out)


def frame_length(header, counter, limit=1024 * 1024):
    if len(header) != 8:
        raise PacketError("Incomplete frame header")
    encoded = struct.unpack_from("<I", header, 2)[0]
    size = ((~(encoded ^ (counter & 0xFFFFFFFF))) & 0xFFFFFFFF) + 8
    if not 9 <= size <= limit:
        raise PacketError("Frame length or connection counter is invalid")
    return size


def decode_frame(frame, counter):
    return parse_packet(unwrap_compression(unwrap_frame(frame, counter)))


def encode_wire(packet, counter, nonce=None):
    return encode_frame(wrap_uncompressed(encode_packet(packet)), counter, nonce)


def make_pong(request, now_ms):
    if (
        request["version"] != 1
        or request["packet_type"] != 3
        or request["body_type"] != 2
        or request["body_length"] != 8
        or request["api"]
        or request["hint"]
        or request["result_type"] != 0
        or request["sequence_id"] != 0
        or request["reliable_type"] != 0
    ):
        raise PacketError("Only the observed keepalive request is implemented")
    return Packet(
        packet_type=4,
        body_type=2,
        body=bytes.fromhex(request["body_hex"]) + struct.pack("<q", now_ms),
    )
