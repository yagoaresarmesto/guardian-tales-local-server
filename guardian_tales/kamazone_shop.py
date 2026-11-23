# SPDX-License-Identifier: Apache-2.0
"""Preserved seasonal shop inventory and exit, without purchases or currency grants."""

import hashlib
import json
import random
from functools import lru_cache

from . import kamazone
from .raid_static import decode, records
from .village import integer

CLOSE = "/kamazonland/close-shop"
MAX_STOCK = 3


@lru_cache(maxsize=2)
def catalog(source, season_id):
    mode = json.loads(records(decode(source))[1]["kamazonland2"][1])
    season = kamazone.one(mode["Seasons"], "Id", season_id)
    available, excluded = season.get("Artifacts"), season.get("ArtifactsException", [])
    if any(
        not isinstance(ids, list) or any(not integer(i, minimum=1) for i in ids)
        for ids in (available, excluded)
    ) or not isinstance(mode.get("Artifacts"), list):
        raise ValueError("Kama-ZONE shop requires preserved seasonal artifact definitions")
    eligible = []
    for ident in sorted(set(available) - set(excluded)):
        row = kamazone.one(mode["Artifacts"], "Id", ident)
        if (
            row.get("Kind") == "Normal"
            and row.get("Lootable") is True
            and integer(row.get("Price"), minimum=1)
        ):
            eligible.append(ident)
    if not eligible:
        raise ValueError("No preserved normal artifacts are available for this Kama-ZONE shop")
    return tuple(eligible)


def stock(source, season_id, seed, node_id):
    # A separate stream keeps every existing map type and monster roll intact.
    token = f"local-kamazone-shop-v1:{season_id}:{seed}:{node_id}".encode()
    rng = random.Random(hashlib.sha256(token).digest())
    choices = catalog(source, season_id)
    return {str(i): False for i in sorted(rng.sample(choices, min(MAX_STOCK, len(choices))))}


def valid(shops):
    return (
        isinstance(shops, dict)
        and len(shops) <= 128
        and all(
            key.isascii()
            and key.isdecimal()
            and str(int(key)) == key
            and integer(int(key), minimum=1)
            and isinstance(items, dict)
            and 1 <= len(items) <= MAX_STOCK
            and all(
                ident.isascii()
                and ident.isdecimal()
                and str(int(ident)) == ident
                and integer(int(ident), minimum=1)
                and type(sold) is bool
                for ident, sold in items.items()
            )
            for key, items in shops.items()
        )
    )


def matches(value, source, season_id, nodes):
    if not value["shops"]:
        return True
    by_id = {node["Id"]: node for node in nodes}
    eligible = set(catalog(source, season_id))
    return all(
        int(key) in by_id
        and by_id[int(key)]["Type"] == "Shop"
        and {int(i) for i in items} <= eligible
        for key, items in value["shops"].items()
    )


def open_shop(value, source, season_id, node):
    key = str(node["Id"])
    if key not in value["shops"]:
        value["shops"][key] = stock(source, season_id, value["seed"], node["Id"])


def validate(request):
    if (
        not isinstance(request, dict)
        or set(request) != {"NodeId"}
        or not integer(request["NodeId"], minimum=1)
    ):
        raise ValueError("Kama-ZONE shop closing requires a node ID")


def close(value, request, nodes):
    validate(request)
    ident = request["NodeId"]
    node = next((n for n in nodes if n["Id"] == ident), None)
    if (
        not value["active"]
        or ident != value["current_node_id"]
        or node is None
        or node["Type"] != "Shop"
        or str(ident) not in value["shops"]
        or value["battle_started"]
        or value["pending_result"] is not None
    ):
        raise ValueError("Open the current Kama-ZONE shop before closing it")
    if not value["stage_started"] and value["states"].get(str(ident)) != 11:
        raise ValueError("No Kama-ZONE shop is open")
    value["states"][str(ident)] = 11
    value["stage_started"] = False


def project(value, user):
    for node in user["Nodes"]:
        items = value["shops"].get(str(node["Id"]))
        if items is not None:
            node["ShopArtifacts"] = dict(items)


def response(route):
    return {"ChoiceEffectResults": [], "AddedItems": []} if route == CLOSE else {}
