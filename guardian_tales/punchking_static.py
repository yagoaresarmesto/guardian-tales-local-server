# SPDX-License-Identifier: Apache-2.0
"""Compose arena variant/day calendars over the independently selected raid tables."""

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime

from .guild_raid import load_selection as raid_selection
from .packet_reader import MAX_PACKET
from .punchking import SELECTION, integer, load_catalog, utc_now, window
from .raid_static import (
    MANIFEST_KEYS,
    atomic_replace,
    compress,
    decode,
    digest,
    records,
    validate_manifest,
)
from .raid_static import bootstrap_override as raid_override
from .snapshots import CLIENT


def atomic_write(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".dka-", delete=False) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def raid_digest(references):
    value = raid_selection(references)
    return value.get("static_data_sha256") if value else None


def load_selection(references):
    path = references.directory / SELECTION
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 2048:
        raise ValueError("Invalid arena selection file")
    value = references.json(SELECTION)
    if (
        not isinstance(value, dict)
        or set(value)
        != {"client", "variant", "day", "content_date", "period", "raid_sha256"} | MANIFEST_KEYS
        or value["client"] != CLIENT
        or not integer(value["variant"], 1, 3)
        or not integer(value["day"], 1, 7)
    ):
        raise ValueError("Invalid arena selection")
    try:
        anchor = datetime.fromisoformat(value["content_date"] + "T12:00:00+00:00")
        if window(value["day"], anchor) != (value["content_date"], value["period"]):
            raise ValueError("Arena day does not match its calendar window")
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid arena selection date/window") from error
    sha = value["raid_sha256"]
    if sha is not None and (
        not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)
    ):
        raise ValueError("Invalid composed raid digest")
    validate_manifest(value)
    return value


def select(references, variant_id, day, now=None):
    now = now or utc_now()
    variants = load_catalog(references)["variants"]
    if not integer(variant_id, 1, 3):
        raise ValueError("Choose an arena variant from 1 to 3")
    variant = next(v for v in variants if v["id"] == variant_id)
    content_date, period = window(day, now)
    previous = load_selection(references)
    source = raid_override(references, "static_data_get.bin", None)
    if source is None:
        source = references.read_bytes("static_data_get.bin")
    lines, items = records(decode(source))
    if not {"guildpunchking", "seasondate", "__checksum__"} <= items.keys():
        raise ValueError("Missing arena, calendar or checksum static table")
    arena = json.loads(items["guildpunchking"][1])
    seasons = arena["Seasons"]
    matches = [r for r in seasons if r["Id"] == variant["season_id"]]
    monsters = {r["Id"]: r for r in arena["Monsters"]}
    if (
        len(matches) != 1
        or matches[0]["SeasonId"] != variant["calendar_id"]
        or matches[0]["Monsters"] != [d["id"] for d in variant["days"]]
    ):
        raise ValueError("Arena variant differs from the preserved public season")
    for row in variant["days"]:
        actual = monsters.get(row["id"], {})
        if any(
            actual.get(k) != row[v]
            for k, v in (
                ("MonsterId", "monster_id"),
                ("StageId", "stage_id"),
                ("WeakPoint", "weak_point"),
                ("ElementalType", "element"),
            )
        ):
            raise ValueError("Arena boss details differ from matching public data")
    calendar = json.loads(items["seasondate"][1])
    arena_dates = {r["SeasonId"] for r in seasons}
    found = set()
    for row in calendar["EventPeriod"]:
        if row["Id"] not in arena_dates:
            continue
        if row["Id"] in found:
            raise ValueError("Ambiguous arena calendar")
        found.add(row["Id"])
        active = row["Id"] == variant["calendar_id"]
        dates = (
            (period["from"], period["to"])
            if active
            else ("2000-01-01T00:00:00+00:00", "2000-01-07T23:59:59+00:00")
        )
        for key, stamp in zip(("From", "To"), dates):
            if not isinstance(row.get(key), dict) or "KakaoGlobal" not in row[key]:
                raise ValueError("Arena calendar requires explicit global dates")
            row[key]["KakaoGlobal"] = stamp
    if found != arena_dates:
        raise ValueError("Arena calendar rows are missing")
    text = json.dumps(calendar, ensure_ascii=False, separators=(",", ":"))
    revision = max(
        int(time.time()),
        items["seasondate"][2] + 1,
        (previous or {}).get("static_data_revision", 0) + 1,
    )
    if revision > 0x7FFFFFFF:
        raise ValueError("Arena static revision overflow")
    checksum = digest(
        b"local-dka-calendar-v1\n" + items["__checksum__"][1].encode() + b"\n" + text.encode()
    )
    for name, content in (("seasondate", text), ("__checksum__", checksum)):
        at = items[name][0]
        lines[at : at + 4] = [
            name + "\n",
            content + "\n",
            str(revision) + "\n",
            digest(content.encode()) + "\n",
        ]
    raw = "".join(lines).encode()
    body = compress(raw)
    if decode(body) != raw:
        raise ValueError("Arena static compression did not round trip")
    sha256 = hashlib.sha256(body).hexdigest()
    value = {
        "client": CLIENT,
        "variant": variant_id,
        "day": day,
        "content_date": content_date,
        "period": period,
        "raid_sha256": raid_digest(references),
        "static_data_sha256": sha256,
        "static_data_checksum": checksum,
        "static_data_revision": revision,
    }
    atomic_write(references.directory / f"guild_punchking_static_{sha256}.bin", body)
    atomic_write(
        references.directory / SELECTION, json.dumps(value, separators=(",", ":")).encode()
    )
    return value


def bootstrap_override(references, filename, request):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return None
    selection = load_selection(references)
    if selection is None:
        return None
    # Keep the requested day fixed on a later login and compose later raid changes.
    if selection["content_date"] != utc_now().date().isoformat() or selection[
        "raid_sha256"
    ] != raid_digest(references):
        selection = select(references, selection["variant"], selection["day"])
    if filename == "static_data_check.bin":
        current = request.get("Checksum") if isinstance(request, dict) else None
        return json.dumps(
            {
                "UpToDate": current == selection["static_data_checksum"],
                "Checksum": selection["static_data_checksum"],
                "QuitGameWhenStaticDataUpdateNeeded": False,
            }
        ).encode()
    path = references.directory / f"guild_punchking_static_{selection['static_data_sha256']}.bin"
    if not path.is_file() or not 5 <= path.stat().st_size <= MAX_PACKET:
        raise ValueError("Prepared arena static tables are missing; run dka-season set again")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != selection["static_data_sha256"]:
        raise ValueError("Prepared arena static checksum mismatch")
    return body
