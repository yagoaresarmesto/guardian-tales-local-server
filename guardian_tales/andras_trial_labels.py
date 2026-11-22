# SPDX-License-Identifier: Apache-2.0
"""Optional in-memory English CDN title; original resources remain untouched."""

import base64
import hashlib
import struct
import zlib
from functools import lru_cache

from .andras_trial_static import ENTRY, HEADER, binary_rows
from .raid_custom import binary_name_hash
from .raid_static import compress
from .reference import ReferenceData

KEY = "demon_slayer_leader_skill"
TITLE = "Sovereign of Eternal Slaughter"
MAX_SOURCE = 8 * 1024 * 1024


def cipher(key, iv):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as error:
        raise ValueError(
            'Install the optional hero-trials dependencies: pip install ".[hero-trials]"'
        ) from error
    return Cipher(algorithms.AES(key), modes.CBC(iv))


def filename(source_sha256):
    return "andras-trial-strings-" + source_sha256 + ".key"


@lru_cache(maxsize=2)
def string_table(source, active):
    if not 16 <= len(source) <= MAX_SOURCE:
        raise ValueError("Invalid original English string table size")
    rows = binary_rows(base64.b64encode(source).decode(), require_id=False, max_count=500000)
    strings = {name_hash: raw for _, name_hash, raw in rows}
    if len(strings) != len(rows) or any(
        strings.get(binary_name_hash(key)) != value
        for key, value in {
            "name_demon_slayer": b"Andras",
            "demon_slayer_support_skill": b"Cold Death",
            "dokkaebi_myth_leader_skill": b"Nimbus",
        }.items()
    ):
        raise ValueError("Andras title requires the matching original English string table")
    # The input is the original decoded matching table, never a patched copy.
    hashed = binary_name_hash(KEY)
    if any(name_hash == hashed for _, name_hash, _ in rows):
        raise ValueError("The original English table already defines the trial leader title")
    if not active:
        return source
    ident = max(row[0] for row in rows) + 1
    if ident > 0xFFFFFFFF:
        raise ValueError("No native string identifier remains for the trial leader title")
    magic, version, count, blocks = HEADER.unpack_from(source)
    if blocks >= 65535:
        raise ValueError("No native block remains for the trial leader title")
    end = HEADER.size + count * ENTRY.size
    start = (end + blocks * 2 + 3) & ~3
    payload = TITLE.encode()
    chunk = compress(payload)
    # Preserve every stock index entry and compressed block byte-for-byte.
    result = bytearray(HEADER.pack(magic, version, count + 1, blocks + 1))
    result.extend(source[HEADER.size : end])
    result.extend(ENTRY.pack(ident, hashed, blocks, len(payload)))
    result.extend(source[end : end + blocks * 2])
    result.extend(struct.pack("<H", len(chunk)))
    result.extend(b"\0" * (-len(result) % 4))
    result.extend(source[start:])
    result.extend(chunk)
    return bytes(result)


def decode_resource(source, key):
    if len(key) != 32 or not 32 <= len(source) <= MAX_SOURCE or len(source) % 16:
        raise ValueError("Invalid Andras English resource envelope")
    decryptor = cipher(key, source[:16]).decryptor()
    padded = decryptor.update(source[16:]) + decryptor.finalize()
    padding = padded[-1]
    if not 1 <= padding <= 16 or padded[-padding:] != bytes([padding]) * padding:
        raise ValueError("Invalid Andras English resource padding")
    inflater = zlib.decompressobj(-15)
    try:
        raw = inflater.decompress(padded[:-padding], MAX_SOURCE + 1)
    except zlib.error as error:
        raise ValueError("Invalid Andras English resource compression") from error
    if len(raw) > MAX_SOURCE or not inflater.eof or inflater.unused_data:
        raise ValueError("Invalid Andras English resource length")
    return raw


@lru_cache(maxsize=2)
def resource(source, key):
    changed = string_table(decode_resource(source, key), True)
    compressor = zlib.compressobj(level=9, wbits=-15)
    compressed = compressor.compress(changed) + compressor.flush()
    padding = 16 - len(compressed) % 16
    padded = compressed + bytes([padding]) * padding
    # The final four IV bytes encode the native content version/key selector.
    # Use a different prefix for this distinct payload, retaining that selector.
    iv = hashlib.sha256(b"local-andras-title-v1\n" + changed).digest()[:12] + source[12:16]
    encryptor = cipher(key, iv).encryptor()
    return iv + encryptor.update(padded) + encryptor.finalize()


def cdn_override(directory, path, source_sha256):
    if directory is None or path.name != "strings-bin-enUS" or path.parent.name != "static_data":
        return None
    from .andras_trial import load

    references = ReferenceData(directory)
    selection = load(references)
    if selection is None or not selection["active"]:
        return None
    key_path = references.directory / filename(selection["source_sha256"])
    if not key_path.exists():
        return None
    if (
        not key_path.is_file()
        or key_path.stat().st_size > 128
        or hashlib.sha256(references.read_bytes("static_data_get.bin")).hexdigest()
        != selection["source_sha256"]
    ):
        raise ValueError("Invalid Andras English resource binding")
    text = key_path.read_text(encoding="ascii").strip()
    if len(text) != 64 or any(c not in "0123456789abcdefABCDEF" for c in text):
        raise ValueError("Invalid private Andras resource key")
    if not 32 <= path.stat().st_size <= MAX_SOURCE:
        raise ValueError("Invalid original English resource size")
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != source_sha256:
        raise ValueError("Original English resource differs from its manifest")
    return resource(source, bytes.fromhex(text))
