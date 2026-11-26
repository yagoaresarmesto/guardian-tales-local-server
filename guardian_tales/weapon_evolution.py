# SPDX-License-Identifier: Apache-2.0
"""Evolve owned equipment through the normal and Grade 6 forges."""

import json
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache

from .admin_test_items import save_profile
from .inventory_panel.equipment_options import generate, rules_for
from .inventory_panel.equipment_ribbons import available_in_client
from .inventory_panel.weapon_progression import LIMIT_BREAK_TYPES
from .jewel_upgrade import owned_inventory
from .raid_static import decode, records
from .snapshots import CLIENT
from .test_item_static import item_definitions
from .village import INT_MAX, MAX_REVISION, integer
from .weapon_options import valid_options

ROUTE = "/item/evolve-weapon-bundle"
MYTH_ROUTE = "/item/myth-weapon"
ROUTES = (ROUTE, MYTH_ROUTE)


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_evolution_requests "
        "(operation_id TEXT PRIMARY KEY, selection TEXT NOT NULL)"
    )


@lru_cache(maxsize=2)
def catalog(body):
    tables = records(decode(body))[1]
    effects = {row["Id"] for row in json.loads(tables.get("options", (0, "[]"))[1])}
    specs = {
        spec["Id"]: spec
        for spec in item_definitions(body)
        if spec.get("Type") == "weapon"
        and spec.get("WeaponType") in LIMIT_BREAK_TYPES
        and integer(spec.get("Rarity"), 5)
        and spec.get("SortingNumber") != -1
    }
    enhancement = json.loads(tables.get("weaponenhance", (0, "{}"))[1])
    myth_origins = {
        step["OriginRarity"]
        for step in enhancement.get("WeaponMyth", [])
        if step.get("Rarity") == 5 and integer(step.get("OriginRarity"), 4)
    }
    return specs, effects, myth_origins


def chain(spec, specs, to_max, now, *, max_rarity=4):
    version = tuple(map(int, CLIENT["version"].split(".")))
    while spec["Rarity"] < max_rarity:
        links = spec.get("EvolveTo") or {}
        if not isinstance(links, dict):
            raise ValueError("Invalid equipment evolution link")
        ident = links.get("KakaoGlobal", links.get("Default"))
        if not ident:
            break
        target = specs.get(ident)
        if target is None or not available_in_client(target, version, now):
            break
        if (
            target["Rarity"] != spec["Rarity"] + 1
            or target["WeaponType"] != spec["WeaponType"]
            or not spec.get("NameWithoutRarity")
            or target.get("NameWithoutRarity") != spec["NameWithoutRarity"]
            or target.get("OriginRarity") != spec.get("OriginRarity")
        ):
            raise ValueError("Invalid equipment evolution chain")
        yield target
        if not to_max:
            break
        spec = target


def evolved_options(saved, target, effects):
    if saved and not valid_options(saved):
        raise ValueError("Invalid saved equipment options")
    rules = rules_for(target, effects)
    if rules is None:
        if target.get("MinOptions") == target.get("MaxOptions") == 0 and not target.get("Options"):
            return None
        raise ValueError("Missing option rules for the evolved equipment")
    previous = {r["OptionId"]: r for r in saved or []}
    # Keep compatible rolls and lock flags, bringing levels into the new catalog range.
    levels = {
        ident: min(rule["high"], max(rule["low"], previous[ident]["Level"]))
        for ident, rule in rules["options"].items()
        if ident in previous
    }
    levels = generate(rules, [], levels)
    return [
        dict(
            OptionId=ident,
            Level=levels[ident],
            Locked=previous.get(ident, {}).get("Locked", False),
            OptionSource=0,
        )
        for ident in rules["options"]
        if ident in levels
    ]


def apply_batch(profile, ids, to_max, specs, effects, *, myth_origins=None):
    user, record = profile["User"], profile["UserRecord"]
    if not integer(user.get("Cas"), MAX_REVISION - 1) or not integer(
        record.get("Cas"), MAX_REVISION - 1
    ):
        raise ValueError("Invalid saved evolution revision")
    all_ids = [row.get("Id") for row in owned_inventory(user)]
    if not all(integer(i, minimum=1) for i in all_ids) or len(set(all_ids)) != len(all_ids):
        raise ValueError("Ambiguous inventory IDs")
    weapons = {row["Id"]: row for row in user["ItemWeapons"]}
    grade_six = myth_origins is not None
    if grade_six:
        slots = user.get("TrainingSlots", {})
        if not isinstance(slots, dict) or any(
            not isinstance(slot, dict) or slot.get("ItemId") == ids[0] for slot in slots.values()
        ):
            raise ValueError("Select a weapon outside the Training Room")
    now = datetime.now(timezone.utc)
    gains = Counter()
    for ident in ids:
        item = weapons.get(ident, {})
        if not integer(item.get("ItemId"), minimum=1) or not integer(item.get("Amount"), 1, 1):
            raise ValueError("Select owned equipment copies")
        source = specs.get(item["ItemId"])
        if grade_six and (
            not source or source["Rarity"] != 4 or source.get("OriginRarity") not in myth_origins
        ):
            raise ValueError("Select a 5-star weapon eligible for Grade 6 evolution")
        steps = (
            list(chain(source, specs, to_max, now, max_rarity=5 if grade_six else 4))
            if source
            else []
        )
        if not steps:
            raise ValueError("This equipment has no available evolution in the selected forge")
        for target in steps:
            # Grade 6 upgrades the weapon's base stats and keeps its per-copy rolls.
            if not grade_six:
                item["Options"] = evolved_options(item.get("Options"), target, effects)
            item["ItemId"] = target["Id"]
            gains[str(target["Rarity"])] += 1
    counts = record.setdefault("EvolveWeaponCount", {})
    if not isinstance(counts, dict):
        raise ValueError("Invalid saved equipment evolution counters")
    for rank, n in gains.items():
        if not integer(counts.get(rank, 0), INT_MAX - n):
            raise ValueError("Invalid saved equipment evolution count")
        counts[rank] = counts.get(rank, 0) + n
    record["Cas"] += 1


def evolve(account, body, operation_id, route=ROUTE):
    if (
        not isinstance(body, dict)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid equipment evolution request")
    if route == MYTH_ROUTE:
        if set(body) != {"targetWeaponId"} or not integer(body["targetWeaponId"], minimum=1):
            raise ValueError("Select one owned weapon for Grade 6 evolution")
        ids = [body["targetWeaponId"]]
        to_max = False
        selection = json.dumps([route, ids[0]])
    elif (
        route == ROUTE
        and set(body) == {"WeaponIds", "EvolveToMaxRarity", "discountBuff"}
        and type(body["EvolveToMaxRarity"]) is bool
        and type(body["discountBuff"]) is bool
        and isinstance(body["WeaponIds"], list)
        and body["WeaponIds"]
        and all(integer(i, minimum=1) for i in body["WeaponIds"])
        and len(set(body["WeaponIds"])) == len(body["WeaponIds"])
    ):
        ids = sorted(body["WeaponIds"])
        to_max = body["EvolveToMaxRarity"]
        selection = json.dumps([ids, to_max, body["discountBuff"]])
    else:
        raise ValueError("Invalid equipment evolution selection")
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        receipt = db.execute(
            "SELECT selection FROM weapon_evolution_requests WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if receipt:
            if receipt[0] != selection:
                raise ValueError("Equipment evolution retry has a different selection")
        else:
            specs, effects, origins = catalog(account.references.read_bytes("static_data_get.bin"))
            apply_batch(
                profile,
                ids,
                to_max,
                specs,
                effects,
                myth_origins=origins if route == MYTH_ROUTE else None,
            )
            db.executemany(
                "DELETE FROM weapon_option_proposals WHERE item_id=?", ((i,) for i in ids)
            )
            save_profile(db, profile)
            db.execute(
                "INSERT INTO weapon_evolution_requests VALUES(?,?)", (operation_id, selection)
            )
    return {"User": profile["User"], "UserRecord": profile["UserRecord"]}
