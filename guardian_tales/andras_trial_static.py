# SPDX-License-Identifier: Apache-2.0
"""Data-only Andras Myth prototype, retaining the original combat/visual assets."""

import base64
import copy
import json
import struct
from datetime import datetime
from functools import lru_cache

from .raid_custom import binary_name_hash
from .raid_static import compress, decode, digest, records

SOURCE = 490
ORIGIN = 488
VARIANT = 20488
STONE = 85488
NAME = "demon_slayer_6"
HEADER = struct.Struct("<4sIII")
ENTRY = struct.Struct("<IQHH")


def same_definition(left, right):
    if left.keys() != right.keys():
        return False
    for key in left:
        if left[key] == right[key]:
            continue
        if (
            key not in ("DateFrom", "DateTo")
            or not isinstance(left[key], dict)
            or not isinstance(right[key], dict)
            or left[key].keys() != right[key].keys()
        ):
            return False
        for region, value in left[key].items():
            other = right[key][region]
            if value != other and (
                not isinstance(value, str)
                or not isinstance(other, str)
                or datetime.fromisoformat(value) != datetime.fromisoformat(other)
            ):
                return False
    return True


def binary_rows(encoded, *, require_id=True, max_count=10000):
    data = base64.b64decode(encoded, validate=True)
    if len(data) < HEADER.size:
        raise ValueError("Missing native hero binary header")
    magic, version, count, blocks = HEADER.unpack_from(data)
    end = HEADER.size + count * ENTRY.size
    start = (end + blocks * 2 + 3) & ~3
    if (
        magic != b"k1ng"
        or version != 1
        or not 1 <= count <= max_count
        or not 1 <= blocks <= count
        or start > len(data)
    ):
        raise ValueError("Invalid native hero binary layout")
    lengths = struct.unpack_from("<" + "H" * blocks, data, end)
    if start + sum(lengths) != len(data):
        raise ValueError("Invalid native hero binary block lengths")
    chunks = []
    for length in lengths:
        chunks.append(decode(data[start : start + length]))
        start += length
    offsets = [0] * blocks
    result = []
    for ident, name_hash, block, length in ENTRY.iter_unpack(data[HEADER.size : end]):
        if block >= blocks or not length:
            raise ValueError("Invalid hero binary record reference")
        offset = offsets[block]
        raw = chunks[block][offset : offset + length]
        offsets[block] += length
        if len(raw) != length or (require_id and json.loads(raw).get("Id") != ident):
            raise ValueError("Hero binary record does not match its index")
        result.append((ident, name_hash, raw))
    if offsets != list(map(len, chunks)) or len({r[0] for r in result}) != count:
        raise ValueError("Ambiguous hero binary records")
    return result


def pack_rows(rows):
    index, chunks, pending = [], [], bytearray()
    for ident, name_hash, raw in rows:
        if not 0 < len(raw) <= 64000:
            raise ValueError("Trial hero exceeds the native record limit")
        if len(pending) + len(raw) > 64000:
            chunks.append(compress(bytes(pending)))
            pending.clear()
        index.append(ENTRY.pack(ident, name_hash, len(chunks), len(raw)))
        pending.extend(raw)
    if pending:
        chunks.append(compress(bytes(pending)))
    if not chunks or any(len(chunk) > 65535 for chunk in chunks):
        raise ValueError("Trial hero exceeds the native block limit")
    prefix = HEADER.pack(b"k1ng", 1, len(rows), len(chunks)) + b"".join(index)
    prefix += struct.pack("<" + "H" * len(chunks), *map(len, chunks))
    return base64.b64encode(prefix + b"\0" * (-len(prefix) % 4) + b"".join(chunks)).decode()


@lru_cache(maxsize=2)
def definitions(body):
    tables = records(decode(body))[1]
    if not {"heroes", "heroes-bin", "items", "__checksum__"} <= tables.keys():
        raise ValueError("Andras trial requires matching hero and item static tables")
    heroes = json.loads(tables["heroes"][1])
    items = json.loads(tables["items"][1])
    if (
        not isinstance(heroes, list)
        or not isinstance(items, list)
        or any(not isinstance(row, dict) for row in heroes + items)
    ):
        raise ValueError("Invalid Andras trial source definitions")
    source = [row for row in heroes if row.get("Id") == SOURCE]
    if (
        len(source) != 1
        or any(
            source[0].get(key) != value
            for key, value in {
                "Name": "demon_slayer_5",
                "OriginId": ORIGIN,
                "Rank": 4,
                "Class": "demon_slayer",
                "MythStoneId": 0,
            }.items()
        )
        or source[0].get("MythTo")
    ):
        raise ValueError("The original non-Myth five-star Andras is required")
    if any(row.get("Id") == VARIANT or row.get("Name") == NAME for row in heroes) or any(
        row.get("Id") == STONE for row in items
    ):
        raise ValueError("Andras trial identifiers collide with the supplied content")
    stone_templates = [
        row
        for row in items
        if row.get("Type") == "evolve_stone"
        and row.get("StoneType") == "HeroMyth"
        and row.get("SpriteName")
    ]
    if not stone_templates:
        raise ValueError("Andras trial requires an existing Myth stone icon")
    binary = binary_rows(tables["heroes-bin"][1])
    actual = {ident: json.loads(raw) for ident, _, raw in binary}
    if actual.keys() != {row["Id"] for row in heroes} or any(
        not same_definition(row, actual[row["Id"]]) for row in heroes
    ):
        raise ValueError("Hero JSON and binary definitions do not agree")
    from .andras_trial_growth import overlay

    return heroes, items, source[0], stone_templates[0], binary, overlay(tables)


@lru_cache(maxsize=2)
def prepare(body, generation, active):
    from .andras_trial_growth import LEADER, TABLES

    lines, tables = records(decode(body))
    values = {
        name: tables[name][1]
        for name in ("heroes", "heroes-bin", "items", *TABLES)
        if name in tables
    }
    if active:
        heroes, items, source, template, binary, growth = definitions(body)
        values.update(growth)
        updated = copy.deepcopy(source)
        updated["MythTo"] = {"KakaoGlobal": VARIANT}
        updated["MythStoneId"] = STONE
        variant = copy.deepcopy(source)
        variant.update(
            Id=VARIANT, Name=NAME, Rank=6, Options=[{"OptionId": LEADER}, *source["Options"]]
        )
        variant.pop("MythTo", None)
        stone = copy.deepcopy(template)
        stone.update(Id=STONE, Name="local_trial_myth_stone_demon_slayer")
        heroes = [updated if row["Id"] == SOURCE else row for row in heroes] + [variant]
        values["heroes"] = json.dumps(heroes, ensure_ascii=False, separators=(",", ":"))
        values["items"] = json.dumps(items + [stone], ensure_ascii=False, separators=(",", ":"))
        binary_source = json.loads(next(raw for ident, _, raw in binary if ident == SOURCE))
        binary_updated = dict(binary_source, MythTo={"KakaoGlobal": VARIANT}, MythStoneId=STONE)
        binary_variant = dict(
            binary_source,
            Id=VARIANT,
            Name=NAME,
            Rank=6,
            Options=[{"OptionId": LEADER}, *binary_source["Options"]],
        )
        binary_variant.pop("MythTo", None)
        replacement = json.dumps(binary_updated, ensure_ascii=False, separators=(",", ":")).encode()
        payload = json.dumps(binary_variant, ensure_ascii=False, separators=(",", ":")).encode()
        try:
            name_hash = binary_name_hash(NAME)
        except ValueError as error:
            raise ValueError(
                'Install the optional hero-trials dependencies: pip install ".[hero-trials]"'
            ) from error
        if name_hash in {row[1] for row in binary}:
            raise ValueError("Andras trial name collides with the native binary index")
        values["heroes-bin"] = pack_rows(
            [
                (ident, old_hash, replacement if ident == SOURCE else raw)
                for ident, old_hash, raw in binary
            ]
            + [(VARIANT, name_hash, payload)]
        )
    revision = max(tables[name][2] for name in (*values, "__checksum__")) + generation + 2
    if (
        type(generation) is not int
        or not 1 <= generation <= 0x7FFFFFFF
        or revision > 0x7FFFFFFF
        or type(active) is not bool
    ):
        raise ValueError("Invalid Andras trial static generation")
    checksum = digest(
        b"local-andras-myth-trial-v3\n"
        + tables["__checksum__"][1].encode()
        + b"\n"
        + str(generation).encode()
        + b"\n"
        + b"\n".join(value.encode() for value in values.values())
    )
    for name, content in (*values.items(), ("__checksum__", checksum)):
        at = tables[name][0]
        actual = (
            base64.b64decode(content, validate=True) if name.endswith("-bin") else content.encode()
        )
        lines[at : at + 4] = [
            name + "\n",
            content + "\n",
            str(revision) + "\n",
            digest(actual) + "\n",
        ]
    return compress("".join(lines).encode()), checksum
