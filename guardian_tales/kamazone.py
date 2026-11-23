# SPDX-License-Identifier: Apache-2.0
"""Optional Kama-ZONE season visibility in Events; gameplay remains unsupported."""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .punchking_static import atomic_write
from .raid_static import compress, decode, digest, records
from .reference import ReferenceData
from .village import integer

SELECTION = "kamazone_selection.json"
FIELDS = ("From", "To", "RewardUntil")
REGION = "KakaoGlobal"
NAMES = {
    "mall_season_name_1": "Valentine Season",
    "mall_season_name_2": "Lifeguard Season",
    "mall_season_name_3": "Mecha Harpy Scintilla Season",
}
INACTIVE = ("2000-01-01T00:00:00+00:00", "2000-01-02T00:00:00+00:00", "2000-01-03T00:00:00+00:00")


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Invalid Kama-ZONE calendar timestamp")
    date = datetime.fromisoformat(value)
    if date.utcoffset() is None:
        raise ValueError("Kama-ZONE calendar requires timezone-aware timestamps")
    return date


def one(rows, key, value):
    found = [r for r in rows if isinstance(r, dict) and r.get(key) == value]
    if len(found) != 1:
        raise ValueError(f"Kama-ZONE requires one {key}={value}")
    return found[0]


@lru_cache(maxsize=2)
def catalog(body):
    tables = records(decode(body))[1]
    if not {"kamazonland2", "seasondate", "__checksum__"} <= tables.keys():
        raise ValueError("Kama-ZONE requires matching event-season and calendar tables")
    mode, calendar = (json.loads(tables[name][1]) for name in ("kamazonland2", "seasondate"))
    if not isinstance(mode, dict) or not isinstance(calendar, dict):
        raise ValueError("Invalid Kama-ZONE data tables")
    seasons, periods = mode.get("Seasons"), calendar.get("EventPeriod")
    if not isinstance(seasons, list) or not isinstance(periods, list):
        raise ValueError("Invalid Kama-ZONE seasons/calendar")
    result = {}
    for season in seasons:
        if (
            not isinstance(season, dict)
            or not integer(season.get("Id"), minimum=1)
            or not integer(season.get("SeasonDateId"), minimum=1)
        ):
            raise ValueError("Invalid Kama-ZONE season identity")
        period = one(periods, "Id", season["SeasonDateId"])
        if not isinstance(period.get("From"), dict):
            raise ValueError("Invalid Kama-ZONE regional calendar")
        if REGION not in period["From"]:
            continue
        if any(not isinstance(period.get(k), dict) or REGION not in period[k] for k in FIELDS):
            raise ValueError("Incomplete Global Kama-ZONE calendar")
        dates = tuple(timestamp(period[k][REGION]) for k in FIELDS)
        if not dates[0] < dates[1] <= dates[2]:
            raise ValueError("Invalid Global Kama-ZONE date ordering")
        name = season.get("SeasonName")
        if not isinstance(name, str) or not 1 <= len(name) <= 128 or season["Id"] in result:
            raise ValueError("Invalid or duplicate Global Kama-ZONE season")
        result[season["Id"]] = dict(
            season_id=season["Id"],
            name=NAMES.get(name, name),
            name_key=name,
            calendar_id=season["SeasonDateId"],
            original_period={k: period[k][REGION] for k in FIELDS},
        )
    if (
        not result
        or len(result) > 64
        or len({r["calendar_id"] for r in result.values()}) != len(result)
    ):
        raise ValueError("Global Kama-ZONE seasons need distinct calendars")
    return result


def validate_window(value):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError("Invalid local Kama-ZONE window")
    dates = tuple(timestamp(value[k]) for k in FIELDS)
    if (
        any(d.utcoffset() != timedelta(0) for d in dates)
        or dates[1] - dates[0] != timedelta(days=14)
        or dates[2] - dates[1] != timedelta(days=7)
    ):
        raise ValueError("Kama-ZONE preview needs fourteen days plus seven reward days in UTC")
    return tuple(value[k] for k in FIELDS)


def load(references):
    path = references.directory / SELECTION
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Invalid Kama-ZONE selection file")
    value = references.json(SELECTION)
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "generation", "season_id", "source_sha256", "period"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or not integer(value["generation"], minimum=1)
        or value["season_id"] is not None
        and not integer(value["season_id"], minimum=1)
        or not isinstance(value["source_sha256"], str)
        or len(value["source_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in value["source_sha256"])
    ):
        raise ValueError("Invalid Kama-ZONE selection")
    if value["season_id"] is None:
        if value["period"] is not None:
            raise ValueError("Disabled Kama-ZONE selection cannot retain a local window")
    else:
        validate_window(value["period"])
    return value


@lru_cache(maxsize=2)
def prepare(body, generation, season_id, period):
    lines, tables = records(decode(body))
    if not integer(generation, minimum=1) or not {"seasondate", "__checksum__"} <= tables.keys():
        raise ValueError("Invalid Kama-ZONE static generation or calendar")
    content = tables["seasondate"][1]
    if season_id is not None:
        eligible = catalog(body)
        if not integer(season_id, minimum=1) or season_id not in eligible:
            raise ValueError("Select a Global Kama-ZONE season ID from kamazone list")
        window = (
            dict(zip(FIELDS, period)) if isinstance(period, tuple) and len(period) == 3 else None
        )
        validate_window(window)
        start, _, reward = (timestamp(window[k]) for k in FIELDS)
        calendar = json.loads(content)
        for ident, season in eligible.items():
            row = one(calendar["EventPeriod"], "Id", season["calendar_id"])
            values = period if ident == season_id else INACTIVE
            # Other expired seasons already stay hidden. Suppress only an
            # overlapping original season, and only its Global calendar fields.
            if ident != season_id and not (
                timestamp(row["From"][REGION]) <= reward
                and timestamp(row["RewardUntil"][REGION]) >= start
            ):
                continue
            for key, value in zip(FIELDS, values):
                row[key][REGION] = value
        content = json.dumps(calendar, ensure_ascii=False, separators=(",", ":"))
    elif period is not None:
        raise ValueError("Disabled Kama-ZONE overlay cannot set a period")
    revision = max(tables["seasondate"][2], tables["__checksum__"][2]) + generation + 1
    if revision > 0x7FFFFFFF:
        raise ValueError("Kama-ZONE static revision exceeds the native integer range")
    checksum = digest(
        b"local-kamazone-menu-v1\n"
        + tables["__checksum__"][1].encode()
        + str(generation).encode()
        + str(season_id).encode()
        + content.encode()
    )
    # Advance the calendar revision on disable too, so cached active dates are
    # replaced by the exact parent calendar rather than retaining newer rows.
    for name, text in (("seasondate", content), ("__checksum__", checksum)):
        at = tables[name][0]
        lines[at : at + 4] = [
            name + "\n",
            text + "\n",
            str(revision) + "\n",
            digest(text.encode()) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(references, filename, request, parent):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return parent(references, filename, request)
    selected = load(references)
    if selected is None:
        return parent(references, filename, request)
    if (
        selected["season_id"] is not None
        and hashlib.sha256(references.read_bytes("static_data_get.bin")).hexdigest()
        != selected["source_sha256"]
    ):
        raise ValueError("Kama-ZONE selection belongs to another content pack; disable it first")
    window = tuple(selected["period"][k] for k in FIELDS) if selected["period"] else None
    body, checksum = prepare(
        parent(references, "static_data_get.bin", request),
        selected["generation"],
        selected["season_id"],
        window,
    )
    if filename == "static_data_get.bin":
        return body
    return json.dumps(
        dict(
            Checksum=checksum,
            UpToDate=isinstance(request, dict) and request.get("Checksum") == checksum,
            QuitGameWhenStaticDataUpdateNeeded=False,
        )
    ).encode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "select", "status", "disable"))
    parser.add_argument("--season-id", type=int)
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    references = ReferenceData(args.reference_dir)
    try:
        if (args.action == "select") != (args.season_id is not None):
            raise ValueError("Use select --season-id ID; list/status/disable take no season ID")
        selected = load(references)
        source = references.read_bytes("static_data_get.bin")
        seasons = catalog(source)
        sha = hashlib.sha256(source).hexdigest()
        now = utc_now()
        candidate = selected
        if args.action == "select":
            if args.season_id not in seasons:
                raise ValueError("Select a Global Kama-ZONE season ID from kamazone list")
            if not (
                selected
                and selected["season_id"] == args.season_id
                and selected["source_sha256"] == sha
                and timestamp(selected["period"]["From"])
                <= now
                < timestamp(selected["period"]["To"])
            ):
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                dates = (start, start + timedelta(days=14), start + timedelta(days=21))
                candidate = dict(
                    version=1,
                    generation=(selected or {}).get("generation", 0) + 1,
                    season_id=args.season_id,
                    source_sha256=sha,
                    period={k: d.isoformat() for k, d in zip(FIELDS, dates)},
                )
        elif args.action == "disable" and selected and selected["season_id"] is not None:
            candidate = dict(
                selected, generation=selected["generation"] + 1, season_id=None, period=None
            )
        changed = candidate != selected
        if changed:
            window = tuple(candidate["period"][k] for k in FIELDS) if candidate["period"] else None
            prepare(source, candidate["generation"], candidate["season_id"], window)
            atomic_write(
                references.directory / SELECTION, json.dumps(candidate, indent=2).encode() + b"\n"
            )
        enabled = bool(candidate and candidate["season_id"] is not None)
        matches = not enabled or candidate["source_sha256"] == sha
        print(
            json.dumps(
                dict(
                    selected_season_id=candidate["season_id"] if candidate else None,
                    content_matches=matches,
                    local_period=candidate["period"] if candidate else None,
                    menu_active_now=bool(
                        enabled
                        and matches
                        and timestamp(candidate["period"]["From"])
                        <= now
                        < timestamp(candidate["period"]["RewardUntil"])
                    ),
                    seasons=list(seasons.values()),
                    scope="Events menu and read-only idle lobby; challenges and gameplay are not implemented",
                    saved_account_modified=False,
                    restart_backend_and_game_required=changed,
                ),
                indent=2,
            )
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
