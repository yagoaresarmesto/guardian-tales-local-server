# SPDX-License-Identifier: Apache-2.0
"""Local Colosseum lobby and optional practice opponent."""

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from guardian_tales.modes.guild.raid_static import decode, records
from guardian_tales.settlement.village import integer
from guardian_tales.teams.presets import (
    COLOSSEUM_PRESET_COUNT,
    GEAR_FIELDS,
    current_group,
    owned_party_preset,
    validate_members,
)

ENTRY = "/colosseum/enter"
OPPONENTS = "/colosseum/get-opponents"
REFRESH = "/colosseum/refresh-opponents"
RANKING = "/colosseum/get-my-ranking"
RANKINGS = "/colosseum/get-rankings"
BATTLE_RECORDS = "/colosseum/get-battle-records"
BATTLE_INFOS = "/colosseum/get-battle-infos"
DEFENSE_PARTY = "/colosseum/get-defense-party"
SET_DEFENSE_PRESET = "/colosseum/set-defense-party-preset"
SET_DEFENSE_FORMATION = "/colosseum/set-defense-party-formation"
SAVE_ATTACK_FORMATION = "/colosseum/save-formation"
START = "/colosseum/start-stage/v2"
END = "/colosseum/end-stage/v3"
OPPONENT_LIST_ROUTES = (OPPONENTS, REFRESH)
READ_ROUTES = (
    ENTRY,
    *OPPONENT_LIST_ROUTES,
    RANKING,
    RANKINGS,
    BATTLE_RECORDS,
    BATTLE_INFOS,
    DEFENSE_PARTY,
)
DEFENSE_MUTATIONS = (SET_DEFENSE_PRESET, SET_DEFENSE_FORMATION)
MUTATIONS = (*DEFENSE_MUTATIONS, SAVE_ATTACK_FORMATION)
BATTLE_ROUTES = (START, END)
ROUTES = (*READ_ROUTES, *BATTLE_ROUTES, *MUTATIONS)
PRACTICE_CONFIG = "colosseum_practice.json"
DEFAULT_POSITIONS = (12, 3, 19, 9)
FORMATION_CELLS = 20
OPPONENT_SLOTS = 3
ACCOUNT_OPTION_FIELDS = (
    "AccountBuffs",
    "GuardianLevel",
    "GuardianMastery",
    "HeavenHold",
    "HeroCollection",
    "ItemCollection",
)


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS colosseum_defense "
        "(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS colosseum_defense_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS colosseum_attack_formations "
        "(preset_id INTEGER PRIMARY KEY, positions TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS colosseum_attack_formation_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL)"
    )


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


def defense_state(account, profile):
    row = account.db.execute("SELECT value FROM colosseum_defense WHERE id=1").fetchone()
    if row:
        return json.loads(row[0]), True
    captured = profile.get("UserColosseum", {}).get("DefensePartyInfo")
    if captured and (captured.get("Preset") or {}).get("Characters") and captured.get("Formation"):
        return captured, True
    if not (account.references.directory / PRACTICE_CONFIG).is_file():
        selected = profile["User"].get("SelectedPresetId", {}).get("ColosseumAttack", 0)
        if not selected:
            return None, False
        preset = owned_party_preset(account.db, profile, selected)
        return {
            "Preset": preset,
            "Formation": {"Id": 0, "Positions": list(DEFAULT_POSITIONS)},
        }, False
    config = account.references.json(PRACTICE_CONFIG)
    if (
        not isinstance(config, dict)
        or set(config) != {"preset_id"}
        or not integer(config["preset_id"], minimum=600)
        or config["preset_id"] >= 600 + COLOSSEUM_PRESET_COUNT
    ):
        raise ValueError("Configure one Colosseum attack preset ID for practice")
    preset = owned_party_preset(account.db, profile, config["preset_id"])
    return {"Preset": preset, "Formation": {"Id": 0, "Positions": list(DEFAULT_POSITIONS)}}, True


def valid_positions(positions, size):
    return (
        isinstance(positions, list)
        and size <= len(positions) <= len(DEFAULT_POSITIONS)
        and all(integer(position) and position <= FORMATION_CELLS for position in positions)
        and all(positions[:size])
        and len(set(positions) - {0}) == len(positions) - positions.count(0)
    )


def defense_preset(profile, value):
    # The defense editor sends a PartyPreset object. Only the roster and gear
    # references are authoritative. Other serialized properties can be derived.
    if not isinstance(value, dict) or not isinstance(value.get("Characters"), list):
        raise ValueError("Save one Colosseum defense preset")
    slots = value["Characters"]
    if len(slots) > len(DEFAULT_POSITIONS):
        raise ValueError("Save at most four Colosseum defenders")
    characters = [
        (
            {key: member[key] for key in ("Id", *GEAR_FIELDS) if key in member}
            if isinstance(member, dict)
            else member
        )
        for member in slots
        if member is not None
    ]
    validate_members(profile, characters)
    name = value.get("Name")
    if name is not None and (
        not isinstance(name, str)
        or len(name) > 64
        or any(0xD800 <= ord(character) <= 0xDFFF for character in name)
    ):
        raise ValueError("Invalid Colosseum defense name")
    return {
        "Id": value["Id"] if integer(value.get("Id")) else 0,
        "Order": value["Order"] if integer(value.get("Order")) else 0,
        "Name": name,
        "Characters": characters,
    }


def save(account, route, body, operation_id):
    fields = {
        SET_DEFENSE_PRESET: {"Preset"},
        SET_DEFENSE_FORMATION: {"Positions"},
        SAVE_ATTACK_FORMATION: {"PresetId", "Positions"},
    }
    if (
        route not in fields
        or not isinstance(body, dict)
        or set(body) != fields[route]
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid Colosseum team or formation save")
    table = (
        "colosseum_attack_formation_requests"
        if route == SAVE_ATTACK_FORMATION
        else "colosseum_defense_requests"
    )
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    previous = account.db.execute(
        f"SELECT route, request FROM {table} WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if previous and previous != (route, encoded):
        raise ValueError("Colosseum save request identity was reused with different data")

    with account.db:
        if not previous:
            profile = account.profile()
            if route == SAVE_ATTACK_FORMATION:
                save_attack_formation(account, profile, body)
            else:
                save_defense(account, profile, route, body)
            account.db.execute(f"INSERT INTO {table} VALUES(?,?,?)", (operation_id, route, encoded))
        response = read(account, DEFENSE_PARTY, None)
        if route in DEFENSE_MUTATIONS:
            # The lobby polls NextRefresh and fetches new cards when it expires.
            response["UserColosseum"]["NextRefresh"] = "2000-01-01T00:00:00+00:00"
        return response


def save_attack_formation(account, profile, body):
    preset_id = body["PresetId"]
    if not integer(preset_id, minimum=600) or preset_id >= 600 + COLOSSEUM_PRESET_COUNT:
        raise ValueError("Select an existing Colosseum attack preset")
    preset = owned_party_preset(account.db, profile, preset_id)
    positions = body["Positions"]
    if not valid_positions(positions, len(preset["Characters"])):
        raise ValueError("Save distinct Colosseum positions on the 20-cell grid")
    account.db.execute(
        "INSERT INTO colosseum_attack_formations VALUES(?,?) "
        "ON CONFLICT(preset_id) DO UPDATE SET positions=excluded.positions",
        (preset_id, json.dumps(positions, separators=(",", ":"))),
    )


def save_defense(account, profile, route, body):
    defense, _ = defense_state(account, profile)
    formation = defense["Formation"] if defense else {"Id": 0, "Positions": list(DEFAULT_POSITIONS)}
    if route == SET_DEFENSE_PRESET:
        preset = defense_preset(profile, body["Preset"])
        if not valid_positions(formation["Positions"], len(preset["Characters"])):
            formation = dict(formation, Positions=list(DEFAULT_POSITIONS))
    else:
        if defense is None or not valid_positions(
            body["Positions"], len(defense["Preset"]["Characters"])
        ):
            raise ValueError("Save distinct Colosseum positions on the 20-cell grid")
        preset = defense["Preset"]
        formation = dict(formation, Positions=body["Positions"])

    account.db.execute(
        "INSERT INTO colosseum_defense VALUES(1,?) "
        "ON CONFLICT(id) DO UPDATE SET value=excluded.value",
        (json.dumps({"Preset": preset, "Formation": formation}, separators=(",", ":")),),
    )


def attack_formations(account, profile):
    formations = dict(profile.get("UserColosseum", {}).get("Formations") or {})
    rows = account.db.execute(
        "SELECT preset_id, positions FROM colosseum_attack_formations"
    ).fetchall()
    if rows:
        sizes = {
            preset["Id"]: len(preset.get("Characters") or [])
            for preset in current_group(account.db)["Presets"]
            if isinstance(preset, dict) and integer(preset.get("Id"))
        }
        for preset_id, encoded in rows:
            positions = json.loads(encoded)
            if sizes.get(preset_id) and valid_positions(positions, sizes[preset_id]):
                formations[str(preset_id)] = {"Id": preset_id, "Positions": positions}
    return formations


def practice_opponents(profile, defense):
    preset = defense["Preset"]
    owner = profile["User"]
    first_id = 2_000_000_000
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
    owner_options = owner.get("Options", {})
    opponent_user.update(
        Cas=0,
        Name=preset.get("Name") or "Practice defense",
        Options={key: owner_options[key] for key in ACCOUNT_OPTION_FIELDS if key in owner_options},
        Party={"Id": 0, "Characters": party_ids},
        Characters=characters,
        ItemWeapons=[row for row in owner["ItemWeapons"] if row["Id"] in equipment_ids],
        ItemMiscs=[row for row in owner["ItemMiscs"] if row["Id"] in equipment_ids],
        ItemStackables=[],
    )
    opponent = {
        "Formation": defense["Formation"],
        "Rank": None,
        "Trophy": profile["UserRecord"].get("ColosseumTrophy", 0),
        "GuildName": "",
    }
    # The lobby only renders after it has three entries and three counters.
    return [dict(opponent, User=dict(opponent_user, Id=user_id)) for user_id in opponent_ids]


def practice_battle(route, request, opponents, last_served_opponents):
    if not isinstance(request, dict) or not integer(request.get("OpponentId"), minimum=1):
        raise ValueError("Select the configured local Colosseum opponent")
    opponent = next((row for row in opponents if row["User"]["Id"] == request["OpponentId"]), None)
    if opponent is None:
        raise ValueError("Select the configured local Colosseum opponent")
    if route == START:
        if set(request) != {"OpponentId", "OpponentParty", "OpponentPositions"}:
            raise ValueError("Invalid Colosseum practice start")
        # The client starts with its cached card. A tap can precede its automatic list refresh.
        for candidate in (opponent, *last_served_opponents):
            user = candidate["User"]
            if (
                user["Id"] == request["OpponentId"]
                and [row["CharacterId"] for row in user["Characters"]] == request["OpponentParty"]
                and candidate["Formation"]["Positions"] == request["OpponentPositions"]
            ):
                return {}
        raise ValueError("Select a served local Colosseum opponent lineup")
    if (
        set(request) != {"OpponentId", "Result", "Damages", "OpponentLevels"}
        or type(request["Result"]) is not int
        or not isinstance(request["Damages"], list)
        or not isinstance(request["OpponentLevels"], list)
    ):
        raise ValueError("Invalid Colosseum practice result")
    return {"AddedTrophy": 0, "AddedItems": []}


def read(account, route, request, *, last_served_opponents=()):
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering Colosseum")
    if route not in (*READ_ROUTES, *BATTLE_ROUTES):
        raise ValueError("Unsupported Colosseum read")
    if route == BATTLE_INFOS:
        if (
            not isinstance(request, dict)
            or set(request) != {"SeasonId", "Tier", "IsAttack"}
            or not integer(request["SeasonId"])
            or type(request["Tier"]) is not int
            or not -0x80000000 <= request["Tier"] <= 0x7FFFFFFF
            or type(request["IsAttack"]) is not bool
        ):
            raise ValueError("Season Stats expects SeasonId, Tier and a Boolean IsAttack")
        return {"Infos": []}
    if route not in BATTLE_ROUTES and request not in (None, {}):
        if route != ENTRY:
            raise ValueError("This Colosseum read accepts no parameters")
        if (
            not isinstance(request, dict)
            or set(request) != {"IsPartial"}
            or type(request["IsPartial"]) is not bool
        ):
            raise ValueError("Colosseum entry expects a Boolean IsPartial cache hint")
    if route == RANKINGS:
        return {"Rankings": []}
    if route == BATTLE_RECORDS:
        return {"BattleRecords": []}
    profile = account.profile()
    if route == RANKING:
        ranking = profile.get("UserColosseum", {}).get("Ranking")
        if ranking is None:
            ranking = profile["UserRecord"].get("ColosseumRank", 0)
        return {"Ranking": ranking or 0}
    defense, practice_enabled = defense_state(account, profile)
    opponents = practice_opponents(profile, defense) if practice_enabled else []
    if route in BATTLE_ROUTES:
        return practice_battle(route, request, opponents, last_served_opponents)
    opponent_ids = [opponent["User"]["Id"] for opponent in opponents]
    challenges = [0] * len(opponent_ids)
    formations = attack_formations(account, profile)
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reset = (midnight + timedelta(days=7 - now.weekday())).isoformat()
    # NeedRefresh compares server time to NextRefresh even with a cached empty list.
    # Renew the deadline on list reads as well, including a session crossing a reset.
    lobby = (
        {"Opponents": opponents}
        if route in OPPONENT_LIST_ROUTES
        else {"SeasonUntil": reset, "DefenseBattleRecords": [], "NewSeason": False}
    )
    if route == DEFENSE_PARTY:
        lobby = {"Changed": False}
    if "UserColosseum" in profile:
        return {
            **lobby,
            "UserColosseum": {
                **profile["UserColosseum"],
                "DefensePartyInfo": defense,
                "Formations": formations,
                "OpponentIds": opponent_ids,
                "Challenges": challenges,
                "NextRefresh": reset,
            },
        }
    record = profile["UserRecord"]
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
            "Formations": formations,
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
