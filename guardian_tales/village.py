# SPDX-License-Identifier: Apache-2.0
"""Collect configured village production with atomic balances, clocks and receipts."""

import json
import math
import struct
import time

from .snapshots import CLIENT, preserved_read

ROUTE = "/lobby-village/harvest-all"
SOUL_POINTS = 70012
GOLD = 70001
INT_MAX = 0x7FFFFFFF
MAX_REVISION = 0x7FFFFFFFFFFFFFFF
MAX_TIME = 253402300799


def integer(value, maximum=INT_MAX, minimum=0):
    return type(value) is int and minimum <= value <= maximum


def number(value):
    return type(value) in (int, float) and 0 <= value <= 1000000 and math.isfinite(value)


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS village_state "
        "(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS village_harvest_requests "
        "(operation_id TEXT PRIMARY KEY, result TEXT NOT NULL)"
    )


def current_village(db):
    read = preserved_read(db, "/lobby-village/enter")
    village = read.get("UserLobbyVillage") if isinstance(read, dict) else None
    if not isinstance(village, dict):
        raise ValueError("Harvesting requires a preserved village")
    return village


def load_catalog(references):
    path = references.directory / "village_harvest_catalog.json"
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Village harvesting requires a matching external catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "client",
            "min_seconds",
            "inn_factor",
            "facility_divisor",
            "sp_base_max",
            "rarity_bonus",
            "match_bonus",
            "buildings",
            "followers",
        }
        or value["client"] != CLIENT
        or not integer(value["min_seconds"], 86400, 1)
        or not number(value["inn_factor"])
        or not number(value["facility_divisor"])
        or value["facility_divisor"] == 0
        or not integer(value["sp_base_max"])
        or not integer(value["match_bonus"], 1000)
        or not isinstance(value["rarity_bonus"], list)
        or not 1 <= len(value["rarity_bonus"]) <= 10
        or any(not integer(v, 1000) for v in value["rarity_bonus"])
    ):
        raise ValueError("Invalid village production constants")
    for field in ("buildings", "followers"):
        rows = value[field]
        if (
            not isinstance(rows, dict)
            or not 1 <= len(rows) <= 10000
            or any(not k.isascii() or not k.isdecimal() or str(int(k)) != k for k in rows)
            or any(not isinstance(row, dict) for row in rows.values())
        ):
            raise ValueError("Invalid village production catalog rows")
    for row in value["buildings"].values():
        if row.get("kind") == "inn":
            if (
                set(row)
                != {"kind", "sp_rate", "gold_rate", "sp_storage", "gold_storage", "manufacture_max"}
                or any(not number(row[k]) for k in ("sp_rate", "gold_rate"))
                or any(not integer(row[k]) for k in ("sp_storage", "gold_storage"))
                or not integer(row["manufacture_max"], 10000, 1)
            ):
                raise ValueError("Invalid inn production catalog")
        elif row.get("kind") == "producer":
            effects = row.get("effects")
            if (
                set(row) != {"kind", "specialization", "slots", "effects"}
                or not isinstance(row["specialization"], str)
                or not integer(row["slots"], 100)
                or not isinstance(effects, list)
                or not 1 <= len(effects) <= 20
            ):
                raise ValueError("Invalid facility production catalog")
            for effect in effects:
                if (
                    not isinstance(effect, dict)
                    or set(effect) != {"item_id", "value", "period", "storage"}
                    or type(effect["item_id"]) is not int
                    or effect["item_id"] not in (GOLD, SOUL_POINTS)
                    or not integer(effect["value"])
                    or not integer(effect["period"], 86400, 1)
                    or not integer(effect["storage"])
                ):
                    raise ValueError("Invalid facility production effect")
            if len({effect["item_id"] for effect in effects}) != 1:
                raise ValueError("Mixed-resource facility clocks are not supported")
        elif row != {"kind": "other"}:
            raise ValueError("Unsupported village building catalog")
    for row in value["followers"].values():
        if (
            set(row) != {"rarity", "specialization"}
            or not integer(row["rarity"], len(value["rarity_bonus"]) - 1)
            or not isinstance(row["specialization"], str)
        ):
            raise ValueError("Invalid production follower catalog")
    return value


def collect(user, village, catalog, now):
    """Mutate detached values only; the caller commits them together."""
    if not integer(now, MAX_TIME, 1) or village.get("UserId") != user.get("Id"):
        raise ValueError("Invalid village clock or owner")
    buildings, clocks = village.get("Buildings"), village.get("LastHarvestTime")
    if (
        not isinstance(buildings, list)
        or len(buildings) > 1000
        or any(
            not isinstance(row, dict) or not integer(row.get("Id"), minimum=1) for row in buildings
        )
        or len({row["Id"] for row in buildings}) != len(buildings)
        or not isinstance(clocks, dict)
        or any(not integer(clocks.get(k), MAX_TIME) for k in ("SoulPoint", "Gold"))
    ):
        raise ValueError("Invalid saved village buildings or harvest clocks")
    inn, producers = [], []
    deployed = set()
    owned = village.get("VillagerIds")
    if not isinstance(owned, list) or any(not integer(i) for i in owned):
        raise ValueError("Invalid saved village inhabitants")
    for building in buildings:
        spec = catalog["buildings"].get(str(building.get("SpecId")))
        if not integer(building.get("SpecId"), minimum=1) or spec is None:
            raise ValueError("Unknown saved village building specification")
        if not integer(building.get("Status"), 4):
            raise ValueError("Invalid village building status")
        if spec["kind"] == "inn":
            if building["Status"] not in (0, 2):
                raise ValueError("Harvesting an unfinished inn is not supported")
            inn.append(spec)
        elif spec["kind"] == "producer" and building["Status"] == 2:
            ids = building.get("DeployVillagers")
            if ids is None:
                ids = []
            if (
                not integer(building.get("EndTime"), MAX_TIME)
                or not isinstance(ids, list)
                or len(ids) > spec["slots"]
                or any(
                    not integer(i) or i not in owned or str(i) not in catalog["followers"]
                    for i in ids
                )
                or len(set(ids)) != len(ids)
                or deployed.intersection(ids)
            ):
                raise ValueError("Invalid saved facility clock or deployed inhabitants")
            deployed.update(ids)
            bonus = sum(
                catalog["rarity_bonus"][catalog["followers"][str(i)]["rarity"]]
                + (
                    catalog["match_bonus"]
                    if catalog["followers"][str(i)]["specialization"] == spec["specialization"]
                    else 0
                )
                for i in ids
            )
            elapsed = now - building["EndTime"]
            amount = 0
            if building["EndTime"] > 0 and elapsed >= catalog["min_seconds"]:
                production = sum(
                    e["value"] / catalog["facility_divisor"] * (elapsed // e["period"])
                    for e in spec["effects"]
                )
                # Native code divides the percentage in float32, then applies
                # it to double production before the per-building cap/truncate.
                percentage = struct.unpack("<f", struct.pack("<f", bonus / 100))[0]
                production += production * percentage
                amount = int(min(production, sum(e["storage"] for e in spec["effects"])))
            producers.append((building, spec["effects"][0]["item_id"], amount))
    if len(inn) != 1:
        raise ValueError("Harvesting requires exactly one saved inn")
    inn = inn[0]
    manufacture = village.get("Manufacture")
    if (
        not isinstance(manufacture, list)
        or len(manufacture) != 3
        or any(not isinstance(row, dict) or type(row.get("Type")) is not int for row in manufacture)
        or {row["Type"] for row in manufacture} != {1, 2, 3}
        or any(not integer(row.get("Level"), inn["manufacture_max"], 1) for row in manufacture)
    ):
        raise ValueError("Invalid saved inn manufacture levels")
    elapsed_sp, elapsed_gold = now - clocks["SoulPoint"], now - clocks["Gold"]
    inn_sp = inn_gold = 0
    if clocks["SoulPoint"] > 0 and elapsed_sp >= catalog["min_seconds"]:
        inn_sp = int(
            min(
                inn["sp_storage"],
                sum(
                    inn["sp_rate"] * (catalog["inn_factor"] + row["Level"]) * elapsed_sp / 3
                    for row in sorted(manufacture, key=lambda row: row["Type"])
                ),
            )
        )
    if clocks["Gold"] > 0 and elapsed_gold >= catalog["min_seconds"]:
        inn_gold = int(min(inn["gold_storage"], inn["gold_rate"] * elapsed_gold))
    totals = {SOUL_POINTS: inn_sp, GOLD: inn_gold}
    for _, item, amount in producers:
        totals[item] += amount
    assets = {}
    for item in totals:
        rows = [a for a in user.get("Assets", []) if isinstance(a, dict) and a.get("Id") == item]
        if len(rows) != 1 or not integer(rows[0].get("Amount")):
            raise ValueError("Harvesting requires valid saved soul-point and gold assets")
        assets[item] = rows[0]
    adjustment = assets[SOUL_POINTS].get("MaxAdj")
    if not integer(adjustment, minimum=-0x80000000):
        raise ValueError("Invalid saved soul-point capacity adjustment")
    maximum = catalog["sp_base_max"] + adjustment
    if not integer(maximum, minimum=1):
        raise ValueError("Invalid saved soul-point capacity")
    # Explicit local collection policy: cap to free balance capacity, consume
    # eligible clocks only when that resource is credited, discard capped excess.
    granted = {
        SOUL_POINTS: min(totals[SOUL_POINTS], max(0, maximum - assets[SOUL_POINTS]["Amount"])),
        GOLD: min(totals[GOLD], INT_MAX - assets[GOLD]["Amount"]),
    }
    notices = [{"ItemId": item, "Amount": amount} for item, amount in granted.items() if amount]
    if notices:
        for value in (user.get("Cas"), village.get("Cas")):
            if not integer(value, MAX_REVISION - 1):
                raise ValueError("Invalid account or village revision")
        for item, amount in granted.items():
            assets[item]["Amount"] += amount
        if inn_sp and granted[SOUL_POINTS]:
            clocks["SoulPoint"] = now
        if inn_gold and granted[GOLD]:
            clocks["Gold"] = now
        for building, item, amount in producers:
            if amount and granted[item]:
                building["EndTime"] = now
        user["Cas"] += 1
        village["Cas"] += 1
    return notices


def harvest(account, body, operation_id, now=None):
    if (
        body not in (None, {})
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Village harvesting accepts no parameters after the prologue")
    profile = account.profile()
    village = current_village(account.db)
    previous = account.db.execute(
        "SELECT result FROM village_harvest_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        return {
            "User": profile["User"],
            "UserLobbyVillage": village,
            "AddedItems": json.loads(previous[0]),
        }
    catalog = load_catalog(account.references)
    now = int(time.time()) if now is None else now
    notices = collect(profile["User"], village, catalog, now)
    with account.db:
        if notices:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
            account.db.execute(
                "INSERT INTO village_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(village, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO village_harvest_requests VALUES(?,?)",
            (operation_id, json.dumps(notices, separators=(",", ":"))),
        )
    return {"User": profile["User"], "UserLobbyVillage": village, "AddedItems": notices}
