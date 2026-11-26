# SPDX-License-Identifier: Apache-2.0
"""Opt-in access and practice battles for preserved solo Expedition stages."""

import json
import re
from functools import lru_cache

from guardian_tales.content.static_cache import prepare_static
from guardian_tales.modes.guild.raid_static import compress, decode, digest, records
from guardian_tales.settlement.village import integer

ENTRY = "/expedition/enter"
TODAY_SCORE = "/expedition/get-today-max-score"
FARM_ENTRY = "/heavenholdfarm/enter"
START = "/expedition/start-stage"
BEAT = "/expedition/beat-monsters"
CLEAR = "/expedition/clear-stage/v2"
END = "/expedition/end-stage"
RANKINGS = "/expedition/get-stage-rankings"
STAGE_FIELDS = {
    START: {"StageId"},
    BEAT: {"StageId", "MonsterHandleNames"},
    CLEAR: {
        "StageId",
        "PlayTime",
        "KillScore",
        "Survivors",
        "PartySwitchingCount",
        "Kills",
        "SupportSkillUsed",
    },
    END: {"StageId"},
    RANKINGS: {"StageId"},
}
ROUTES = (ENTRY, TODAY_SCORE, FARM_ENTRY, *STAGE_FIELDS)
TRIAL = "expedition_trial.enabled"
FEATURE_IDS = (31, 110)
REGION_ID = 1
DOTNET_TICKS_PER_MILLISECOND = 10_000
MAX_PLAY_TIME_TICKS = 0x7FFFFFFFFFFFFFFF


def enabled(references):
    return (references.directory / TRIAL).is_file()


@lru_cache(maxsize=2)
def prepare(body):
    lines, tables = records(decode(body))
    if not {"unlockfeature", "__checksum__"} <= tables.keys():
        raise ValueError("Expedition requires the matching external feature table")
    features = json.loads(tables["unlockfeature"][1])
    if not isinstance(features, list) or any(not isinstance(row, dict) for row in features):
        raise ValueError("Invalid feature rules for Expedition")
    for feature_id in FEATURE_IDS:
        rows = [row for row in features if row.get("Id") == feature_id]
        versions = rows[0].get("VersionFrom") if len(rows) == 1 else None
        if not isinstance(versions, dict) or versions.get("KakaoGlobal") != "v9.99":
            raise ValueError("Expedition requires the matching Global maintenance rules")
        versions["KakaoGlobal"] = "v3.57"

    content = json.dumps(features, ensure_ascii=False, separators=(",", ":"))
    revision = max(tables["unlockfeature"][2], tables["__checksum__"][2]) + 1
    if revision > 0x7FFFFFFF:
        raise ValueError("Expedition static revision exceeds the native integer range")
    checksum = digest(
        b"local-expedition-v1\n" + tables["__checksum__"][1].encode() + b"\n" + content.encode()
    )
    for name, value in (("unlockfeature", content), ("__checksum__", checksum)):
        at = tables[name][0]
        lines[at : at + 4] = [
            name + "\n",
            value + "\n",
            str(revision) + "\n",
            digest(value.encode()) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(references, filename, request, parent):
    if filename not in ("static_data_get.bin", "static_data_check.bin") or not enabled(references):
        return parent(references, filename, request)
    source = parent(references, "static_data_get.bin", request)
    body, checksum = prepare_static(references, prepare, source)
    from .expedition_levels import load_levels
    from .expedition_levels import prepare as prepare_levels

    selection = load_levels(references)
    if selection is not None:
        body, checksum = prepare_static(references, prepare_levels, body, *selection)
    if filename == "static_data_get.bin":
        return body
    return json.dumps(
        {
            "UpToDate": isinstance(request, dict) and request.get("Checksum") == checksum,
            "Checksum": checksum,
            "QuitGameWhenStaticDataUpdateNeeded": False,
        }
    ).encode()


@lru_cache(maxsize=1)
def stage_catalog(body):
    _, tables = records(decode(body))
    if not {"expedition", "expeditionbattle", "stages"} <= tables.keys():
        raise ValueError("Expedition practice requires the matching stage and combat tables")
    expedition = json.loads(tables["expedition"][1])
    stage_ids = {stage for district in expedition["Districts"] for stage in district["StageIds"]}
    stages = {row["Id"]: row for row in json.loads(tables["stages"][1]) if row["Id"] in stage_ids}
    return stages, json.loads(tables["expeditionbattle"][1])["Constants"]


def play_time_ticks(value):
    # The native request boxes a TimeSpan; its JSON value uses the invariant
    # constant format [d.]hh:mm:ss[.fffffff]. Keep legacy integer tick inputs.
    if integer(value, maximum=MAX_PLAY_TIME_TICKS):
        return value
    if not isinstance(value, str) or len(value) > 25:
        raise ValueError("Expedition PlayTime requires a nonnegative TimeSpan or tick count")
    match = re.fullmatch(
        r"(?:(\d{1,8})\.)?(\d{2}):([0-5]\d):([0-5]\d)(?:\.(\d{1,7}))?", value, re.ASCII
    )
    if match is None or int(match[2]) > 23:
        raise ValueError("Invalid Expedition TimeSpan format")
    days, hours, minutes, seconds, fraction = match.groups()
    elapsed_seconds = ((int(days or 0) * 24 + int(hours)) * 60 + int(minutes)) * 60 + int(seconds)
    ticks = elapsed_seconds * 10_000_000 + int((fraction or "0").ljust(7, "0"))
    if ticks > MAX_PLAY_TIME_TICKS:
        raise ValueError("Expedition PlayTime exceeds the native TimeSpan range")
    return ticks


def practice_result(request, stage, constants):
    ticks = play_time_ticks(request["PlayTime"])
    if (
        not all(integer(request[key]) for key in ("KillScore", "PartySwitchingCount", "Kills"))
        or not integer(request["Survivors"], maximum=4 * stage["PartyCount"])
        or type(request["SupportSkillUsed"]) is not bool
    ):
        raise ValueError("Invalid Expedition practice result")
    elapsed = ticks // DOTNET_TICKS_PER_MILLISECOND
    remaining = max(0, stage["Time"] * 1000 - elapsed)
    time_score = int(remaining * constants["RemainingTimeBonus"])
    base = request["KillScore"] + time_score
    survivor_score = int(constants["RemainingPartyBonus"] * request["Survivors"] * base)
    switch_score = int(constants["PartySwitchingBonus"] * request["PartySwitchingCount"] * base)
    if base + survivor_score + switch_score > 0x7FFFFFFF:
        raise ValueError("Expedition practice score exceeds the native integer range")
    return {
        "RegionId": REGION_ID,
        "KillScore": request["KillScore"],
        "TimeScore": time_score,
        "SurvivorsScore": survivor_score,
        "PartySwitchingScore": switch_score,
        "TodayMaxScore": [],
        "NewRecord": False,
        "Rankings": [],
        "AddedCollectibles": [],
        "AddedItems": [],
    }


def practice_stage(references, saved, route, request):
    if (
        not isinstance(request, dict)
        or set(request) != STAGE_FIELDS[route]
        or not integer(request["StageId"], minimum=1)
    ):
        raise ValueError("Invalid Expedition stage request")
    stage_id = request["StageId"]
    stages, constants = stage_catalog(references.read_bytes("static_data_get.bin"))
    if stage_id not in stages:
        raise ValueError("Select a stage in a preserved Expedition district")
    if route == RANKINGS:
        return {"Rankings": []}
    if not any(
        isinstance(row, dict)
        and row.get("Id") == stage_id
        and integer(row.get("StageState"))
        and row["StageState"] & 3 == 3
        for row in saved["StageStates"]
    ):
        raise ValueError("Select a stage already opened and unlocked in the Expedition save")
    if route == BEAT:
        names = request["MonsterHandleNames"]
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError("Expedition monster reports require a list of handle names")
        return {"AddedCollectibles": [], "AddedSpecialCollectibles": []}
    if route == CLEAR:
        return practice_result(request, stages[stage_id], constants)
    return {}


def read(store, route, request):
    if not enabled(store.references) or store.account.needs_prologue():
        raise ValueError("The local Expedition trial requires activation and a completed prologue")
    if route == FARM_ENTRY:
        if (
            not isinstance(request, dict)
            or set(request) != {"IsPartial"}
            or type(request["IsPartial"]) is not bool
        ):
            raise ValueError("Heavenhold Farm entry requires Boolean IsPartial")
        profile = store.account.profile()
        farm = profile.get("UserHeavenHoldFarm")
        if farm is None:
            # The Expedition map loads the farm resource during scene setup.
            farm = {
                "UserId": profile["User"]["Id"],
                "Obstacles": [],
                "Buildings": [],
                "PurchasedShopItemCount": {},
                "SaleProductIds": [],
                "ExtraBuildingCount": {},
                "FishInventory": [],
                "Aquariums": [],
                "Villagers": [],
                "ObstacleSpots": {},
            }
        return {"IsPartial": False, "UserHeavenHoldFarm": farm}
    profile = store.account.profile()
    saved = profile.get("UserExpedition")
    if (
        not isinstance(saved, dict)
        or saved.get("UserId") != profile["User"]["Id"]
        or not isinstance(saved.get("StageStates"), list)
    ):
        raise ValueError("The Expedition trial requires saved Expedition progress")
    if route in STAGE_FIELDS:
        return practice_stage(store.references, saved, route, request)
    fields = {"RegionId", "IsPartial"} if route == ENTRY else {"RegionId"}
    if (
        not isinstance(request, dict)
        or set(request) != fields
        or type(request["RegionId"]) is not int
        or request["RegionId"] != REGION_ID
        or route == ENTRY
        and type(request["IsPartial"]) is not bool
    ):
        raise ValueError("Invalid Expedition region request")
    if route == TODAY_SCORE:
        return {"TodayMaxScore": []}
    return {"IsFirstEnter": False, "IsPartial": False, "UserExpedition": saved}
