# SPDX-License-Identifier: Apache-2.0
"""Reversible Guild War calendar overlay above the selected Raid and arena data."""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .punchking_static import atomic_write
from .punchking_static import bootstrap_override as arena_override
from .raid_static import (
    LOCAL_FROM,
    LOCAL_TO,
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
OVERLAY_POLICY = 7
PHASES = {"coop-offense": 1, "coop-defense": 2, "multi-offense": 3, "multi-defense": 4}
ROUND_MODES = {"auto": None, "prep": 24, "combat": 0}
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
        or set(value)
        - {"skip_basic", "overlay_policy", "phase", "defend_castle", "attack_castle", "round_mode"}
        != {"client", "season_id", "period", "base_sha256"} | MANIFEST_KEYS
        or "overlay_policy" in value
        and (
            type(value["overlay_policy"]) is not int
            or value["overlay_policy"] not in (3, 4, 5, 6, OVERLAY_POLICY)
        )
        or type(value.get("skip_basic", False)) is not bool
        or type(value.get("phase", 1)) is not int
        or value.get("phase", 1) not in PHASES.values()
        or type(value.get("defend_castle", 0)) is not int
        or not 0 <= value.get("defend_castle", 0) <= 0x7FFFFFFF
        or value.get("defend_castle", 0) > 0
        and value.get("phase", 1) != 4
        or type(value.get("attack_castle", 0)) is not int
        or not 0 <= value.get("attack_castle", 0) <= 0x7FFFFFFF
        or value.get("attack_castle", 0) > 0
        and value.get("phase", 1) != 3
        or type(value.get("round_mode", "auto")) is not str
        or value.get("round_mode", "auto") not in ROUND_MODES
        or value.get("round_mode", "auto") != "auto"
        and value.get("phase", 1) not in (3, 4)
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


def enable(
    references,
    source=None,
    skip_basic=None,
    phase=None,
    defend_castle=None,
    attack_castle=None,
    round_mode=None,
):
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
    if defend_castle is None:
        defend_castle = (previous or {}).get("defend_castle", 0) if phase == 4 else 0
    if (
        type(defend_castle) is not int
        or not 0 <= defend_castle <= 0x7FFFFFFF
        or defend_castle > 0
        and phase != 4
    ):
        raise ValueError(
            "A local defense castle requires phase multi-defense and a native castle ID"
        )
    if defend_castle and defend_castle not in {row[0] for row in _castle_specs(source, 1)}:
        raise ValueError("Select a defense castle from the enabled native deployment")
    if attack_castle is None:
        attack_castle = (previous or {}).get("attack_castle", 0) if phase == 3 else 0
    if (
        type(attack_castle) is not int
        or not 0 <= attack_castle <= 0x7FFFFFFF
        or attack_castle > 0
        and phase != 3
    ):
        raise ValueError("A local siege target requires phase multi-offense and a native castle ID")
    if attack_castle and attack_castle not in {row[0] for row in _castle_specs(source, 1)}:
        raise ValueError("Select a siege target from the enabled native deployment")
    if round_mode is None:
        round_mode = (previous or {}).get("round_mode", "auto") if phase in (3, 4) else "auto"
    if (
        type(round_mode) is not str
        or round_mode not in ROUND_MODES
        or round_mode != "auto"
        and phase not in (3, 4)
    ):
        raise ValueError("Select auto round timing, or prep/combat for a native Multi phase")
    skip_basic = (previous or {}).get("skip_basic", False) if skip_basic is None else skip_basic
    if type(skip_basic) is not bool:
        raise ValueError("Guild War skip-basic policy must be Boolean")
    shop_group = seasons[0].get("ShopGroupId")
    shops = war.get("ShopSet")
    if (
        type(shop_group) is not int
        or shop_group <= 0
        or not isinstance(shops, list)
        or any(
            not isinstance(row, dict) or type(row.get("GroupId")) is not int or row["GroupId"] <= 0
            for row in shops
        )
    ):
        raise ValueError("Invalid native Guild War season shop group")
    # Each shop row unconditionally resolves absent currency item 21644 for its
    # icon. Native FindAll and SetUI support zero rows, so expose an empty trial
    # shop instead of manufacturing a spec, purchase or reward.
    war["ShopSet"] = [row for row in shops if row["GroupId"] != shop_group]
    constants = war.get("Constants")
    participation = (
        "PlayCoopCoinReward",
        "PlayMultiCoinReward",
        "PlayMultiBattleMedalReward",
        "GetPointPlay",
    )
    if not isinstance(constants, dict) or any(
        type(constants.get(key)) is not int or not 0 <= constants[key] <= 0x7FFFFFFF
        for key in participation
    ):
        raise ValueError("Missing native Guild War participation rewards")
    # Native callbacks append these items locally even with empty AddedItems.
    # Item 21644 is absent; Multi adds medal 21661 from GetPointPlay (offset
    # 0xc4), rather than its named medal field at 0x68. Suppress decorations
    # to keep supported exits rewardless without manufacturing item specs.
    for key in participation:
        constants[key] = 0
    if (
        type(constants.get("MultiBattleRoundStartTime")) is not int
        or not 0 <= constants["MultiBattleRoundStartTime"] <= 24
    ):
        raise ValueError("Invalid native Guild War battle-round start hour")
    if round_mode != "auto":
        # The native predicate compares server time with ContentToday plus this
        # many hours. Preserve the clock and calendar; select only the War round.
        constants["MultiBattleRoundStartTime"] = ROUND_MODES[round_mode]
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
    practice_end = datetime.fromisoformat(period["from"]) - timedelta(seconds=1)
    practice_start = practice_end - timedelta(days=7)
    affected = raid_ids | {war_id}
    found = set()
    for row in dates:
        if row.get("Id") not in affected:
            continue
        if row["Id"] in found:
            raise ValueError("Ambiguous Guild War/Raid calendar")
        found.add(row["Id"])
        stamps = {}
        for key in ("From", "To"):
            if not isinstance(row.get(key), dict) or "KakaoGlobal" not in row[key]:
                raise ValueError("Guild War activation needs explicit Global calendar dates")
            stamps[key] = row[key]["KakaoGlobal"]
        if row["Id"] == war_id:
            stamps = {"From": period["from"], "To": period["to"]}
        elif stamps == {"From": LOCAL_FROM, "To": LOCAL_TO}:
            # Raid preparation marks the selected season in this parent body.
            # The client sorts by start date and uses its last ended season for practice.
            stamps = {"From": practice_start.isoformat(), "To": practice_end.isoformat()}
            if isinstance(row.get("RewardUntil"), dict) and "KakaoGlobal" in row["RewardUntil"]:
                stamps["RewardUntil"] = stamps["To"]
        else:
            stamps = {"From": START_INACTIVE, "To": END_INACTIVE}
        for key, stamp in stamps.items():
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
        f"local-guild-war-v{OVERLAY_POLICY}\n".encode()
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
        "defend_castle": defend_castle,
        "attack_castle": attack_castle,
        "round_mode": round_mode,
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
    # Verify the current file before reusing an immutable, content-keyed catalog.
    return set(_cooperative_stage_ids(prepared_body(references, selection), selection["season_id"]))


@lru_cache(maxsize=2)
def _cooperative_stage_ids(body, season_id):
    _, items = records(decode(body))
    war = json.loads(items["guildwar"][1])
    seasons = war.get("Seasons") if isinstance(war, dict) else None
    sets = war.get("CastleStageSet") if isinstance(war, dict) else None
    if (
        not isinstance(seasons, list)
        or len(seasons) != 1
        or not isinstance(seasons[0], dict)
        or seasons[0].get("Id") != season_id
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
    return frozenset(stages)


def castle_specs(references, selection):
    """Read only the enabled season's native castle deployment catalog."""
    rows = _castle_specs(prepared_body(references, selection), selection["season_id"])
    return {
        value: {"Id": value, "GroupId": group, "Grade": grade, "SpotId": spot}
        for value, group, grade, spot in rows
    }


def defense_stage_ids(references, selection):
    if selection.get("phase", 1) != 4 or not selection.get("defend_castle", 0):
        raise ValueError("Select a local defense castle in multi-defense first")
    return _defense_stage_ids(
        prepared_body(references, selection), selection["season_id"], selection["defend_castle"]
    )


def offense_stage_ids(references, selection):
    if selection.get("phase", 1) != 3:
        raise ValueError("Select multi-offense before entering a Fortress siege stage")
    return _offense_stage_ids(
        prepared_body(references, selection),
        selection["season_id"],
        selection.get("attack_castle", 0),
    )


@lru_cache(maxsize=2)
def _offense_stage_ids(body, season_id, castle_id):
    castles = {row[0]: row for row in _castle_specs(body, season_id)}
    if castle_id and castle_id not in castles:
        raise ValueError("The selected siege target is missing from the native deployment")
    grades = {castles[castle_id][2]} if castle_id else {row[2] for row in castles.values()}
    _, items = records(decode(body))
    war = json.loads(items["guildwar"][1])
    group = war["Seasons"][0].get("CastleStageGroupId")
    rows = war.get("CastleStageSet")
    if type(group) is not int or group <= 0 or not isinstance(rows, list):
        raise ValueError("Invalid Guild War siege stage group")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid Guild War stage set")
    stages = set()
    for grade in sorted(grades):
        matches = [
            row
            for row in rows
            if row.get("GroupId") == group and row.get("StageSetType") == f"MultiGrade{grade}"
        ]
        if len(matches) != 1:
            raise ValueError("Expected one native siege stage set per deployed castle grade")
        values = matches[0].get("SiegeStageIds")
        if (
            not isinstance(values, list)
            or not values
            or any(type(value) is not int or not 0 < value <= 0x7FFFFFFF for value in values)
            or len(set(values)) != len(values)
            or stages.intersection(values)
        ):
            raise ValueError("Invalid or ambiguous native castle siege stages")
        stages.update(values)
    return frozenset(stages)


@lru_cache(maxsize=2)
def _defense_stage_ids(body, season_id, castle_id):
    castles = {row[0]: row for row in _castle_specs(body, season_id)}
    if castle_id not in castles:
        raise ValueError("The selected defense castle is missing from the native deployment")
    _, items = records(decode(body))
    war = json.loads(items["guildwar"][1])
    group = war["Seasons"][0].get("CastleStageGroupId")
    rows = war.get("CastleStageSet")
    if type(group) is not int or group <= 0 or not isinstance(rows, list):
        raise ValueError("Invalid Guild War defense stage group")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid Guild War stage set")
    matches = [
        row
        for row in rows
        if row.get("GroupId") == group
        and row.get("StageSetType") == f"MultiGrade{castles[castle_id][2]}"
    ]
    if len(matches) != 1:
        raise ValueError("Expected one matching native castle-grade defense set")
    stages = matches[0].get("DefenceStageIds")
    if (
        not isinstance(stages, list)
        or not stages
        or any(type(value) is not int or not 0 < value <= 0x7FFFFFFF for value in stages)
        or len(set(stages)) != len(stages)
    ):
        raise ValueError("Invalid native castle defense stages")
    return frozenset(stages)


@lru_cache(maxsize=2)
def _castle_specs(body, season_id):
    # Recheck the file digest on every read, but decode matching static data once.
    # Immutable cache rows prevent callers from altering subsequent responses.
    _, items = records(decode(body))
    war = json.loads(items["guildwar"][1])
    seasons = war.get("Seasons") if isinstance(war, dict) else None
    if (
        not isinstance(seasons, list)
        or len(seasons) != 1
        or not isinstance(seasons[0], dict)
        or seasons[0].get("Id") != season_id
        or type(seasons[0].get("CastleDeployGroupId")) is not int
        or seasons[0]["CastleDeployGroupId"] <= 0
    ):
        raise ValueError("Invalid Guild War castle deployment group")
    group = seasons[0]["CastleDeployGroupId"]
    specs, spots = war.get("CastleSpecs"), war.get("CastleDeploySpots")
    if not isinstance(specs, list) or not isinstance(spots, list):
        raise ValueError("Missing native Guild War castle deployment")
    spot_ids = []
    for spot in spots:
        if not isinstance(spot, dict) or type(spot.get("SpotId")) is not int or spot["SpotId"] <= 0:
            raise ValueError("Invalid Guild War castle spot")
        spot_ids.append(spot["SpotId"])
    if len(set(spot_ids)) != len(spot_ids):
        raise ValueError("Ambiguous Guild War castle spots")
    selected, used_spots = {}, set()
    for row in specs:
        if not isinstance(row, dict) or type(row.get("GroupId")) is not int:
            raise ValueError("Invalid Guild War castle specification")
        if row["GroupId"] != group:
            continue
        if (
            type(row.get("Id")) is not int
            or not 0 < row["Id"] <= 0x7FFFFFFF
            or row["Id"] in selected
            or type(row.get("Grade")) is not int
            or row["Grade"] not in (1, 2, 3, 4)
            or type(row.get("SpotId")) is not int
            or row["SpotId"] not in spot_ids
            or row["SpotId"] in used_spots
        ):
            raise ValueError("Invalid or ambiguous Guild War castle deployment")
        selected[row["Id"]] = row
        used_spots.add(row["SpotId"])
    if not selected:
        raise ValueError("The enabled Guild War season has no native castles")
    return tuple(
        (row["Id"], row["GroupId"], row["Grade"], row["SpotId"]) for row in selected.values()
    )


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
