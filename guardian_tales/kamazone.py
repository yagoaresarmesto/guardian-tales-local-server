# SPDX-License-Identifier: Apache-2.0
"""Select a preserved Global Kama-ZONE season for the Events menu."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from . import kamazone_legacy
from .punchking_static import atomic_write
from .raid_static import compress, decode, digest, records
from .reference import ReferenceData
from .state_lock import StateLock
from .static_cache import prepare_static
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
def source_tables(body):
    return records(decode(body))[1]


@lru_cache(maxsize=2)
def old_seasons(source):
    return kamazone_legacy.catalog(source_tables(source))


@lru_cache(maxsize=3)
def mode_data(source, season_id=None):
    tables = source_tables(source)
    if season_id is not None and season_id in old_seasons(source):
        return kamazone_legacy.event_mode(tables, season_id)
    return json.loads(tables["kamazonland2"][1])


@lru_cache(maxsize=2)
def artifact_specs(source, season_id=None):
    rows = mode_data(source, season_id).get("Artifacts")
    if not isinstance(rows, list):
        raise ValueError("Missing preserved Kama-ZONE artifact definitions")
    specs = {}
    for row in rows:
        if not isinstance(row, dict) or not integer(row.get("Id"), minimum=1) or row["Id"] in specs:
            raise ValueError("Invalid or duplicate Kama-ZONE artifact definition")
        specs[row["Id"]] = row
    return specs


@lru_cache(maxsize=2)
def catalog(body):
    tables = source_tables(body)
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


def playable_season(source, season_id):
    return season_id in catalog(source) or season_id in old_seasons(source)


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
        or type(value.get("version")) is not int
        or value["version"] not in (1, 2)
        or set(value)
        != {"version", "generation", "season_id", "source_sha256", "period"}
        | ({"event_calendar"} if value["version"] == 2 else set())
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
    if value.get("event_calendar") is not None:
        previous = value["event_calendar"]
        if (
            not isinstance(previous, dict)
            or previous.keys() != {"season_id", "period"}
            or not integer(previous["season_id"], minimum=1)
            or value["season_id"] is None
        ):
            raise ValueError("Invalid saved event-season calendar")
        validate_window(previous["period"])
    return value


@lru_cache(maxsize=2)
def prepare(body, generation, season_id, period):
    lines, tables = records(decode(body))
    if not integer(generation, minimum=1) or not {"seasondate", "__checksum__"} <= tables.keys():
        raise ValueError("Invalid Kama-ZONE static generation or calendar")
    content = tables["seasondate"][1]
    if season_id is not None:
        eligible = catalog(body)
        if season_id not in eligible:
            archive = old_seasons(body)
            if season_id in archive:
                eligible = {**eligible, season_id: archive[season_id]}
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
    body, checksum = prepare_static(
        references,
        prepare,
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


class SeasonSelectionChanged(ValueError):
    """A more recent season selection must be reloaded before applying."""


def selection_status(selected, seasons, source_hash, now, *, archive=None, changed=False):
    season_id = selected["season_id"] if selected else None
    period = selected["period"] if selected else None
    matches = season_id is None or selected["source_sha256"] == source_hash
    phase = "disabled"
    if period:
        start, end, reward_end = (timestamp(period[k]) for k in FIELDS)
        if not matches:
            phase = "pack-mismatch"
        elif now < start:
            phase = "scheduled"
        elif now < end:
            phase = "active"
        elif now < reward_end:
            phase = "reward-period"
        else:
            phase = "expired"
    return dict(
        selected_season_id=season_id,
        content_matches=matches,
        local_period=period,
        menu_active_now=phase in ("active", "reward-period"),
        calendar_phase=phase,
        generation=(selected or {}).get("generation", 0),
        seasons=list(seasons.values()),
        old_seasons=list((archive or {}).values()),
        old_active=season_id in (archive or {}),
        previous_event_season_id=((selected or {}).get("event_calendar") or {}).get("season_id"),
        scope="Global Kama-ZONE season calendar for the Events menu",
        saved_account_modified=False,
        restart_backend_and_game_required=changed,
    )


def status(references):
    source = references.read_bytes("static_data_get.bin")
    return selection_status(
        load(references),
        catalog(source),
        hashlib.sha256(source).hexdigest(),
        utc_now(),
        archive=old_seasons(source),
    )


def change_season(references, season_id, *, expected_generation=None, old=False, leave_old=False):
    """Select a rotation, restore the previous event, or clear the local calendar."""
    if old and season_id is None or leave_old and (old or season_id is not None):
        raise ValueError("Choose an archived season to activate, or turn Old Kamazone off.")
    source = references.read_bytes("static_data_get.bin")
    seasons = catalog(source)
    sha = hashlib.sha256(source).hexdigest()
    archive = old_seasons(source)
    options = archive if old else seasons
    if season_id is not None and (not integer(season_id, minimum=1) or season_id not in options):
        raise ValueError("Choose a season from the selected Global Kama-ZONE catalog")

    # Restoring an unconfigured installation is a read-only no-op.
    if season_id is None and not (references.directory / SELECTION).exists():
        if expected_generation not in (None, 0):
            raise SeasonSelectionChanged("Season selection changed. Reload before applying.")
        return selection_status(None, seasons, sha, utc_now(), archive=archive)

    with StateLock(references.directory, filename=".kamazone_season.lock"):
        selected = load(references)
        generation = (selected or {}).get("generation", 0)
        if expected_generation is not None and expected_generation != generation:
            raise SeasonSelectionChanged("Season selection changed. Reload before applying.")
        now = utc_now()
        current = selection_status(selected, seasons, sha, now, archive=archive)
        previous = (selected or {}).get("event_calendar") if current["content_matches"] else None
        if leave_old:
            if not current["old_active"]:
                return current
            season_id = (
                previous["season_id"] if previous and previous["season_id"] in seasons else None
            )
        if current["selected_season_id"] == season_id and current["calendar_phase"] in (
            "active",
            "disabled",
        ):
            return current
        period = None
        if leave_old and season_id is not None:
            period = previous["period"]
        elif season_id is not None:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            dates = (start, start + timedelta(days=14), start + timedelta(days=21))
            period = {key: date.isoformat() for key, date in zip(FIELDS, dates)}
        candidate = dict(
            version=1,
            generation=generation + 1,
            season_id=season_id,
            source_sha256=sha if season_id is not None else selected["source_sha256"],
            period=period,
        )
        if old:
            if current["content_matches"] and current["selected_season_id"] in seasons:
                previous = dict(season_id=selected["season_id"], period=selected["period"])
            candidate.update(version=2, event_calendar=previous)
            # Resolve the converted table before publishing the selection.
            mode_data(source, season_id)
        window = tuple(period[k] for k in FIELDS) if period else None
        prepare(source, candidate["generation"], season_id, window)
        atomic_write(
            references.directory / SELECTION, json.dumps(candidate, indent=2).encode() + b"\n"
        )
        return selection_status(candidate, seasons, sha, now, archive=archive, changed=True)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "practice":
        from .kamazone_practice import main as practice_main

        return practice_main(arguments[1:])
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="All seasonal menu benefits and 4,000 points are available automatically.",
    )
    parser.add_argument("action", choices=("list", "select", "status", "disable"))
    parser.add_argument("--season-id", type=int)
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(arguments)
    references = ReferenceData(args.reference_dir)
    try:
        if (args.action == "select") != (args.season_id is not None):
            raise ValueError("Use select --season-id ID; list/status/disable take no season ID")
        if args.action in ("select", "disable"):
            result = change_season(references, args.season_id)
        else:
            result = status(references)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        parser.error(str(error))
