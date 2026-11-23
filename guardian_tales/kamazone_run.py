# SPDX-License-Identifier: Apache-2.0
"""Local Kama-ZONE challenge/map and battle entry, separate from account progress."""

import copy
import hashlib
import json
import math
import random
import secrets
from functools import lru_cache

from . import (
    kamazone,
    kamazone_battle,
    kamazone_event_effects,
    kamazone_events,
    kamazone_shelter,
    kamazone_shop,
)
from .punchking_static import atomic_write
from .raid_static import decode, records
from .village import integer

CHALLENGE = "/kamazonland/challenge"
SELECT = "/kamazonland/select-characters"
START = "/kamazonland/start-stage"
BATTLE = "/kamazonland/start-battle"
CONCLUDE = "/kamazonland/conclude"
ROUTES = (
    CHALLENGE,
    SELECT,
    START,
    BATTLE,
    CONCLUDE,
    *kamazone_battle.ROUTES,
    *kamazone_events.ROUTES,
    kamazone_shop.CLOSE,
    kamazone_shelter.TAKE,
)
STATE = "kamazone_run.json"
HP_SCALE = 10000
COMBAT = ("Normal", "Elite", "Boss")
NODE_TYPES = ("Starting", *COMBAT, "Shelter", "Shop", "Special")
ENTRY_TYPES = (*COMBAT, "Shelter", "Shop", "Special")
PROBABILITIES = ("Normal", "Elite", "Shelter", "Shop", "Special")


def valid_positions(value):
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(integer(i, maximum=24) for i in value)
        and len(set(value)) == 4
    )


def valid_formation(value):
    return (
        isinstance(value, dict)
        and set(value) == {"Id", "Positions"}
        and integer(value["Id"])
        and valid_positions(value["Positions"])
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
    value = kamazone_events.upgrade(
        kamazone_shelter.upgrade(kamazone_battle.upgrade(references.json(STATE)))
    )
    # Existing v1 files predate the distinction between opening the encounter
    # panel and loading combat. Reading them must not rewrite their contents.
    if isinstance(value, dict) and "battle_started" not in value:
        value = dict(value, battle_started=False)
    if isinstance(value, dict) and "shops" not in value:
        value = dict(value, shops={})
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
            "shops",
            *kamazone_shelter.defaults(),
            *kamazone_battle.defaults(),
            *kamazone_events.defaults(),
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
        or not kamazone_battle.valid_state(value)
        or not kamazone_shop.valid(value["shops"])
        or not kamazone_shelter.valid(value)
        or not kamazone_events.valid(value)
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
    nodes = floor_nodes(source, season_id, value["seed"])
    if (
        value["difficulty"] not in data["tiers"]
        or value["current_node_id"] not in data["nodes"]
        or any(int(k) not in data["nodes"] for k in value["states"])
        or not set(value["characters"]) <= owned
        or value["stage_started"]
        and not value["active"]
        or value["battle_started"]
        and (not value["stage_started"] or not value["characters"] or value["formation"] is None)
        or not kamazone_battle.matches(value, owned, nodes)
        or not kamazone_shop.matches(value, source, season_id, nodes)
        or not kamazone_shelter.matches(value, source, season_id, nodes)
        or not kamazone_events.matches(value, source, season_id, nodes)
    ):
        raise ValueError("Local Kama-ZONE run no longer matches its owner or content")
    kamazone_battle.finish_empty_victory(
        value, next(node for node in nodes if node["Id"] == value["current_node_id"])
    )
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
    if value["active"] or value["states"]:
        nodes = copy.deepcopy(floor_nodes(source, season_id, value["seed"]))
        for node in nodes:
            node["State"] = value["states"].get(str(node["Id"]), 0)
        user.update(
            Difficulty=value["difficulty"],
            Nodes=nodes,
            Progress=dict(
                Floor=1, CurrentNodeId=value["current_node_id"], Concluded=not value["active"]
            ),
        )
        kamazone_battle.project(value, owned, user)
        kamazone_shop.project(value, user)
        kamazone_shelter.project(value, user)
        kamazone_events.project(value, user)
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
            and not valid_positions(request["Formation"])
        ):
            raise ValueError(
                "Kama-ZONE battle entry requires a node ID and four formation positions"
                if route == BATTLE
                else "Kama-ZONE stage entry requires a node ID"
            )
        if previous is None or not previous["active"]:
            raise ValueError("Start a Kama-ZONE challenge before entering a node")
    elif route in kamazone_battle.ROUTES:
        kamazone_battle.validate(route, request)
        if previous is None or not previous["active"]:
            raise ValueError("Start a Kama-ZONE challenge before reporting combat")
    elif route == kamazone_shop.CLOSE:
        if previous is None:
            raise ValueError("Open a Kama-ZONE shop before closing it")
        # Validate before checking receipts as with the other native operations.
        kamazone_shop.validate(request)
    elif route == kamazone_shelter.TAKE:
        kamazone_shelter.validate(request)
        if previous is None:
            raise ValueError("Open a Kama-ZONE shelter before choosing an action")
    elif route == CONCLUDE:
        # Native Finish Challenge sends this nullable, lower-camel-case field.
        # Artifact keep/loot is not implemented; never accept an invented ID.
        if (
            not isinstance(request, dict)
            or set(request) != {"keepingArtifactId"}
            or request["keepingArtifactId"] is not None
        ):
            raise ValueError(
                "Kama-ZONE finish requires keepingArtifactId=null; artifact keep is unavailable"
            )
        if previous is None or not previous["states"]:
            raise ValueError("Start a Kama-ZONE challenge before finishing it")
    elif route in kamazone_events.ROUTES:
        kamazone_events.validate(route, request)
        if previous is None:
            raise ValueError("Open a Kama-ZONE special event before choosing/closing it")
    else:
        raise ValueError("Unsupported local Kama-ZONE run operation")
    if previous and operation_id in previous["seen_operations"]:
        return response_extras(route)
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
            shops={},
            **kamazone_battle.defaults(),
            **kamazone_shelter.defaults(),
            **kamazone_events.defaults(),
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
            shops={},
            **kamazone_battle.defaults(),
            **kamazone_shelter.defaults(),
        )
        floor_nodes(source, season_id, value["seed"])
        kamazone_events.reset(value)
    elif route == SELECT:
        if value["battle_started"] or value["pending_result"] == 1:
            raise ValueError("Cannot change Kama-ZONE characters during an active stage")
        value["characters"] = list(ids)
    elif route == BATTLE:
        if not value["stage_started"] or request["NodeId"] != value["current_node_id"]:
            raise ValueError("Enter the selected Kama-ZONE node before loading its battle")
        if not value["characters"]:
            raise ValueError("Select a Kama-ZONE party before loading combat")
        node = next(
            n for n in floor_nodes(source, season_id, value["seed"]) if n["Id"] == request["NodeId"]
        )
        if node["Type"] not in COMBAT or not node["BattleMonsters"]:
            raise ValueError("Only a Kama-ZONE combat node can load a battle")
        if value["pending_result"] == 1 or any(
            value["hps"].get(str(i), HP_SCALE) == 0 for i in value["characters"]
        ):
            raise ValueError("Close the cleared battle or select surviving Kama-ZONE heroes")
        # BeforeLoad sends Formation.Positions, not the Formation model itself.
        # The shared singleton and local state still require the model object.
        value["formation"] = dict(
            Id=(value["formation"] or {}).get("Id", 0), Positions=list(request["Formation"])
        )
        value["battle_started"] = True
        value["states"][str(request["NodeId"])] = 1
        value.update(pending_result=None, last_result_hash=None)
    elif route in kamazone_battle.ROUTES:
        count = value["battle_count"]
        kamazone_battle.apply(value, route, request, floor_nodes(source, season_id, value["seed"]))
        if value["battle_count"] != count:
            kamazone_event_effects.tick(value, "Battle")
    elif route == kamazone_shop.CLOSE:
        kamazone_shop.close(value, request, floor_nodes(source, season_id, value["seed"]))
    elif route == kamazone_shelter.TAKE:
        kamazone_shelter.take(
            value, source, season_id, request, floor_nodes(source, season_id, value["seed"])
        )
    elif route in kamazone_events.ROUTES:
        kamazone_events.handle(value, source, season_id, route, request, owned)
    elif route == CONCLUDE:
        if value["active"]:
            if (
                value["current_node_id"] == data["starting"]
                or value["battle_started"]
                or value["pending_result"] == 1
            ):
                raise ValueError(
                    "Leave the starting position and resolve combat/loot before finishing"
                )
            # Retain the ended run for the native summary and read-only reopen.
            # This closes a local challenge; it does not clear the season or
            # grant floor rewards, account currency or artifact keep rights.
            value.update(
                active=False, stage_started=False, battle_started=False, pending_result=None
            )
    else:
        ident, current = request["NodeId"], value["current_node_id"]
        if ident != current and ident in (data["nodes"][current].get("NextNodeIds") or []):
            kamazone_shelter.skip(value, current)
        # The APK opens the node first. EnterStage then initializes PartyInfo,
        # sends select-characters, and finally calls start-battle from BeforeLoad.
        if value["pending_result"] == 1:
            raise ValueError("Close the cleared Kama-ZONE battle before moving")
        if value["stage_started"] and ident != current:
            raise ValueError("Finish the active Kama-ZONE stage before moving")
        if not value["stage_started"]:
            retry = ident == current and value["states"].get(str(current), 0) & 4
            retry = retry or (
                ident == current
                and str(current) in value["shelters"]
                and value["shelters"][str(current)]["choice"] is None
            )
            advance = (
                current == data["starting"] or value["states"].get(str(current), 0) & 2
            ) and ident in (data["nodes"][current].get("NextNodeIds") or [])
            if not retry and not advance:
                raise ValueError("The Kama-ZONE node is not connected to a cleared position")
        nodes = floor_nodes(source, season_id, value["seed"])
        node = next((r for r in nodes if r["Id"] == ident), None)
        if (
            node is None
            or node["Type"] not in ENTRY_TYPES
            or node["Type"] in COMBAT
            and not node["BattleMonsters"]
        ):
            raise ValueError("This Kama-ZONE node requires an unimplemented special-event handler")
        if node["Type"] == "Shop":
            kamazone_shop.open_shop(value, source, season_id, node)
        value["current_node_id"] = ident
        value["stage_started"] = True
        value["states"][str(ident)] = 1
        if node["Type"] == "Shelter":
            new_visit = str(ident) not in value["shelters"]
            kamazone_shelter.open_shelter(value, source, season_id, node)
            if new_visit:
                kamazone_event_effects.tick(value, "Shelter")
        if node["Type"] == "Special":
            kamazone_events.open_event(value, source, season_id, node, owned)
        value.update(pending_result=None, last_result_hash=None)
    value["seen_operations"] = (value["seen_operations"] + [operation_id])[-64:]
    encoded = json.dumps(value, indent=2).encode() + b"\n"
    if not kamazone_events.valid(value) or len(encoded) > 32768:
        raise ValueError("Local Kama-ZONE event state exceeds its bounded format")
    atomic_write(account.references.directory / STATE, encoded)
    return response_extras(route)


def response_extras(route):
    return (
        kamazone_battle.response(route)
        | kamazone_shop.response(route)
        | kamazone_shelter.response(route)
        | kamazone_events.response(route)
    )
