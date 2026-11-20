# SPDX-License-Identifier: Apache-2.0
"""Prepare local Raid calendar and boss data from immutable external tables."""

import base64
import hashlib
import json
import os
import struct
import tempfile
import time
from array import array

from .packet_reader import MAX_PACKET, lz4_block

MAX_STATIC = 64 * 1024 * 1024
LOCAL_FROM = "2000-01-01T00:00:00+00:00"
LOCAL_TO = "2099-12-24T23:59:59+00:00"
LOCAL_REWARD_UNTIL = "2099-12-31T23:59:59+00:00"
MANIFEST_KEYS = {"static_data_sha256", "static_data_checksum", "static_data_revision"}


def atomic_replace(source, target):
    """Keep atomic publication while tolerating brief Windows sharing locks."""
    for attempt in range(6):
        try:
            return os.replace(source, target)
        except PermissionError as error:
            if getattr(error, "winerror", None) not in (32, 33) or attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def digest(data):
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


def record_bytes(name, content):
    return base64.b64decode(content, validate=True) if name.endswith("-bin") else content.encode()


def compress(data):
    """Encode a bounded raw LZ4 block with a fixed-size match table."""
    if not 0 < len(data) <= MAX_STATIC:
        raise ValueError("Static table text exceeds its preparation limit")
    out = bytearray()
    positions = array("i", [-1]) * 65536
    anchor = at = 0
    end = len(data) - 5

    def extra(length):
        while length >= 255:
            out.append(255)
            length -= 255
        out.append(length)

    while at <= len(data) - 12:
        word = struct.unpack_from("<I", data, at)[0]
        key = ((word * 2654435761) & 0xFFFFFFFF) >> 16
        previous = positions[key]
        positions[key] = at
        if (
            previous < 0
            or at - previous > 65535
            or data[previous : previous + 4] != data[at : at + 4]
        ):
            at += 1
            continue
        length = 4
        while (
            at + length + 64 <= end
            and data[previous + length : previous + length + 64]
            == data[at + length : at + length + 64]
        ):
            length += 64
        while at + length < end and data[previous + length] == data[at + length]:
            length += 1
        literals = at - anchor
        out.append((min(literals, 15) << 4) | min(length - 4, 15))
        if literals >= 15:
            extra(literals - 15)
        out.extend(data[anchor:at])
        out.extend(struct.pack("<H", at - previous))
        if length >= 19:
            extra(length - 19)
        at += length
        anchor = at
    literals = len(data) - anchor
    out.append(min(literals, 15) << 4)
    if literals >= 15:
        extra(literals - 15)
    out.extend(data[anchor:])
    out.extend(struct.pack("<I", len(data)))
    if len(out) > MAX_PACKET - 1024:
        raise ValueError("Prepared static tables exceed the existing packet limit")
    return bytes(out)


def decode(body):
    if not 5 <= len(body) <= MAX_PACKET:
        raise ValueError("Invalid external static table body size")
    expected = struct.unpack("<I", body[-4:])[0]
    return lz4_block(body[:-4], expected, limit=MAX_STATIC)


def records(raw):
    lines = raw.decode("utf-8").splitlines(keepends=True)
    result = {}
    for at in range(0, len(lines), 4):
        if all(not line.strip() for line in lines[at:]):
            break
        if at + 3 >= len(lines):
            raise ValueError("Incomplete static table record")
        name, content, version, checksum = (s.rstrip("\r\n") for s in lines[at : at + 4])
        if not name or name in result or digest(record_bytes(name, content)) != checksum:
            raise ValueError("Invalid static table name or content checksum")
        revision = int(version)
        if not 0 <= revision <= 0x7FFFFFFF:
            raise ValueError("Invalid static table revision")
        result[name] = (at, content, revision)
    return lines, result


def prepare(references, season, previous_revision=0, *, lineup=None, rotation_tables=False):
    source = references.directory / "static_data_get.bin"
    if not source.is_file() or not 5 <= source.stat().st_size <= MAX_PACKET:
        raise ValueError("Raid activation requires the matching external static_data_get.bin")
    raw = decode(source.read_bytes())
    lines, items = records(raw)
    if not {"guildraid2", "seasondate", "__checksum__"} <= items.keys():
        raise ValueError("Missing raid, calendar or checksum static record")
    raid = json.loads(items["guildraid2"][1])
    if not isinstance(raid, dict) or any(
        not isinstance(raid.get(key), list) or any(not isinstance(row, dict) for row in raid[key])
        for key in ("Seasons", "Boss", "BossDetails")
    ):
        raise ValueError("Invalid preserved raid static table shape")
    matches = [s for s in raid.get("Seasons", []) if s.get("Id") == season["season_id"]]
    if len(matches) != 1 or any(
        matches[0].get(k) != season[v]
        for k, v in (("BossSet", "boss_set"), ("RoundSet", "round_set"))
    ):
        raise ValueError("Raid season does not match the preserved static tables")
    selected = matches[0]
    date_id = selected.get("SeasonDateId")
    if type(date_id) is not int or not 5400001 <= date_id <= 5400999:
        raise ValueError("Selected season must use the matching global raid calendar range")
    if sum(s.get("SeasonDateId") == date_id for s in raid["Seasons"]) != 1:
        raise ValueError("Selected raid calendar must not be shared between seasons")
    boss_rows = [b for b in raid.get("Boss", []) if b.get("SetId") == season["boss_set"]]
    details = {b["Id"]: b for b in raid.get("BossDetails", [])}
    actual = sorted(
        (
            {"slot": b["Slot"], "id": b["Id"], "stage_id": details[b["Id"]]["StageId"]}
            for b in boss_rows
        ),
        key=lambda b: b["slot"],
    )
    if actual != sorted(season["bosses"], key=lambda b: b["slot"]):
        raise ValueError("Raid boss/stage catalog does not match preserved static tables")
    updates = {}
    if lineup is not None or rotation_tables:
        if "monsters" not in items:
            raise ValueError("Custom Raid rotations require the matching monster table")
        updates = {
            name: items[name][1]
            for name in ("guildraid2", "monsters", "monsters-bin")
            if name in items
        }
    if lineup is not None:
        from .guild_raid import validate_season
        from .raid_custom import append_binary_monsters, build_season, use_local_presentation

        monsters = json.loads(updates["monsters"])
        monster_count = len(monsters)
        season = build_season(raid, monsters, season, selected, lineup)
        validate_season(season)
        use_local_presentation(raid, selected, references.directory)
        updates["guildraid2"] = json.dumps(raid, ensure_ascii=False, separators=(",", ":"))
        if len(monsters) != monster_count:
            updates["monsters"] = json.dumps(monsters, ensure_ascii=False, separators=(",", ":"))
            if "monsters-bin" in updates:
                updates["monsters-bin"] = append_binary_monsters(
                    updates["monsters-bin"], monsters[monster_count:]
                )
    calendar = json.loads(items["seasondate"][1])
    if (
        not isinstance(calendar, dict)
        or not isinstance(calendar.get("EventPeriod"), list)
        or any(not isinstance(row, dict) for row in calendar["EventPeriod"])
    ):
        raise ValueError("Invalid preserved season calendar table shape")
    dates = [d for d in calendar.get("EventPeriod", []) if d.get("Id") == date_id]
    if len(dates) != 1:
        raise ValueError("Selected raid needs one existing calendar row")
    date = dates[0]
    for key, value in (("From", LOCAL_FROM), ("To", LOCAL_TO), ("RewardUntil", LOCAL_REWARD_UNTIL)):
        if key == "RewardUntil" and key not in date:
            continue
        if not isinstance(date.get(key), dict) or "KakaoGlobal" not in date[key]:
            raise ValueError("Selected raid date must contain explicit global service timestamps")
        date[key]["KakaoGlobal"] = value
    content = json.dumps(calendar, ensure_ascii=False, separators=(",", ":"))
    updates["seasondate"] = content
    revision = max(int(time.time()), previous_revision + 1, 1 + max(items[k][2] for k in updates))
    if revision > 0x7FFFFFFF:
        raise ValueError("Local static revision exceeds the native integer range")
    base = items["__checksum__"][1].encode()
    checksum_input = b"local-raid-calendar-v1\n" + base + b"\n" + content.encode()
    if "guildraid2" in updates:
        checksum_input += b"\n" + b"\n".join(
            digest(record_bytes(name, value)).encode()
            for name, value in updates.items()
            if name != "seasondate"
        )
    checksum = digest(checksum_input)
    updates["__checksum__"] = checksum
    for name, value in updates.items():
        at = items[name][0]
        lines[at : at + 4] = [
            name + "\n",
            value + "\n",
            str(revision) + "\n",
            digest(record_bytes(name, value)) + "\n",
        ]
    prepared = "".join(lines).encode()
    body = compress(prepared)
    if decode(body) != prepared:
        raise ValueError("Prepared static body failed its compression round trip")
    sha256 = hashlib.sha256(body).hexdigest()
    path = references.directory / f"guild_raid_static_{sha256}.bin"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=references.directory, prefix=".raid-static-", delete=False
        ) as stream:
            temporary = stream.name
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    manifest = {
        "static_data_sha256": sha256,
        "static_data_checksum": checksum,
        "static_data_revision": revision,
    }
    if "guildraid2" in updates:
        manifest["rotation_tables"] = True
    if lineup is not None:
        manifest["custom_season"] = season
    return manifest


def validate_manifest(selection):
    sha256 = selection["static_data_sha256"]
    checksum = selection["static_data_checksum"]
    revision = selection["static_data_revision"]
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(c not in "0123456789abcdef" for c in sha256)
    ):
        raise ValueError("Invalid local raid static body digest")
    try:
        valid_checksum = (
            isinstance(checksum, str) and len(base64.b64decode(checksum, validate=True)) == 32
        )
    except ValueError:
        valid_checksum = False
    if not valid_checksum or type(revision) is not int or not 1 <= revision <= 0x7FFFFFFF:
        raise ValueError("Invalid local raid static checksum or revision")


def bootstrap_override(references, filename, request):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return None
    from .guild_raid import load_selection

    selection = load_selection(references)
    if selection is None or not MANIFEST_KEYS <= selection.keys():
        return None
    if filename == "static_data_check.bin":
        current = request.get("Checksum") if isinstance(request, dict) else None
        return json.dumps(
            {
                "UpToDate": current == selection["static_data_checksum"],
                "Checksum": selection["static_data_checksum"],
                "QuitGameWhenStaticDataUpdateNeeded": False,
            }
        ).encode()
    path = references.directory / f"guild_raid_static_{selection['static_data_sha256']}.bin"
    if not path.is_file() or not 5 <= path.stat().st_size <= MAX_PACKET:
        raise ValueError("Prepared raid static body is missing; run raid-season set again")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != selection["static_data_sha256"]:
        raise ValueError("Prepared raid static body checksum mismatch")
    return body
