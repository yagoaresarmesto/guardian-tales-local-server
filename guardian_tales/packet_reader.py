# SPDX-License-Identifier: Apache-2.0
"""Offline reader for the observed Guardian Tales 3.57.0 native packet path.

Reads local files only. The outer raw LZ4 wrapper is supported and bounded.
API JSON and the separate body-level LZ4 encoding are handled by bootstrap.py.
"""

import argparse
import json
import struct
from datetime import datetime, timezone
from pathlib import Path

MAX_PACKET = 16 * 1024 * 1024


class PacketError(ValueError):
    pass


def checksum(data):
    value = 0xF208
    for b in data:
        value = (value * 257 + b + 1) & 0xFFFF
    return value


def unwrap_frame(data, counter):
    if len(data) < 9:
        raise PacketError("Frame is shorter than its header and payload")
    expected, encoded, nonce = struct.unpack_from("<HIH", data)
    size = (~(encoded ^ (counter & 0xFFFFFFFF))) & 0xFFFFFFFF
    if not 0 < size <= MAX_PACKET or size + 8 != len(data):
        raise PacketError("Frame length/counter mismatch")
    if checksum(data[2:]) != expected:
        raise PacketError("Frame checksum mismatch")
    seed = (nonce + (nonce >> 8)) & 0xFF
    seed = seed or 0x6B
    rotated = bytearray(size)
    for i in range(size):
        pos = i + 8
        rotated[i] = ((data[pos] ^ data[pos - 1]) - seed - pos) & 0xFF
    shift = nonce % size
    return bytes(rotated[size - shift :] + rotated[: size - shift])


def unwrap_compression(data):
    if len(data) < 8:
        raise PacketError("Compression envelope is too short")
    boundary = struct.unpack_from("<I", data)[0]
    if boundary < 4 or boundary + 4 != len(data):
        raise PacketError("Compression envelope length mismatch")
    stored = data[4:boundary]
    original = struct.unpack_from("<I", data, boundary)[0]
    if original > MAX_PACKET:
        raise PacketError("Original packet exceeds the reader limit")
    return stored if len(stored) == original else lz4_block(stored, original)


def lz4_block(data, expected, *, limit=MAX_PACKET):
    """Decode a bounded raw LZ4 block; no frame container or external library."""
    out = bytearray()
    read_lz4_sequences(data, expected, limit=limit, output=out)
    return bytes(out)


def read_lz4_sequences(data, expected, *, limit, output=None):
    """Validate the block and optionally expand its sequences into an empty bytearray."""
    if not 0 <= expected <= limit:
        raise PacketError("LZ4 output size outside reader limits")
    at = 0
    size = 0
    end = len(data)

    def extended():
        nonlocal at
        length = 15
        while True:
            if at >= end:
                raise PacketError("Truncated LZ4 length")
            b = data[at]
            at += 1
            length += b
            if length > expected:
                raise PacketError("LZ4 length exceeds expected output")
            if b != 255:
                return length

    while at < end:
        token = data[at]
        at += 1
        literal = token >> 4
        if literal == 15:
            literal = extended()
        size += literal
        if at + literal > end or size > expected:
            raise PacketError("LZ4 literal exceeds input/output bounds")
        if output is not None:
            output += data[at : at + literal]
        at += literal
        if at == end:
            break
        if at + 2 > end:
            raise PacketError("Truncated LZ4 match offset")
        offset = data[at] | (data[at + 1] << 8)
        at += 2
        match = token & 15
        if match == 15:
            match = extended()
        match += 4
        if not offset or offset > size or size + match > expected:
            raise PacketError("Invalid LZ4 match")
        if output is not None:
            if offset >= match:
                start = size - offset
                output += output[start : start + match]
            else:
                for _ in range(match):
                    output.append(output[-offset])
        size += match
    if size != expected:
        raise PacketError("LZ4 output length mismatch")


def parse_packet(data):
    if not 10 <= len(data) <= MAX_PACKET:
        raise PacketError("Packet length outside reader limits")
    version, packet_type, reliable_type, result_type, body_type, sequence_id = struct.unpack_from(
        "<HBBBBI", data
    )
    at = 10

    def text():
        nonlocal at
        count = 0
        for shift in range(0, 35, 7):
            if at >= len(data):
                raise PacketError("Truncated string length")
            byte = data[at]
            at += 1
            if shift == 28 and byte > 7:
                raise PacketError("String length is negative or overflows Int32")
            count |= (byte & 127) << shift
            if not byte & 128:
                break
        else:
            raise PacketError("Invalid 7-bit string length")
        if count > 65536 or at + count > len(data):
            raise PacketError("String exceeds input or reader limits")
        try:
            value = data[at : at + count].decode("utf-8")
        except UnicodeError as e:
            raise PacketError("Invalid UTF-8 string") from e
        at += count
        return value

    api = text()
    error = text() if result_type in (1, 2) else None
    hint = text()
    body = b""
    if body_type:
        if at + 4 > len(data):
            raise PacketError("Truncated body length")
        n = struct.unpack_from("<I", data, at)[0]
        at += 4
        if n > MAX_PACKET or at + n > len(data):
            raise PacketError("Body exceeds input or reader limits")
        body = data[at : at + n]
        at += n
    if at != len(data):
        raise PacketError(f"Unconsumed bytes: {len(data)-at}")
    result = dict(
        version=version,
        packet_type=packet_type,
        reliable_type=reliable_type,
        result_type=result_type,
        body_type=body_type,
        sequence_id=sequence_id,
        api=api,
        error=error,
        hint=hint,
        body_length=len(body),
        body_hex=body.hex(),
        bytes_consumed=at,
        bytes_total=len(data),
    )
    if packet_type in (3, 4):
        result["packet_type_name"] = "Ping" if packet_type == 3 else "Pong"
        if body_type == 2 and len(body) in (8, 16):
            values = struct.unpack("<" + "q" * (len(body) // 8), body)
            # Expose the interpretation only for plausible contemporary epochs.
            if all(946684800000 <= v < 4102444800000 for v in values):
                result["keepalive_timestamps_utc"] = [
                    datetime.fromtimestamp(v / 1000, timezone.utc).isoformat() for v in values
                ]
    return result


def decode(data, layer="packet", counter=None):
    if layer == "frame":
        if counter is None:
            raise PacketError("Frame decoding requires --counter")
        data = unwrap_frame(data, counter)
    if layer in ("frame", "envelope"):
        data = unwrap_compression(data)
    return parse_packet(data)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read a local packet file without connecting to any server."
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--layer", choices=["packet", "envelope", "frame"], default="packet")
    parser.add_argument("--counter", type=lambda x: int(x, 0))
    args = parser.parse_args(argv)
    try:
        if args.file.stat().st_size > MAX_PACKET + 16:
            raise PacketError("Input file exceeds the reader limit")
        result = decode(args.file.read_bytes(), args.layer, args.counter)
    except (PacketError, OSError) as e:
        parser.exit(2, "Error: " + str(e) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
