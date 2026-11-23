# SPDX-License-Identifier: Apache-2.0
"""Seasonal Kama-ZONE shops, run-local silver purchases and closing."""

import hashlib
import random
from functools import lru_cache

from . import kamazone
from . import kamazone_event_effects as effects
from .village import integer

CLOSE = "/kamazonland/close-shop"
BUY = "/kamazonland/buy-shop-item"
ROUTES = (BUY, CLOSE)
MAX_STOCK = 3


@lru_cache(maxsize=2)
def catalog(source, season_id):
    mode = kamazone.mode_data(source)
    specs = kamazone.artifact_specs(source)
    season = kamazone.one(mode["Seasons"], "Id", season_id)
    available, excluded = season.get("Artifacts"), season.get("ArtifactsException", [])
    if any(
        not isinstance(ids, list) or any(not integer(i, minimum=1) for i in ids)
        for ids in (available, excluded)
    ):
        raise ValueError("Kama-ZONE shop requires preserved seasonal artifact definitions")
    prices = {}
    for ident in sorted(set(available) - set(excluded)):
        row = specs.get(ident)
        if row is None:
            raise ValueError("Missing seasonal shop artifact")
        if (
            row.get("Kind") == "Normal"
            and row.get("Lootable") is True
            and integer(row.get("Price"), minimum=1)
        ):
            prices[ident] = row["Price"]
    if not prices:
        raise ValueError("No preserved normal artifacts are available for this Kama-ZONE shop")
    discounts = {}
    for ident, row in specs.items():
        if row.get("EffectType") == "MallShopDiscount":
            values = row.get("EffectValue")
            if not isinstance(values, list) or not values or not integer(values[0], maximum=100):
                raise ValueError("Invalid Kama-ZONE shop discount")
            discounts[ident] = values[0]
    return prices, discounts


def stock(source, season_id, seed, node_id):
    # A separate stream keeps every existing map type and monster roll intact.
    token = f"local-kamazone-shop-v1:{season_id}:{seed}:{node_id}".encode()
    rng = random.Random(hashlib.sha256(token).digest())
    prices, _ = catalog(source, season_id)
    choices = sorted(prices)
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
    prices, _ = catalog(source, season_id)
    return all(
        int(key) in by_id
        and by_id[int(key)]["Type"] == "Shop"
        and {int(i) for i in items} <= prices.keys()
        for key, items in value["shops"].items()
    )


def open_shop(value, source, season_id, node):
    key = str(node["Id"])
    if key not in value["shops"]:
        value["shops"][key] = stock(source, season_id, value["seed"], node["Id"])


def validate(route, request):
    if not isinstance(request, dict) or not integer(request.get("NodeId"), minimum=1):
        raise ValueError("Kama-ZONE shop actions require a node ID")
    if route == CLOSE:
        if set(request) != {"NodeId"}:
            raise ValueError("Unexpected Kama-ZONE shop closing fields")
    else:
        index = request.get("DiscardArtifactOrCurseIndex")
        if (
            not set(request) <= {"NodeId", "ChoiceArtifactOrCurseId", "DiscardArtifactOrCurseIndex"}
            or not integer(request.get("ChoiceArtifactOrCurseId"), minimum=1)
            or index is not None
            and not integer(index, maximum=effects.LIMIT - 1)
        ):
            raise ValueError("Select a shop artifact and an optional replacement slot")


def handle(value, source, season_id, route, request, nodes):
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
        raise ValueError("Enter the current Kama-ZONE shop first")
    if not value["stage_started"] and (route != CLOSE or value["states"].get(str(ident)) != 11):
        raise ValueError("No Kama-ZONE shop is open")
    if route == CLOSE:
        value["states"][str(ident)] = 11
        value["stage_started"] = False
        return

    item = request["ChoiceArtifactOrCurseId"]
    stock = value["shops"][str(ident)]
    if stock.get(str(item)) is not False:
        raise ValueError("The selected artifact is unavailable or sold out")
    prices, discounts = catalog(source, season_id)
    inventory = value["artifacts"]
    discount = min(100, sum(discounts.get(row["Id"], 0) for row in inventory))
    price = prices[item] * (100 - discount) // 100
    if value["silver_coin"] < price:
        raise ValueError("Not enough Kama-ZONE silver coins")
    index = request.get("DiscardArtifactOrCurseIndex")
    if index is not None and len(inventory) < effects.LIMIT:
        raise ValueError("Only a full shop inventory requires a replacement")
    effects.add_reward(inventory, item, index, artifact=True)
    value["silver_coin"] -= price
    stock[str(item)] = True


def project(value, user):
    for node in user["Nodes"]:
        items = value["shops"].get(str(node["Id"]))
        if items is not None:
            node["ShopArtifacts"] = dict(items)


def response(route):
    return {"ChoiceEffectResults": [], "AddedItems": []} if route == CLOSE else {}
