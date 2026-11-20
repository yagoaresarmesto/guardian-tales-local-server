# SPDX-License-Identifier: Apache-2.0
"""Configured local hero draws with atomic costs, rewards and frozen retry results."""

import json
import secrets
from datetime import datetime, timezone

from .characters import new_character
from .snapshots import is_imported
from .summon_payment import pay, validate_request
from .village import INT_MAX, MAX_REVISION, integer

CATEGORIES = {"Normal", "Story", "Unique"}


def load_draw_catalog(references):
    if not (references.directory / "summon_draw_catalog.json").is_file():
        raise ValueError("An explicit local summon-draw catalog is required")
    value = references.json("summon_draw_catalog.json")
    keys = {
        "heroes",
        "origin_by_spec",
        "category_weights",
        "duplicate_crystals",
        "gem_costs",
        "ticket_item_id",
        "selectable_ticket_item_id",
        "hero_crystal_asset_id",
        "mileage_asset_id",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Invalid local summon-draw catalog")
    for name in (
        "ticket_item_id",
        "selectable_ticket_item_id",
        "hero_crystal_asset_id",
        "mileage_asset_id",
    ):
        if type(value[name]) is not int or not 1 <= value[name] <= 0x7FFFFFFF:
            raise ValueError("Invalid summon currency or ticket identifier")
    if len({value["hero_crystal_asset_id"], value["mileage_asset_id"], 70003}) != 3:
        raise ValueError("Summon reward currencies must be distinct")
    if value["ticket_item_id"] == value["selectable_ticket_item_id"]:
        raise ValueError("Summon ticket kinds must be distinct")
    for name in ("category_weights", "duplicate_crystals", "gem_costs"):
        expected = {"1", "10"} if name == "gem_costs" else CATEGORIES
        row = value[name]
        if (
            not isinstance(row, dict)
            or set(row) != expected
            or any(type(v) is not int or not 1 <= v <= 1000000 for v in row.values())
        ):
            raise ValueError("Invalid configured summon costs, weights or duplicate rewards")
    heroes = value["heroes"]
    if not isinstance(heroes, dict) or not 1 <= len(heroes) <= 2000:
        raise ValueError("Invalid local hero pool")
    for key, row in heroes.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or int(key) > 0x7FFFFFFF
            or not isinstance(row, dict)
            or set(row) != {"rank", "category"}
            or not isinstance(row["category"], str)
            or row["category"] not in CATEGORIES
            or type(row["rank"]) is not int
            or not 0 <= row["rank"] <= 4
        ):
            raise ValueError("Invalid local hero definition")
    if {r["category"] for r in heroes.values()} != CATEGORIES:
        raise ValueError("Every configured summon category needs a hero pool")
    origins = value["origin_by_spec"]
    if not isinstance(origins, dict) or not 1 <= len(origins) <= 20000:
        raise ValueError("Invalid hero-origin mapping")
    for key, origin in origins.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or int(key) > 0x7FFFFFFF
            or type(origin) is not int
            or str(origin) not in heroes
        ):
            raise ValueError("Invalid hero-origin mapping")
    if any(origins.get(key) != int(key) for key in heroes):
        raise ValueError("Every origin must map to itself")
    return value


def result_response(profile, results):
    return {
        "User": profile["User"],
        "UserShop": profile["UserShop"],
        "UserRecord": profile["UserRecord"],
        "Summons": results,
    }


def draw_characters(account, request, operation_id, regular=False):
    validate_request(request, regular)
    if (
        not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Hero draws require a valid request identity and completed prologue")
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request,results FROM character_summon_requests WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Summon request identity was already used for a different draw")
        return result_response(account.profile(), json.loads(previous[1]))
    catalog = load_draw_catalog(account.references)
    profile = account.profile()
    user = profile["User"]
    shop = profile["UserShop"]
    selected = shop.get("SelectedSummonCharacters")
    heroes = catalog["heroes"]
    if not regular and (
        not isinstance(selected, list)
        or len(selected) != 5
        or any(
            type(i) is not int or str(i) not in heroes or heroes[str(i)]["category"] != "Unique"
            for i in selected
        )
        or len(set(selected)) != 5
    ):
        raise ValueError("Save five distinct configured Unique hero origins before drawing")
    count = request["Count"]
    record = profile["UserRecord"]
    if (
        not integer(user.get("Id"), minimum=1)
        or any(
            not integer(row.get("UserId"), minimum=1) or row["UserId"] != user["Id"]
            for row in (shop, record)
        )
        or not integer(user.get("Cas"), MAX_REVISION - 1)
        or not integer(record.get("Cas"), MAX_REVISION - 1)
        or not integer(record.get("SummonCharacterCount"), INT_MAX - count)
    ):
        raise ValueError("Invalid hero-summon owner, counters or exhausted revisions")
    rows = user.get("Assets")
    if (
        not isinstance(rows, list)
        or any(not isinstance(row, dict) or not integer(row.get("Id"), minimum=1) for row in rows)
        or len({row["Id"] for row in rows}) != len(rows)
    ):
        raise ValueError("Invalid saved hero-summon asset IDs")
    assets = {a["Id"]: a for a in rows}
    required = (70003, catalog["hero_crystal_asset_id"], catalog["mileage_asset_id"])
    if any(
        i not in assets or type(assets[i]["Amount"]) is not int or assets[i]["Amount"] < 0
        for i in required
    ):
        raise ValueError("Saved summon currency balances are invalid")
    pay(profile, catalog, request, account.references, "Character")
    owned = {}
    imported = is_imported(account.db)
    for character in user["Characters"]:
        if imported and str(character["CharacterId"]) not in catalog["origin_by_spec"]:
            raise ValueError("Imported hero origin is not covered by the configured draw catalog")
        origin = catalog["origin_by_spec"].get(
            str(character["CharacterId"]), character["CharacterId"]
        )
        if origin in owned:
            raise ValueError("Saved account already has duplicate hero origins")
        owned[origin] = character
    counter = user["CharacterIdCounter"]
    if (
        type(counter) is not int
        or not 0 <= counter <= 0x7FFFFFFF - count
        or any(c["Id"] > counter for c in user["Characters"])
    ):
        raise ValueError("Invalid saved character counter")
    pools = {
        category: [int(i) for i, r in heroes.items() if r["category"] == category]
        for category in CATEGORIES
    }
    if not regular:
        pools["Unique"] = list(selected)
    categories = sorted(CATEGORIES)
    weights = catalog["category_weights"]
    total = sum(weights.values())
    results = []
    for _ in range(count):
        roll = secrets.randbelow(total)
        for category in categories:
            if roll < weights[category]:
                break
            roll -= weights[category]
        pool = pools[category]
        origin = pool[secrets.randbelow(len(pool))]
        duplicate = origin in owned
        crystals = catalog["duplicate_crystals"][category] if duplicate else 0
        if not duplicate:
            user["CharacterIdCounter"] += 1
            owned[origin] = new_character(user["CharacterIdCounter"], origin)
            user["Characters"].append(owned[origin])
        assets[catalog["hero_crystal_asset_id"]]["Amount"] += crystals
        results.append(
            {
                "Type": 1,
                "ItemId": owned[origin]["Id"],
                "SpecId": origin,
                "State": 2 if duplicate else 1,
                "StateValue": crystals,
                "Level": 1,
                "Rank": heroes[str(origin)]["rank"],
            }
        )
    assets[catalog["mileage_asset_id"]]["Amount"] += count
    if any(a["Amount"] > 0x7FFFFFFF for a in assets.values()):
        raise ValueError("Summon currency balance overflow")
    user["Cas"] += 1
    profile["UserRecord"]["SummonCharacterCount"] += count
    profile["UserRecord"]["Cas"] += 1
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO character_summon_requests VALUES(?,?,?,?)",
            (
                operation_id,
                encoded,
                json.dumps(results, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return result_response(profile, results)
