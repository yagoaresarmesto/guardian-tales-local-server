# SPDX-License-Identifier: Apache-2.0
"""Local wishlist weapon draws with atomic payment, inventory and frozen retries."""

import json
import secrets
from datetime import datetime, timezone
from functools import lru_cache

from guardian_tales.inventory.items import inventory_item
from guardian_tales.modes.guild.raid_static import decode, records
from guardian_tales.settlement.village import INT_MAX, MAX_REVISION, integer

from .summon_draw import load_draw_catalog, result_response
from .summon_payment import pay, validate_request

ROUTE = "/summon/select-weapon"
MAGIC_METAL = 70008


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_summon_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, "
        "results TEXT NOT NULL, created_at TEXT NOT NULL)"
    )


@lru_cache(maxsize=2)
def weapon_catalog(body):
    _, tables = records(decode(body))
    if not {"items", "constants", "weaponenhance"} <= tables.keys():
        raise ValueError("Weapon draws require matching items, constants and enhancement data")
    items = json.loads(tables["items"][1])
    constants = json.loads(tables["constants"][1])
    enhancement = json.loads(tables["weaponenhance"][1])
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= 100000
        or any(
            not isinstance(item, dict)
            or not integer(item.get("Id"), minimum=1)
            or not isinstance(item.get("Type"), str)
            for item in items
        )
        or len({item["Id"] for item in items}) != len(items)
        or not isinstance(constants, dict)
        or not isinstance(enhancement, dict)
        or not isinstance(enhancement.get("Constants"), dict)
        or not isinstance(enhancement.get("LevelExps"), list)
    ):
        raise ValueError("Invalid external weapon-draw definitions")
    level = constants.get("SummonWeaponBaseLevel")
    metal = enhancement["Constants"].get("MagicMetalPerSummonWeapon")
    levels = enhancement["LevelExps"]
    if (
        not integer(level, len(levels), minimum=1)
        or not integer(metal, minimum=1)
        or any(
            not isinstance(row, dict)
            or type(row.get("Level")) is not int
            or row["Level"] != index
            or not integer(row.get("TotalExps"), minimum=1)
            for index, row in enumerate(levels)
        )
        or any(a["TotalExps"] >= b["TotalExps"] for a, b in zip(levels, levels[1:]))
    ):
        raise ValueError("Invalid initial weapon level, experience or metal reward")
    weapons = {}
    for item in items:
        if item["Type"] != "weapon" or item.get("Summonable") is not True:
            continue
        rank, origin = item.get("Rarity"), item.get("OriginRarity")
        if not integer(rank, 5) or not integer(origin, 5):
            raise ValueError("Invalid summonable weapon rank")
        if rank != origin or rank == 5 or item.get("Limited") is not False:
            continue
        weapons[item["Id"]] = rank
    if {category(rank) for rank in weapons.values()} != {"Normal", "Story", "Unique"}:
        raise ValueError("Each local weapon category requires eligible base definitions")
    return weapons, level, levels[level - 1]["TotalExps"], metal


def category(rank):
    return "Normal" if rank < 2 else "Story" if rank < 4 else "Unique"


def draw(account, body, operation_id, regular=False):
    validate_request(body, regular)
    if (
        not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Weapon draws require a valid request identity and completed prologue")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    previous = account.db.execute(
        "SELECT request,results FROM weapon_summon_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Weapon-summon request identity was reused with different data")
        return result_response(profile, json.loads(previous[1]))
    policy = load_draw_catalog(account.references)
    weapons, level, experience, metal = weapon_catalog(
        account.references.read_bytes("static_data_get.bin")
    )
    user, shop, record = (profile[k] for k in ("User", "UserShop", "UserRecord"))
    selected = shop.get("SelectedSummonWeapons")
    if not regular and (
        not isinstance(selected, list)
        or len(selected) != 5
        or any(not integer(i, minimum=1) or weapons.get(i) != 4 for i in selected)
        or len(set(selected)) != 5
    ):
        raise ValueError("Save five distinct eligible epic weapon designs before drawing")
    count = body["Count"]
    if (
        not integer(user.get("Id"), minimum=1)
        or any(
            not integer(r.get("UserId"), minimum=1) or r["UserId"] != user["Id"]
            for r in (shop, record)
        )
        or not integer(user.get("Cas"), MAX_REVISION - 1)
        or not integer(record.get("Cas"), MAX_REVISION - 1)
        or not integer(record.get("SummonWeaponCount"), INT_MAX - count)
        or not integer(user.get("ItemIdCounter"), INT_MAX - count)
    ):
        raise ValueError("Invalid weapon-summon owner, counters or exhausted revisions")
    inventory = []
    for name in ("ItemMiscs", "ItemStackables", "ItemWeapons"):
        rows = user.get(name)
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or any(not integer(row.get(k), minimum=1) for k in ("Id", "ItemId"))
            or not integer(row.get("Amount"))
            for row in rows
        ):
            raise ValueError("Invalid saved weapon-draw inventory")
        inventory.extend(row["Id"] for row in rows)
    if len(set(inventory)) != len(inventory) or any(i > user["ItemIdCounter"] for i in inventory):
        raise ValueError("Weapon inventory IDs must be unique and covered by the allocator")
    assets = user.get("Assets")
    if (
        not isinstance(assets, list)
        or any(not isinstance(row, dict) or not integer(row.get("Id"), minimum=1) for row in assets)
        or len({row["Id"] for row in assets}) != len(assets)
    ):
        raise ValueError("Invalid saved weapon-summon asset IDs")
    assets = {row["Id"]: row for row in assets}
    mileage = policy["mileage_asset_id"]
    if (
        len({70003, MAGIC_METAL, mileage}) != 3
        or not {70003, MAGIC_METAL, mileage} <= assets.keys()
        or any(
            not integer(assets[i].get("Amount"))
            or not integer(assets[i].get("Spent"), MAX_REVISION)
            for i in (70003, MAGIC_METAL, mileage)
        )
        or assets[MAGIC_METAL]["Amount"] > INT_MAX - metal * count
        or assets[mileage]["Amount"] > INT_MAX - count
    ):
        raise ValueError("Invalid summon currencies or reward balance overflow")
    pay(profile, policy, body, account.references, "Weapon")
    pools = {
        name: [spec for spec, rank in sorted(weapons.items()) if category(rank) == name]
        for name in ("Normal", "Story", "Unique")
    }
    if not regular:
        pools["Unique"] = selected
    weights = policy["category_weights"]
    results = []
    for _ in range(count):
        roll = secrets.randbelow(sum(weights.values()))
        for name in sorted(weights):
            if roll < weights[name]:
                break
            roll -= weights[name]
        pool = pools[name]
        spec = pool[secrets.randbelow(len(pool))]
        user["ItemIdCounter"] += 1
        item = inventory_item(user["ItemIdCounter"], spec)
        item["Experience"] = experience
        user["ItemWeapons"].append(item)
        results.append(
            {
                "Type": 0,
                "ItemId": item["Id"],
                "SpecId": spec,
                "State": 1,
                "StateValue": 0,
                "Level": level,
                "Rank": weapons[spec],
            }
        )
    assets[MAGIC_METAL]["Amount"] += metal * count
    assets[mileage]["Amount"] += count
    user["Cas"] += 1
    record["SummonWeaponCount"] += count
    record["Cas"] += 1
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO weapon_summon_requests VALUES(?,?,?,?)",
            (
                operation_id,
                encoded,
                json.dumps(results, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return result_response(profile, results)
