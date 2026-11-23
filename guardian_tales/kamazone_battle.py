# SPDX-License-Identifier: Apache-2.0
"""Kama-ZONE battle results and no-reward closing in the separate local run."""

import hashlib
import json

from .village import integer

END = "/kamazonland/end-battle"
CLOSE = "/kamazonland/close-battle"
ROUTES = (END, CLOSE)
HP_SCALE = 10000


def defaults():
    return dict(hps={}, monster_hps={}, pending_result=None, last_result_hash=None, battle_count=0)


def upgrade(value):
    return dict(defaults(), **value) if isinstance(value, dict) else value


def hp_map(value, maximum):
    return (
        isinstance(value, dict)
        and len(value) <= maximum
        and all(
            key.isascii()
            and key.isdecimal()
            and str(int(key)) == key
            and integer(int(key), minimum=1)
            and integer(hp, maximum=HP_SCALE)
            for key, hp in value.items()
        )
    )


def valid_state(value):
    return (
        hp_map(value["hps"], 1024)
        and isinstance(value["monster_hps"], dict)
        and len(value["monster_hps"]) <= 128
        and all(
            key.isascii()
            and key.isdecimal()
            and str(int(key)) == key
            and integer(int(key), minimum=1)
            and isinstance(hps, list)
            and 1 <= len(hps) <= 25
            and all(integer(hp, maximum=HP_SCALE) for hp in hps)
            for key, hps in value["monster_hps"].items()
        )
        and (
            value["pending_result"] is None
            or integer(value["pending_result"], minimum=1, maximum=4)
        )
        and (
            value["last_result_hash"] is None
            or isinstance(value["last_result_hash"], str)
            and len(value["last_result_hash"]) == 64
            and all(c in "0123456789abcdef" for c in value["last_result_hash"])
        )
        and integer(value["battle_count"])
    )


def matches(value, owned, nodes):
    by_id = {n["Id"]: n for n in nodes}
    return (
        {int(i) for i in value["hps"]} <= owned
        and all(
            int(i) in by_id and len(hps) == len(by_id[int(i)]["BattleMonsters"])
            for i, hps in value["monster_hps"].items()
        )
        and (
            value["pending_result"] is None
            or value["stage_started"]
            and not value["battle_started"]
            and value["last_result_hash"] is not None
        )
    )


def validate(route, request):
    fields = (
        {"NodeId", "Result", "CharacterHps", "MonsterHps"}
        if route == END
        else {"NodeId", "LootArtifactId", "DiscardArtifactIndex"}
    )
    if (
        not isinstance(request, dict)
        or "NodeId" not in request
        or not set(request) <= fields
        or route == END
        and set(request) != fields
        or not integer(request["NodeId"], minimum=1)
    ):
        raise ValueError("Invalid Kama-ZONE battle result/closing request")
    if route == END:
        if (
            not integer(request["Result"], minimum=1, maximum=4)
            or not hp_map(request["CharacterHps"], 4)
            or not isinstance(request["MonsterHps"], list)
            or not 1 <= len(request["MonsterHps"]) <= 25
            or any(not integer(hp, maximum=HP_SCALE) for hp in request["MonsterHps"])
        ):
            raise ValueError("Kama-ZONE results require a native result and bounded HP values")
    elif (
        request.get("LootArtifactId") is not None or request.get("DiscardArtifactIndex") is not None
    ):
        raise ValueError("Kama-ZONE artifact selection is not implemented")


def apply(value, route, request, nodes):
    ident = request["NodeId"]
    node = next((n for n in nodes if n["Id"] == ident), None)
    if (
        not value["active"]
        or ident != value["current_node_id"]
        or not node
        or not node["BattleMonsters"]
    ):
        raise ValueError("Battle result does not match the current Kama-ZONE encounter")
    if route == END:
        fingerprint = hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if not value["battle_started"]:
            if fingerprint == value["last_result_hash"]:
                return
            raise ValueError("Start the Kama-ZONE battle before reporting its result")
        if (
            not {int(i) for i in request["CharacterHps"]} <= set(value["characters"])
            or len(request["MonsterHps"]) != len(node["BattleMonsters"])
            or request["Result"] == 1
            and any(request["MonsterHps"])
            or value["battle_count"] == 0x7FFFFFFF
        ):
            raise ValueError("Kama-ZONE result does not match its party, monsters or victory")
        value["hps"].update(request["CharacterHps"])
        value["monster_hps"][str(ident)] = list(request["MonsterHps"])
        value["states"][str(ident)] = 3 if request["Result"] == 1 else 5
        value.update(
            battle_started=False,
            pending_result=request["Result"],
            last_result_hash=fingerprint,
            battle_count=value["battle_count"] + 1,
        )
    else:
        if value["battle_started"] or value["last_result_hash"] is None:
            raise ValueError("Finish the Kama-ZONE battle before closing it")
        if value["pending_result"] is None:
            if not value["stage_started"]:
                return
            raise ValueError("No Kama-ZONE battle result is ready to close")
        if value["pending_result"] == 1:
            value["states"][str(ident)] |= 8
        value.update(stage_started=False, pending_result=None)


def project(value, owned, user):
    user["Hps"] = {str(i): value["hps"].get(str(i), HP_SCALE) for i in sorted(owned)}
    if value["battle_count"]:
        user["Progress"]["Battle"] = value["battle_count"]
    for node in user["Nodes"]:
        hps = value["monster_hps"].get(str(node["Id"]))
        if hps is not None:
            for monster, hp in zip(node["BattleMonsters"], hps):
                monster["Hp"] = hp


def response(route):
    # This local milestone records combat/HP but creates no loot or balances.
    if route == END:
        return {"ArtifactEffectResults": []}
    if route == CLOSE:
        return {"ChoiceEffectResults": [], "AddedItems": []}
    return {}
