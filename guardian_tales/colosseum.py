# SPDX-License-Identifier: Apache-2.0
"""Local Colosseum lobby and optional practice opponent."""

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .presets import COLOSSEUM_PRESET_COUNT, GEAR_FIELDS, owned_party_preset
from .raid_static import decode, records
from .village import integer

ENTRY = "/colosseum/enter"
OPPONENTS = "/colosseum/get-opponents"
REFRESH = "/colosseum/refresh-opponents"
RANKING = "/colosseum/get-my-ranking"
START = "/colosseum/start-stage/v2"
END = "/colosseum/end-stage/v3"
READ_ROUTES = (ENTRY, OPPONENTS, REFRESH, RANKING)
BATTLE_ROUTES = (START, END)
ROUTES = (*READ_ROUTES, *BATTLE_ROUTES)
PRACTICE_CONFIG = "colosseum_practice.json"
DEFAULT_POSITIONS = (12, 3, 19, 9)
OPPONENT_SLOTS = 3


@lru_cache(maxsize=1)
def practice_season(body):
    _, tables = records(decode(body))
    if "colosseum" not in tables:
        raise ValueError("Missing Colosseum seasons")
    seasons = json.loads(tables["colosseum"][1]).get("Seasons", [])
    # The local lobby uses the latest season with a map in this client.
    return max(
        row["SeasonId"]
        for row in seasons
        if integer(row.get("SeasonId"), minimum=1)
        and integer(row.get("MapId", {}).get("KakaoGlobal"), minimum=1)
    )


def practice_opponents(account, profile):
    if not (account.references.directory / PRACTICE_CONFIG).is_file():
        return []
    config = account.references.json(PRACTICE_CONFIG)
    if (
        not isinstance(config, dict)
        or set(config) != {"preset_id"}
        or not integer(config["preset_id"], minimum=600)
        or config["preset_id"] >= 600 + COLOSSEUM_PRESET_COUNT
    ):
        raise ValueError("Configure one Colosseum attack preset ID for practice")
    preset_id = config["preset_id"]
    preset = owned_party_preset(account.db, profile, preset_id)
    owner = profile["User"]
    first_id = 2_000_000_000 + preset_id * OPPONENT_SLOTS
    opponent_ids = range(first_id, first_id + OPPONENT_SLOTS)
    if owner["Id"] in opponent_ids:
        raise ValueError("The practice opponent must use a different user ID")
    roster = {row["Id"]: row for row in owner["Characters"]}
    characters = []
    equipment_ids = set()
    for member in preset["Characters"]:
        hero = dict(roster[member["Id"]])
        for slot in GEAR_FIELDS:
            item = member.get(slot)
            hero["Accessory1" if slot == "Accessory" else slot] = item or None
            if item:
                equipment_ids.add(item)
        if hero.get("Costume"):
            equipment_ids.add(hero["Costume"])
        equipment_ids.update((hero.get("EquipCostumes") or {}).values())
        characters.append(hero)
    opponent_user = {
        key: owner[key]
        for key in ("GuardianExperience", "GuardianMasteryLevel", "Unlocked")
        if key in owner
    }
    party_ids = [row["Id"] for row in characters]
    opponent_user.update(
        Cas=0,
        Name=preset["Name"] or f"Practice {preset_id}",
        Party={"Id": 0, "Characters": party_ids},
        Characters=characters,
        ItemWeapons=[row for row in owner["ItemWeapons"] if row["Id"] in equipment_ids],
        ItemMiscs=[row for row in owner["ItemMiscs"] if row["Id"] in equipment_ids],
        ItemStackables=[],
    )
    opponent = {
        "Formation": {"Id": 0, "Positions": list(DEFAULT_POSITIONS)},
        "Rank": None,
        "Trophy": profile["UserRecord"].get("ColosseumTrophy", 0),
        "GuildName": "",
    }
    # The lobby only renders after it has three entries and three counters.
    return [dict(opponent, User=dict(opponent_user, Id=user_id)) for user_id in opponent_ids]


def practice_battle(route, request, opponents):
    if not isinstance(request, dict) or not integer(request.get("OpponentId"), minimum=1):
        raise ValueError("Select the configured local Colosseum opponent")
    opponent = next((row for row in opponents if row["User"]["Id"] == request["OpponentId"]), None)
    if opponent is None:
        raise ValueError("Select the configured local Colosseum opponent")
    if route == START:
        # PartyInfo.ToIntList serializes hero spec IDs in formation order.
        party = [row["CharacterId"] for row in opponent["User"]["Characters"]]
        if (
            set(request) != {"OpponentId", "OpponentParty", "OpponentPositions"}
            or request["OpponentParty"] != party
            or request["OpponentPositions"] != opponent["Formation"]["Positions"]
        ):
            raise ValueError("Refresh the local opponent after changing its lineup")
        return {}
    if (
        set(request) != {"OpponentId", "Result", "Damages", "OpponentLevels"}
        or type(request["Result"]) is not int
        or not isinstance(request["Damages"], list)
        or not isinstance(request["OpponentLevels"], list)
    ):
        raise ValueError("Invalid Colosseum practice result")
    return {"AddedTrophy": 0, "AddedItems": []}


def read(account, route, request):
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering Colosseum")
    if route not in ROUTES:
        raise ValueError("Unsupported Colosseum read")
    if route in BATTLE_ROUTES:
        return practice_battle(route, request, practice_opponents(account, account.profile()))
    if request not in (None, {}):
        if route != ENTRY:
            raise ValueError("Colosseum opponent and ranking reads accept no parameters")
        if (
            not isinstance(request, dict)
            or set(request) != {"IsPartial"}
            or type(request["IsPartial"]) is not bool
        ):
            raise ValueError("Colosseum entry expects a Boolean IsPartial cache hint")
    profile = account.profile()
    if route == RANKING:
        ranking = profile.get("UserColosseum", {}).get("Ranking")
        if ranking is None:
            ranking = profile["UserRecord"].get("ColosseumRank", 0)
        return {"Ranking": ranking or 0}
    opponents = practice_opponents(account, profile)
    opponent_ids = [opponent["User"]["Id"] for opponent in opponents]
    challenges = [0] * len(opponent_ids)
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reset = (midnight + timedelta(days=7 - now.weekday())).isoformat()
    # NeedRefresh compares server time to NextRefresh even with a cached empty list.
    # Renew the deadline on list reads as well, including a session crossing a reset.
    lobby = (
        {"Opponents": opponents}
        if route in (OPPONENTS, REFRESH)
        else {"SeasonUntil": reset, "DefenseBattleRecords": [], "NewSeason": False}
    )
    if "UserColosseum" in profile:
        return {
            **lobby,
            "UserColosseum": {
                **profile["UserColosseum"],
                "OpponentIds": opponent_ids,
                "Challenges": challenges,
                "NextRefresh": reset,
            },
        }
    user = profile["User"]
    record = profile["UserRecord"]
    preset_id = user.get("SelectedPresetId", {}).get("ColosseumAttack", 0)
    defense = None
    if preset_id:
        preset = owned_party_preset(account.db, profile, preset_id)
        defense = {"Preset": preset, "Formation": {"Id": 0, "Positions": list(DEFAULT_POSITIONS)}}
    season = practice_season(account.references.read_bytes("static_data_get.bin"))
    return {
        **lobby,
        "UserColosseum": {
            "SeasonId": season,
            "PrevSeasonId": season,
            "SeasonClaimed": True,
            "Trophy": record.get("ColosseumTrophy", 0),
            "Ranking": record.get("ColosseumRank") or None,
            "Win": 0,
            "Lose": 0,
            "Streak": 0,
            "OpponentIds": opponent_ids,
            "Challenges": challenges,
            "Formations": {},
            "DefensePartyInfo": defense,
            "RefreshCount": 0,
            "NextRefresh": reset,
            "NextReset": reset,
            "Ticket": {
                "Type": 3,
                "PlayCount": 0,
                "RefillCount": 0,
                "NextCharge": None,
                "NextDailyReset": (midnight + timedelta(days=1)).isoformat(),
                "PlayLimitUpgradeExpireTime": None,
            },
        },
    }
