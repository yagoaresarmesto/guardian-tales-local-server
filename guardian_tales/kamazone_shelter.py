# SPDX-License-Identifier: Apache-2.0
"""Shelter choices use separate run HP and never alter the saved account."""

import hashlib
import json
import math
import random
from functools import lru_cache

from . import kamazone
from .kamazone_battle import HP_SCALE
from .raid_static import decode, records
from .village import integer

TAKE = "/kamazonland/take-shelter"


def defaults():
    return dict(shelters={}, curses=[])


def upgrade(value):
    return dict(defaults(), **value) if isinstance(value, dict) else value


def valid(value):
    return (
        isinstance(value["shelters"], dict)
        and len(value["shelters"]) <= 128
        and all(
            key.isascii()
            and key.isdecimal()
            and str(int(key)) == key
            and integer(int(key), minimum=1)
            and isinstance(row, dict)
            and set(row) == {"choice"}
            and (row["choice"] is None or integer(row["choice"], maximum=3))
            for key, row in value["shelters"].items()
        )
        and isinstance(value["curses"], list)
        and len(value["curses"]) <= 128
        and all(integer(i, minimum=1) for i in value["curses"])
    )


@lru_cache(maxsize=2)
def catalog(source, season_id):
    mode = json.loads(records(decode(source))[1]["kamazonland2"][1])
    rate = mode.get("Constants", {}).get("ShelterHpRecover")
    if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("Invalid preserved Kama-ZONE shelter recovery rate")
    season = kamazone.one(mode["Seasons"], "Id", season_id)
    curses = season.get("ArtifactsCurse", [])
    if not isinstance(curses, list) or any(not integer(i, minimum=1) for i in curses):
        raise ValueError("Invalid seasonal Kama-ZONE curses")
    return int(rate * 100), frozenset(curses)


def matches(value, source, season_id, nodes):
    by_id = {node["Id"]: node for node in nodes}
    if any(
        int(key) not in by_id or by_id[int(key)]["Type"] != "Shelter" for key in value["shelters"]
    ):
        return False
    if value["shelters"] or value["curses"]:
        _, curses = catalog(source, season_id)
        return set(value["curses"]) <= curses
    return True


def open_shelter(value, source, season_id, node):
    catalog(source, season_id)
    value["shelters"].setdefault(str(node["Id"]), {"choice": None})
    # Back/Confirm closes the native overlay without another API. Cleared lets
    # the map offer successors; Chosen is set after a choice or forfeiting it.
    value["states"][str(node["Id"])] = 3
    value["stage_started"] = False


def skip(value, ident):
    row = value["shelters"].get(str(ident))
    if row is not None and row["choice"] is None:
        row["choice"] = 0
        value["states"][str(ident)] = 11
        value["stage_started"] = False


def validate(request):
    if (
        not isinstance(request, dict)
        or set(request) != {"NodeId", "ChoiceType"}
        or not integer(request["NodeId"], minimum=1)
        or not integer(request["ChoiceType"], maximum=3)
    ):
        raise ValueError("Shelter requires NodeId and native ChoiceType 0..3")


def take(value, source, season_id, request, nodes):
    ident, choice = request["NodeId"], request["ChoiceType"]
    row = value["shelters"].get(str(ident))
    node = next((n for n in nodes if n["Id"] == ident), None)
    if (
        not value["active"]
        or value["current_node_id"] != ident
        or row is None
        or node is None
        or node["Type"] != "Shelter"
        or value["battle_started"]
        or value["pending_result"] is not None
    ):
        raise ValueError("Open the current Kama-ZONE shelter before choosing an action")
    if row["choice"] is not None:
        if row["choice"] == choice:
            return
        raise ValueError("This Kama-ZONE shelter choice has already been used")
    percent, _ = catalog(source, season_id)
    rng = random.Random(
        hashlib.sha256(
            f"local-kamazone-shelter-v1:{value['seed']}:{ident}:{choice}".encode()
        ).digest()
    )
    if choice == 1:
        for key, hp in value["hps"].items():
            if hp > 0:
                value["hps"][key] = min(HP_SCALE, hp + percent * HP_SCALE // 100)
    elif choice == 2:
        dead = sorted(key for key, hp in value["hps"].items() if hp == 0)
        if not dead:
            raise ValueError("No defeated Kama-ZONE hero is available to revive")
        # Native text specifies one random hero but not restored HP. This local
        # trial revives that hero at full HP; it is not a recovered server rule.
        value["hps"][rng.choice(dead)] = HP_SCALE
    elif choice == 3:
        if not value["curses"]:
            raise ValueError("No Kama-ZONE curse is available to purify")
        value["curses"].pop(rng.randrange(len(value["curses"])))
    row["choice"] = choice
    value["states"][str(ident)] = 11
    value["stage_started"] = False


def project(value, user):
    user["Curses"] = list(value["curses"])
    if value["shelters"]:
        user["Progress"]["Shelter"] = len(value["shelters"])


def response(route):
    return {"ChoiceEffectResults": [], "AddedItems": []} if route == TAKE else {}
