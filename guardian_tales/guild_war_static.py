# SPDX-License-Identifier: Apache-2.0
"""Reversible Guild War calendar overlay above the selected Raid and arena data."""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from .punchking_static import atomic_write
from .punchking_static import bootstrap_override as arena_override
from .raid_static import (
    MANIFEST_KEYS,
    MAX_PACKET,
    compress,
    decode,
    digest,
    records,
    validate_manifest,
)
from .raid_static import bootstrap_override as raid_override
from .snapshots import CLIENT

SELECTION = "guild_war_selection.json"
FEATURE_ID = 126
OVERLAY_POLICY = 3
PHASES = {"coop-offense": 1, "coop-defense": 2, "multi-offense": 3, "multi-defense": 4}
START_INACTIVE = "2000-01-01T00:00:00+00:00"
END_INACTIVE = "2000-01-07T23:59:59+00:00"


def utc_now():
    return datetime.now(timezone.utc)


def base_body(references):
    body = arena_override(references, "static_data_get.bin", None)
    if body is None:
        body = raid_override(references, "static_data_get.bin", None)
    return references.read_bytes("static_data_get.bin") if body is None else body


def load_selection(references):
    path = references.directory / SELECTION
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Invalid Guild War selection file")
    value = references.json(SELECTION)
    if (
        not isinstance(value, dict)
        or set(value) - {"skip_basic", "overlay_policy", "phase"}
        != {"client", "season_id", "period", "base_sha256"} | MANIFEST_KEYS
        or "overlay_policy" in value
        and (type(value["overlay_policy"]) is not int or value["overlay_policy"] != OVERLAY_POLICY)
        or type(value.get("skip_basic", False)) is not bool
        or type(value.get("phase", 1)) is not int
        or value.get("phase", 1) not in PHASES.values()
        or value["client"] != CLIENT
        or type(value["season_id"]) is not int
        or value["season_id"] != 1
        or not isinstance(value["base_sha256"], str)
        or len(value["base_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in value["base_sha256"])
        or not isinstance(value["period"], dict)
        or set(value["period"]) != {"from", "to"}
    ):
        raise ValueError("Invalid Guild War selection")
    try:
        start, end = (datetime.fromisoformat(value["period"][key]) for key in ("from", "to"))
        if (
            start.utcoffset() != timedelta(0)
            or end.utcoffset() != timedelta(0)
            or end - start != timedelta(days=7)
        ):
            raise ValueError("Guild War requires a seven-day UTC period")
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid Guild War period") from error
    validate_manifest(value)
    return value


def enable(references, source=None, skip_basic=None, phase=None):
    source = base_body(references) if source is None else source
    lines, items = records(decode(source))
    if (
        not {"guildwar", "guildraid2", "seasondate", "unlockfeature", "__checksum__"}
        <= items.keys()
    ):
        raise ValueError("Guild War needs matching war, raid and calendar static tables")
    war, raid, calendar = (
        json.loads(items[key][1]) for key in ("guildwar", "guildraid2", "seasondate")
    )
    seasons = war.get("Seasons") if isinstance(war, dict) else None
    if (
        not isinstance(seasons, list)
        or len(seasons) != 1
        or not isinstance(seasons[0], dict)
        or seasons[0].get("Id") != 1
        or seasons[0].get("SeasonDateId") != 5500001
    ):
        raise ValueError("Expected the matching Guild War season 1 and calendar 5500001")
    raid_seasons = raid.get("Seasons") if isinstance(raid, dict) else None
    dates = calendar.get("EventPeriod") if isinstance(calendar, dict) else None
    if (
        not isinstance(raid_seasons, list)
        or not raid_seasons
        or any(
            not isinstance(row, dict) or type(row.get("SeasonDateId")) is not int
            for row in raid_seasons
        )
        or not isinstance(dates, list)
        or any(not isinstance(row, dict) for row in dates)
    ):
        raise ValueError("Invalid Raid/calendar source for Guild War activation")
    raid_ids = {row["SeasonDateId"] for row in raid_seasons}
    war_id = 5500001
    if war_id in raid_ids:
        raise ValueError("Guild War and Raid cannot share a calendar")
    previous = load_selection(references)
    phase = (previous or {}).get("phase", 1) if phase is None else phase
    if type(phase) is not int or phase not in PHASES.values():
        raise ValueError("Select a native Guild War phase from 1 to 4")
    skip_basic = (previous or {}).get("skip_basic", False) if skip_basic is None else skip_basic
    if type(skip_basic) is not bool:
        raise ValueError("Guild War skip-basic policy must be Boolean")
    constants = war.get("Constants")
    if (
        not isinstance(constants, dict)
        or type(constants.get("PlayCoopCoinReward")) is not int
        or not 0 <= constants["PlayCoopCoinReward"] <= 0x7FFFFFFF
    ):
        raise ValueError("Missing native Guild War cooperative participation reward")
    # Native EndCoop adds item 21644 to AddedItems locally when this is positive.
    # That absent item spec crashes the result UI even with an empty server list.
    # Keep the free trial rewardless in both the response and client decoration.
    constants["PlayCoopCoinReward"] = 0
    if skip_basic:
        stage_set_id = constants.get("SingleStageSetId")
        stage_sets = war.get("CastleStageSet")
        if (
            type(stage_set_id) is not int
            or not isinstance(stage_sets, list)
            or any(not isinstance(row, dict) for row in stage_sets)
        ):
            raise ValueError("Missing native Guild War basic-course stage set")
        matches = [row for row in stage_sets if row.get("Id") == stage_set_id]
        if (
            len(matches) != 1
            or matches[0].get("StageSetType") != "Single"
            or any(
                not isinstance(matches[0].get(key), list)
                for key in ("SiegeStageIds", "DefenceStageIds")
            )
        ):
            raise ValueError("Invalid native Guild War basic-course stage lists")
        # IsSingleModeCleared checks both lists in this set, not the similarly
        # named Constants.SingleClearedStageIds. Empty trial lists waive entry
        # prerequisites without recording any fictional player clears.
        for key in ("SiegeStageIds", "DefenceStageIds"):
            matches[0][key] = []
    now = utc_now()
    if now.utcoffset() != timedelta(0):
        raise ValueError("Guild War activation requires a UTC clock")
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period = {"from": start.isoformat(), "to": (start + timedelta(days=7)).isoformat()}
    if previous:
        old_start, old_end = (
            datetime.fromisoformat(previous["period"][key]) for key in ("from", "to")
        )
        if old_start <= now < old_end:
            period = previous["period"]
    affected = raid_ids | {war_id}
    found = set()
    for row in dates:
        if row.get("Id") not in affected:
            continue
        if row["Id"] in found:
            raise ValueError("Ambiguous Guild War/Raid calendar")
        found.add(row["Id"])
        stamps = (
            (period["from"], period["to"])
            if row["Id"] == war_id
            else (START_INACTIVE, END_INACTIVE)
        )
        for key, stamp in zip(("From", "To"), stamps):
            if not isinstance(row.get(key), dict) or "KakaoGlobal" not in row[key]:
                raise ValueError("Guild War activation needs explicit Global calendar dates")
            row[key]["KakaoGlobal"] = stamp
    if found != affected:
        raise ValueError("Guild War/Raid calendar rows are missing")
    features = json.loads(items["unlockfeature"][1])
    if (
        not isinstance(features, list)
        or any(not isinstance(row, dict) or type(row.get("Id")) is not int for row in features)
        or len({row["Id"] for row in features}) != len(features)
        or any(row["Id"] == FEATURE_ID for row in features)
    ):
        raise ValueError("Expected matching feature data without an existing GuildWarSingle rule")
    # The native GuildWarSingle enum is 126, absent from this content snapshot.
    # Define the missing no-reward rule for its existing Play > Others handler.
    features.append(
        {
            "Id": FEATURE_ID,
            "Type": "None",
            "Value": {"Default": 0, "Kong": 0, "Switch": 0, "BiliBili": 0},
            "Rewards": [],
            "PriorMenu": "ContentsBook",
            "VersionFrom": {
                service: "v3.57" if service == "KakaoGlobal" else "v9.99"
                for service in ("Kong", "Test", "Switch", "BiliBili", "KakaoKorea", "KakaoGlobal")
            },
        }
    )
    feature_text = json.dumps(features, ensure_ascii=False, separators=(",", ":"))
    war_text = json.dumps(war, ensure_ascii=False, separators=(",", ":"))
    text = json.dumps(calendar, ensure_ascii=False, separators=(",", ":"))
    revision = max(
        int(time.time()),
        items["seasondate"][2] + 1,
        (previous or {}).get("static_data_revision", 0) + 1,
    )
    if revision > 0x7FFFFFFF:
        raise ValueError("Guild War static revision exceeds the native range")
    checksum = digest(
        b"local-guild-war-v3\n"
        + items["__checksum__"][1].encode()
        + b"\n"
        + text.encode()
        + b"\n"
        + feature_text.encode()
        + b"\n"
        + war_text.encode()
    )
    updates = [
        ("seasondate", text),
        ("unlockfeature", feature_text),
        ("guildwar", war_text),
        ("__checksum__", checksum),
    ]
    for name, content in updates:
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
        raise ValueError("Guild War static compression round trip failed")
    sha256 = hashlib.sha256(body).hexdigest()
    value = {
        "client": CLIENT,
        "season_id": 1,
        "period": period,
        "base_sha256": hashlib.sha256(source).hexdigest(),
        "skip_basic": skip_basic,
        "phase": phase,
        "overlay_policy": OVERLAY_POLICY,
        "static_data_sha256": sha256,
        "static_data_checksum": checksum,
        "static_data_revision": revision,
    }
    atomic_write(references.directory / f"guild_war_static_{sha256}.bin", body)
    atomic_write(
        references.directory / SELECTION, json.dumps(value, separators=(",", ":")).encode()
    )
    return value


def prepared_body(references, selection):
    path = references.directory / f"guild_war_static_{selection['static_data_sha256']}.bin"
    if not path.is_file() or not 5 <= path.stat().st_size <= MAX_PACKET:
        raise ValueError("Prepared Guild War data is missing; run guild-war enable again")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != selection["static_data_sha256"]:
        raise ValueError("Prepared Guild War data has the wrong digest")
    return body


def cooperative_stage_ids(references, selection):
    _, items = records(decode(prepared_body(references, selection)))
    war = json.loads(items["guildwar"][1])
    seasons = war.get("Seasons") if isinstance(war, dict) else None
    sets = war.get("CastleStageSet") if isinstance(war, dict) else None
    if (
        not isinstance(seasons, list)
        or len(seasons) != 1
        or not isinstance(seasons[0], dict)
        or seasons[0].get("Id") != selection["season_id"]
        or type(seasons[0].get("CastleStageGroupId")) is not int
        or not isinstance(sets, list)
        or any(not isinstance(row, dict) for row in sets)
    ):
        raise ValueError("Invalid Guild War season stage group")
    matches = [
        row
        for row in sets
        if row.get("StageSetType") == "Coop"
        and row.get("GroupId") == seasons[0]["CastleStageGroupId"]
    ]
    if len(matches) != 1:
        raise ValueError("Expected one native cooperative Guild War stage set")
    stages = []
    for key in ("SiegeStageIds", "DefenceStageIds"):
        values = matches[0].get(key)
        if not isinstance(values, list) or any(type(v) is not int or v <= 0 for v in values):
            raise ValueError("Invalid cooperative Guild War stage list")
        stages.extend(values)
    if not stages or len(set(stages)) != len(stages):
        raise ValueError("Missing or ambiguous cooperative Guild War stages")
    return set(stages)


def bootstrap_override(references, filename, request):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return None
    selection = load_selection(references)
    if selection is None:
        return None
    source = base_body(references)
    start, end = (datetime.fromisoformat(selection["period"][key]) for key in ("from", "to"))
    if (
        selection.get("overlay_policy") != OVERLAY_POLICY
        or selection["base_sha256"] != hashlib.sha256(source).hexdigest()
        or not start <= utc_now() < end
    ):
        selection = enable(references, source)
    if filename == "static_data_check.bin":
        current = request.get("Checksum") if isinstance(request, dict) else None
        return json.dumps(
            {
                "UpToDate": current == selection["static_data_checksum"],
                "Checksum": selection["static_data_checksum"],
                "QuitGameWhenStaticDataUpdateNeeded": False,
            }
        ).encode()
    return prepared_body(references, selection)
