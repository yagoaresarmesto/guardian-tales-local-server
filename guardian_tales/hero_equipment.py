# SPDX-License-Identifier: Apache-2.0
"""Atomic owned-hero equipment changes with persistent retry identities."""

import json
from functools import lru_cache

from .head_hunter_static import active_spec as head_hunter_spec
from .raid_static import decode, records
from .test_item_static import active_specs
from .village import MAX_REVISION, integer

ROUTES = {
    "/user/change-weapons": ("Weapon1", "Weapon2"),
    "/user/change-accessory": ("Accessory1",),
    "/user/change-orb": ("Orb", "Slot"),
    "/user/change-merch": ("Merch",),
    "/user/change-relic": ("Relic",),
}
SLOTS = ("Weapon1", "Weapon2", "Accessory1", "Orb1", "Orb2", "Merch", "Relic")


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS hero_equipment_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL)"
    )


@lru_cache(maxsize=2)
def catalog(body):
    tables = records(decode(body))[1]
    result = []
    for name in ("heroes", "items"):
        rows = json.loads(tables.get(name, (0, "null", 0))[1])
        if (
            not isinstance(rows, list)
            or not 1 <= len(rows) <= 100000
            or any(not isinstance(r, dict) or not integer(r.get("Id"), minimum=1) for r in rows)
            or len({r["Id"] for r in rows}) != len(rows)
        ):
            raise ValueError("Hero equipment requires matching unambiguous hero/item tables")
        result.append({r["Id"]: r for r in rows})
    return tuple(result)


def resource(user):
    # Send the complete current roster, including displaced holders and explicit
    # null slots. Do not replace inventories, presets, currencies or progression.
    return {key: user[key] for key in ("Id", "Cas", "Characters")}


def selection(route, body):
    if (
        route not in ROUTES
        or not isinstance(body, dict)
        or set(body) != {"CharacterId", *ROUTES[route]}
        or not integer(body["CharacterId"], minimum=1)
    ):
        raise ValueError("Invalid hero equipment request")
    fields = ROUTES[route]
    if route == "/user/change-orb":
        if not integer(body["Slot"], 2, 1):
            raise ValueError("Select card slot one or two")
        changes = {"Orb" + str(body["Slot"]): body["Orb"]}
    else:
        changes = {field: body[field] for field in fields}
    if any(value is not None and not integer(value) for value in changes.values()):
        raise ValueError("Equipment references must be nullable owned inventory IDs")
    changes = {key: value or None for key, value in changes.items()}
    selected = [value for value in changes.values() if value is not None]
    if len(set(selected)) != len(selected):
        raise ValueError("One equipment instance cannot occupy two slots")
    return changes


def validate_item(field, row, kind, item, hero):
    if not integer(row.get("Amount"), minimum=1):
        raise ValueError("Equip an available owned item")
    expected = "ItemWeapons" if field in ("Weapon1", "Weapon2", "Accessory1") else "ItemMiscs"
    if kind != expected:
        raise ValueError("Equipment is in the wrong inventory")
    item_type = item.get("Type")
    if field in ("Weapon1", "Weapon2", "Accessory1"):
        weapon_type = item.get("WeaponType")
        if item_type != "weapon" or not isinstance(weapon_type, str):
            raise ValueError("Select an owned weapon or accessory for this slot")
        if field == "Accessory1":
            if weapon_type != "accessory":
                raise ValueError("The accessory slot requires an accessory")
            return
        compatible = hero.get("CompatibleWeapons")
        allowed = compatible.get("default") if isinstance(compatible, dict) else None
        if (
            not isinstance(allowed, list)
            or weapon_type not in allowed
            or field == "Weapon1"
            and weapon_type in ("accessory", "shield", "enhance", "custom")
            or field == "Weapon2"
            and weapon_type != "shield"
        ):
            raise ValueError("Weapon type is incompatible with this hero or hand")
    elif item_type != ("orb" if field.startswith("Orb") else field.lower()):
        raise ValueError("Equipment type does not match the selected slot")


def change(account, body, operation_id, route):
    changes = selection(route, body)
    if (
        not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Change equipment after the prologue with a valid request identity")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    user = profile["User"]
    previous = account.db.execute(
        "SELECT route,request FROM hero_equipment_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if tuple(previous) != (route, encoded):
            raise ValueError("Equipment request identity was reused for another selection or route")
        return {"User": resource(user)}
    characters = user.get("Characters")
    if (
        not integer(user.get("Id"), minimum=1)
        or not integer(user.get("Cas"), MAX_REVISION)
        or not isinstance(characters, list)
        or any(not isinstance(c, dict) or not integer(c.get("Id"), minimum=1) for c in characters)
        or len({c["Id"] for c in characters}) != len(characters)
        or any(
            c.get(field) is not None and not integer(c[field])
            for c in characters
            for field in SLOTS
        )
    ):
        raise ValueError("Invalid saved hero roster, equipment references or revision")
    targets = [c for c in characters if c["Id"] == body["CharacterId"]]
    if len(targets) != 1:
        raise ValueError("Select one owned inventory hero")
    target = targets[0]
    owned = {}
    for kind in ("ItemWeapons", "ItemMiscs", "ItemStackables"):
        rows = user.get(kind)
        if not isinstance(rows, list):
            raise ValueError("Invalid saved equipment inventory")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not integer(row.get("Id"), minimum=1)
                or row["Id"] in owned
            ):
                raise ValueError("Owned inventory IDs must be unambiguous")
            owned[row["Id"]] = kind, row
    heroes, originals = catalog(account.references.read_bytes("static_data_get.bin"))
    items = dict(originals)
    for encoded_spec in active_specs(account.db):
        spec = json.loads(encoded_spec)
        if spec["Id"] in items:
            raise ValueError("Test equipment collides with the original catalog")
        items[spec["Id"]] = spec
    head_hunter = head_hunter_spec(account.db, account.references)
    if head_hunter is not None:
        spec = json.loads(head_hunter)
        if spec["Id"] in items:
            raise ValueError("Head Hunter trial collides with the original catalog")
        items[spec["Id"]] = spec
    hero = (
        heroes.get(target.get("CharacterId"))
        if integer(target.get("CharacterId"), minimum=1)
        else None
    )
    if hero is None:
        raise ValueError("Missing owned hero specification")
    for field, ident in changes.items():
        if ident is None:
            continue
        kind, row = owned.get(ident, (None, {}))
        if not integer(row.get("ItemId"), minimum=1):
            raise ValueError("Invalid owned equipment specification")
        spec = items.get(row.get("ItemId"))
        if spec is None:
            raise ValueError("Equipment must identify an owned catalog item")
        validate_item(field, row, kind, spec, hero)
    selected = {ident for ident in changes.values() if ident is not None}
    changed = False
    for character in characters:
        for field in SLOTS:
            if character.get(field) in selected and not (
                character is target and changes.get(field) == character[field]
            ):
                character[field] = None
                changed = True
    for field, ident in changes.items():
        if field not in target or target[field] != ident:
            target[field] = ident
            changed = True
    if changed:
        if user["Cas"] == MAX_REVISION:
            raise ValueError("Hero equipment revision overflow")
        user["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO hero_equipment_requests VALUES(?,?,?)", (operation_id, route, encoded)
        )
    return {"User": resource(user)}
