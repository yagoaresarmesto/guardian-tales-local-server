# SPDX-License-Identifier: Apache-2.0
"""Local Kama-ZONE challenge/map and battle entry, separate from account progress."""

import copy
import hashlib
import json
import math
import random
import secrets
from functools import lru_cache

from . import kamazone
from .punchking_static import atomic_write
from .raid_static import decode, records
from .village import integer

CHALLENGE = "/kamazonland/challenge"
SELECT = "/kamazonland/select-characters"
START = "/kamazonland/start-stage"
BATTLE = "/kamazonland/start-battle"
ROUTES = (CHALLENGE, SELECT, START, BATTLE)
STATE = "kamazone_run.json"
HP_SCALE = 10000
COMBAT = ("Normal", "Elite", "Boss")
PROBABILITIES = ("Normal", "Elite", "Shelter", "Shop", "Special")


def valid_formation(value):
    return (
        isinstance(value, dict)
        and set(value) == {"Id", "Positions"}
        and integer(value["Id"])
        and isinstance(value["Positions"], list)
        and len(value["Positions"]) == 4
        and all(integer(i, maximum=24) for i in value["Positions"])
        and len(set(value["Positions"])) == 4
    )


@lru_cache(maxsize=2)
def catalog(source, season_id):
    if season_id not in kamazone.catalog(source):
        raise ValueError("Kama-ZONE challenge requires a preserved Global season")
    mode = json.loads(records(decode(source))[1]["kamazonland2"][1])
    season = kamazone.one(mode["Seasons"], "Id", season_id)
    maximum = season.get("MaxDifficulty")
    if not integer(maximum, maximum=32, minimum=1):
        raise ValueError("Invalid Kama-ZONE season difficulty range")
    tiers = {}
    for difficulty in range(1, maximum + 1):
        rows = [
            r
            for r in mode.get("Difficulty", [])
            if isinstance(r, dict) and r.get("Difficulty") == difficulty and r.get("Floor") == 1
        ]
        if len(rows) != 1 or any(
            not integer(rows[0].get(k), minimum=1)
            for k in ("NormalLevel", "EliteLevel", "BossLevel")
        ):
            raise ValueError("Missing or ambiguous Kama-ZONE difficulty/floor definitions")
        tiers[difficulty] = rows[0]
    floors = [
        r for r in mode.get("FloorPresets", []) if isinstance(r, dict) and r.get("FloorId") == 1
    ]
    if not 2 <= len(floors) <= 128 or any(
        not integer(r.get("Id"), minimum=1) or not integer(r.get("Step")) for r in floors
    ):
        raise ValueError("Invalid opening Kama-ZONE floor graph")
    nodes = {r["Id"]: r for r in floors}
    roots = [r["Id"] for r in floors if r["Step"] == 0]
    if len(nodes) != len(floors) or len(roots) != 1:
        raise ValueError("Kama-ZONE floor requires one starting node and unique IDs")
    for row in floors:
        next_ids = row.get("NextNodeIds")
        if next_ids is not None and (
            not isinstance(next_ids, list)
            or not next_ids
            or len(set(next_ids)) != len(next_ids)
            or any(
                not integer(i, minimum=1) or i not in nodes or nodes[i]["Step"] != row["Step"] + 1
                for i in next_ids
            )
        ):
            raise ValueError("Invalid Kama-ZONE floor connections")
        if row["Id"] != roots[0] and next_ids:
            weights = [row.get(k + "Prob") for k in PROBABILITIES]
            if (
                any(type(w) not in (int, float) or not math.isfinite(w) or w < 0 for w in weights)
                or sum(weights) <= 0
            ):
                raise ValueError("Invalid Kama-ZONE node probabilities")
    monsters = mode.get("Monsters")
    presets = mode.get("BattlePresets")
    if not isinstance(monsters, list) or not isinstance(presets, list):
        raise ValueError("Kama-ZONE battle definitions are missing")
    monsters = [
        r
        for r in monsters
        if isinstance(r, dict)
        and r.get("Hidden") is False
        and integer(r.get("Id"), minimum=1)
        and integer(r.get("MonsterId"), minimum=1)
    ]
    groups = {kind: {} for kind in COMBAT}
    for row in presets:
        if (
            not isinstance(row, dict)
            or row.get("Hidden") is not False
            or row.get("Difficulty") not in groups
        ):
            continue
        if not integer(row.get("GroupId"), minimum=1) or not integer(
            row.get("Position"), maximum=24
        ):
            raise ValueError("Invalid Kama-ZONE battle preset identity/position")
        explicit, classes = row.get("Monster"), row.get("Class")
        candidates = (
            [r["Id"] for r in monsters if r["Id"] == explicit]
            if explicit is not None
            else [
                r["Id"] for r in monsters if isinstance(classes, list) and r.get("Class") in classes
            ]
        )
        groups[row["Difficulty"]].setdefault(row["GroupId"], []).append(
            (row["Position"], candidates)
        )
    for kind, by_id in groups.items():
        groups[kind] = {
            ident: rows
            for ident, rows in by_id.items()
            if rows and len({r[0] for r in rows}) == len(rows) and all(r[1] for r in rows)
        }
        if not groups[kind]:
            raise ValueError("No usable preserved Kama-ZONE " + kind + " battle preset")
    return dict(tiers=tiers, nodes=nodes, starting=roots[0], groups=groups)


@lru_cache(maxsize=4)
def floor_nodes(source, season_id, seed):
    data = catalog(source, season_id)
    rng = random.Random(seed)
    kinds = {}
    for ident, row in sorted(data["nodes"].items()):
        kinds[ident] = (
            "Starting"
            if ident == data["starting"]
            else (
                "Boss"
                if not row.get("NextNodeIds")
                else rng.choices(PROBABILITIES, [row[k + "Prob"] for k in PROBABILITIES])[0]
            )
        )
    # Keep a reachable opening battle for this local entry milestone, choosing
    # only a type with nonzero probability in the original floor definition.
    opening = data["nodes"][data["starting"]].get("NextNodeIds") or []
    if not any(kinds[i] in COMBAT for i in opening):
        first = next((i for i in opening if data["nodes"][i].get("NormalProb", 0) > 0), None)
        if first is None:
            raise ValueError("Opening Kama-ZONE floor has no reachable normal battle")
        kinds[first] = "Normal"
    result = []
    for ident, row in sorted(data["nodes"].items()):
        kind = kinds[ident]
        enemies = []
        if kind in COMBAT:
            groups = data["groups"][kind]
            group = groups[rng.choice(sorted(groups))]
            enemies = [
                dict(Id=rng.choice(ids), Position=position, OptionId=None, Hp=HP_SCALE)
                for position, ids in group
            ]
        result.append(
            dict(
                Id=ident,
                Step=row["Step"],
                Type=kind,
                State=0,
                BattleMonsters=enemies,
                LootArtifacts=[],
                LootCurses=[],
                ShopArtifacts={},
                ShopCurses={},
                ShopEffectArtifacts={},
                SpecialEventChoices={},
                ChoiceEffectResults=[],
            )
        )
    return result


def load(references):
    path = references.directory / STATE
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 32768:
        raise ValueError("Invalid local Kama-ZONE run file")
    value = references.json(STATE)
    # Existing v1 files predate the distinction between opening the encounter
    # panel and loading combat. Reading them must not rewrite their contents.
    if isinstance(value, dict) and "battle_started" not in value:
        value = dict(value, battle_started=False)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "version",
            "source_sha256",
            "season_id",
            "user_id",
            "difficulty",
            "seed",
            "active",
            "stage_started",
            "battle_started",
            "current_node_id",
            "characters",
            "formation",
            "states",
            "seen_operations",
        }
        or type(value["version"]) is not int
        or value["version"] != 1
        or not isinstance(value["source_sha256"], str)
        or len(value["source_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in value["source_sha256"])
        or any(
            not integer(value[k], minimum=1)
            for k in ("season_id", "user_id", "difficulty", "current_node_id")
        )
        or not integer(value["seed"], maximum=0x7FFFFFFFFFFFFFFF)
        or type(value["active"]) is not bool
        or type(value["stage_started"]) is not bool
        or type(value["battle_started"]) is not bool
        or not isinstance(value["characters"], list)
        or len(value["characters"]) > 4
        or any(not integer(i, minimum=1) for i in value["characters"])
        or len(set(value["characters"])) != len(value["characters"])
        or value["formation"] is not None
        and not valid_formation(value["formation"])
        or not isinstance(value["states"], dict)
        or len(value["states"]) > 128
        or any(
            not k.isascii() or not k.isdecimal() or str(int(k)) != k or not integer(v, maximum=15)
            for k, v in value["states"].items()
        )
        or not isinstance(value["seen_operations"], list)
        or len(value["seen_operations"]) > 64
        or any(not isinstance(i, str) or not 1 <= len(i) <= 160 for i in value["seen_operations"])
        or len(set(value["seen_operations"])) != len(value["seen_operations"])
    ):
        raise ValueError("Invalid local Kama-ZONE run state")
    return value


def owner(account):
    user = account.profile().get("User", {})
    roster = user.get("Characters")
    if (
        not integer(user.get("Id"), minimum=1)
        or not isinstance(roster, list)
        or any(not isinstance(r, dict) or not integer(r.get("Id"), minimum=1) for r in roster)
    ):
        raise ValueError("Kama-ZONE challenge requires a valid owned roster")
    return user["Id"], {r["Id"] for r in roster}


def matching(account, source, season_id):
    value = load(account.references)
    user_id, owned = owner(account)
    if (
        value is None
        or value["source_sha256"] != hashlib.sha256(source).hexdigest()
        or (value["season_id"], value["user_id"]) != (season_id, user_id)
    ):
        return None
    data = catalog(source, season_id)
    if (
        value["difficulty"] not in data["tiers"]
        or value["current_node_id"] not in data["nodes"]
        or any(int(k) not in data["nodes"] for k in value["states"])
        or not set(value["characters"]) <= owned
        or value["stage_started"]
        and not value["active"]
        or value["battle_started"]
        and (not value["stage_started"] or not value["characters"] or value["formation"] is None)
    ):
        raise ValueError("Local Kama-ZONE run no longer matches its owner or content")
    return value


def project(account, source, season_id, response):
    value = matching(account, source, season_id)
    if value is None:
        return response
    user = response["UserKamazonLand"]
    _, owned = owner(account)
    user.update(Characters=list(value["characters"]), Hps={str(i): HP_SCALE for i in sorted(owned)})
    if value["formation"] is not None:
        user["Formation"] = copy.deepcopy(value["formation"])
    if value["active"]:
        nodes = copy.deepcopy(floor_nodes(source, season_id, value["seed"]))
        for node in nodes:
            node["State"] = value["states"].get(str(node["Id"]), 0)
        user.update(
            Difficulty=value["difficulty"],
            Nodes=nodes,
            Progress=dict(Floor=1, CurrentNodeId=value["current_node_id"], Concluded=False),
        )
    return response


def handle(account, source, season_id, route, request, operation_id):
    if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 160:
        raise ValueError("Invalid Kama-ZONE operation identity")
    data = catalog(source, season_id)
    previous = matching(account, source, season_id)
    user_id, owned = owner(account)
    if route == CHALLENGE:
        if (
            not isinstance(request, dict)
            or set(request) != {"Difficulty"}
            or (
                not integer(request["Difficulty"], minimum=1)
                or request["Difficulty"] not in data["tiers"]
            )
        ):
            raise ValueError(
                "Select a preserved Kama-ZONE difficulty from 1 to " + str(max(data["tiers"]))
            )
    elif route == SELECT:
        ids = request.get("CharacterIds") if isinstance(request, dict) else None
        if (
            not isinstance(request, dict)
            or set(request) != {"CharacterIds"}
            or not isinstance(ids, list)
            or not 1 <= len(ids) <= 4
            or any(not integer(i, minimum=1) or i not in owned for i in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Select one to four distinct owned Kama-ZONE characters")
    elif route in (START, BATTLE):
        if (
            not isinstance(request, dict)
            or set(request) != ({"NodeId"} if route == START else {"NodeId", "Formation"})
            or not integer(request["NodeId"], minimum=1)
            or route == BATTLE
            and not valid_formation(request["Formation"])
        ):
            raise ValueError("Kama-ZONE stage entry requires a node ID")
        if previous is None or not previous["active"]:
            raise ValueError("Start a Kama-ZONE challenge before entering a node")
    else:
        raise ValueError("Unsupported local Kama-ZONE run operation")
    if previous and operation_id in previous["seen_operations"]:
        return
    value = (
        copy.deepcopy(previous)
        if previous
        else dict(
            version=1,
            source_sha256=hashlib.sha256(source).hexdigest(),
            season_id=season_id,
            user_id=user_id,
            difficulty=min(data["tiers"]),
            seed=0,
            active=False,
            stage_started=False,
            battle_started=False,
            current_node_id=data["starting"],
            characters=[],
            formation=None,
            states={},
            seen_operations=[],
        )
    )
    if route == CHALLENGE:
        value.update(
            difficulty=request["Difficulty"],
            seed=secrets.randbits(63),
            active=True,
            stage_started=False,
            battle_started=False,
            current_node_id=data["starting"],
            states={str(data["starting"]): 8},
        )
        floor_nodes(source, season_id, value["seed"])
    elif route == SELECT:
        if value["battle_started"]:
            raise ValueError("Cannot change Kama-ZONE characters during an active stage")
        value["characters"] = list(ids)
    elif route == BATTLE:
        if not value["stage_started"] or request["NodeId"] != value["current_node_id"]:
            raise ValueError("Enter the selected Kama-ZONE node before loading its battle")
        if not value["characters"]:
            raise ValueError("Select a Kama-ZONE party before loading combat")
        value["formation"] = copy.deepcopy(request["Formation"])
        value["battle_started"] = True
    else:
        ident, current = request["NodeId"], value["current_node_id"]
        # The APK opens the node first. EnterStage then initializes PartyInfo,
        # sends select-characters, and finally calls start-battle from BeforeLoad.
        if value["stage_started"] and ident != current:
            raise ValueError("Finish the active Kama-ZONE stage before moving")
        if not value["stage_started"] and ident not in (
            data["nodes"][current].get("NextNodeIds") or []
        ):
            raise ValueError("The Kama-ZONE node is not connected to the current position")
        nodes = floor_nodes(source, season_id, value["seed"])
        node = next((r for r in nodes if r["Id"] == ident), None)
        if node is None or node["Type"] not in COMBAT or not node["BattleMonsters"]:
            raise ValueError("Only preserved Kama-ZONE battle-node entry is implemented")
        value["current_node_id"] = ident
        value["stage_started"] = True
        value["states"][str(ident)] = 1
    value["seen_operations"] = (value["seen_operations"] + [operation_id])[-64:]
    atomic_write(account.references.directory / STATE, json.dumps(value, indent=2).encode() + b"\n")
