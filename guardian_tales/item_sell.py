# SPDX-License-Identifier: Apache-2.0
"""Shared protected inventory removal for zero-reward sales and extraction."""

import json

from .item_lock import INVENTORIES, MAX_BATCH
from .presets import GEAR_FIELDS
from .snapshots import preserved_read
from .village import MAX_REVISION, integer
from .weapon_enhance import decimal_id, load_catalog

ROUTE = "/item/sell"
EXTRACT = "/item/extract"
RECEIPTS = {ROUTE: "item_sell_requests", EXTRACT: "item_extract_requests"}
EQUIPMENT_FIELDS = frozenset((*GEAR_FIELDS, "Accessory1", "Costume"))


def create_tables(db):
    for table in RECEIPTS.values():
        db.execute(
            f"CREATE TABLE IF NOT EXISTS {table} "
            "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
        )


def gear_references(value):
    """Read both native character fields and saved preset equipment references."""
    result = set()
    if isinstance(value, list):
        for row in value:
            result.update(gear_references(row))
    elif isinstance(value, dict):
        for key, row in value.items():
            if key in EQUIPMENT_FIELDS:
                if row is not None and not integer(row):
                    raise ValueError("Invalid saved equipment reference")
                if row:
                    result.add(row)
            elif key == "EquipCostumes":
                if row is None:
                    continue
                if not isinstance(row, dict) or any(
                    ident is not None and not integer(ident) for ident in row.values()
                ):
                    raise ValueError("Invalid saved equipment-costume references")
                result.update(ident for ident in row.values() if ident)
            else:
                result.update(gear_references(row))
    return result


def protected_ids(db, user):
    characters, training = user.get("Characters"), user.get("TrainingSlots")
    if not isinstance(characters, list) or any(not isinstance(c, dict) for c in characters):
        raise ValueError("Invalid saved character equipment")
    if not isinstance(training, dict) or any(
        not isinstance(slot, dict) or not integer(slot.get("ItemId", 0))
        for slot in training.values()
    ):
        raise ValueError("Invalid saved Training Room assignments")
    # Validate nullable character slots, then detach them only after the entire
    # removal batch passes. Equipment costumes still require their own contract.
    gear_references(characters)
    protected = gear_references(
        [{"EquipCostumes": character.get("EquipCostumes")} for character in characters]
    )
    protected.update(slot.get("ItemId", 0) for slot in training.values())
    protected.update(gear_references(preserved_read(db, "/preset/get-presets")))
    return protected


def sell(account, body, operation_id):
    return dispose(account, body, operation_id)


def dispose(account, body, operation_id, *, route=ROUTE, native_request=None):
    if (
        route not in RECEIPTS
        or not isinstance(body, dict)
        or set(body) != {"SellItems"}
        or not isinstance(body["SellItems"], dict)
        or not 1 <= len(body["SellItems"]) <= MAX_BATCH
        or any(
            not decimal_id(key) or not integer(count, minimum=1)
            for key, count in body["SellItems"].items()
        )
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Sell a bounded map of owned inventory IDs to positive quantities")
    encoded = json.dumps(
        body if native_request is None else native_request, sort_keys=True, separators=(",", ":")
    )
    profile = account.profile()
    user = profile["User"]
    if not integer(user.get("Id"), minimum=1) or not integer(user.get("Cas"), MAX_REVISION):
        raise ValueError("Invalid saved sale owner or revision")
    for saved_route, table in RECEIPTS.items():
        previous = account.db.execute(
            f"SELECT request FROM {table} WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if previous:
            if saved_route != route or previous[0] != encoded:
                raise ValueError("Item-removal identity was reused for another route or selection")
            # Never repeat a debit or restore inventory/balances from an old request.
            return {"User": user}
    extractable = load_catalog(account.references)["weapons"] if route == EXTRACT else None
    with account.db:
        remove_owned_items(account.db, profile, body["SellItems"], extractable=extractable)
        account.db.execute(f"INSERT INTO {RECEIPTS[route]} VALUES(?,?)", (operation_id, encoded))
    return {"User": user}


def remove_owned_items(db, profile, quantities, *, extractable=None):
    """Remove validated copies and their pending rolls in the caller's transaction."""
    user = profile["User"]
    owned = {}
    for key in INVENTORIES:
        rows = user.get(key)
        if not isinstance(rows, list):
            raise ValueError("Invalid saved sale inventory")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not integer(row.get("Id"), minimum=1)
                or row["Id"] in owned
            ):
                raise ValueError("Sale inventory IDs must be globally unambiguous")
            owned[row["Id"]] = row
    protected = protected_ids(db, user)
    weapon_ids = {row["Id"] for row in user["ItemWeapons"]}
    targets = []
    for key, count in quantities.items():
        row = owned.get(int(key))
        if (
            row is None
            or not integer(row.get("ItemId"), minimum=1)
            or not integer(row.get("Amount"), minimum=1)
            or count > row["Amount"]
            or type(row.get("Locked")) is not bool
            or extractable is not None
            and (
                row["Id"] not in weapon_ids
                or row["Amount"] != 1
                or extractable.get(str(row["ItemId"])) != 4
            )
        ):
            raise ValueError("Removal requires sufficient unlocked items outside protected uses")
        if row["Locked"]:
            raise ValueError(f"Unlock copy #{key} first.")
        if row["Id"] in protected:
            raise ValueError(
                f"Remove copy #{key} from presets, Training Room or equipment costumes first."
            )
        sockets = row.get("JewelSlots")
        if sockets is not None and (
            not isinstance(sockets, list) or any(jewel not in (None, 0) for jewel in sockets)
        ):
            raise ValueError(f"Detach the jewels from copy #{key} in the game first.")
        targets.append((row, count))
    if user["Cas"] == MAX_REVISION:
        raise ValueError("Sale revision overflow")
    removed = set()
    for row, count in targets:
        row["Amount"] -= count
        if row["Amount"] == 0:
            removed.add(row["Id"])
    for key in INVENTORIES:
        user[key] = [row for row in user[key] if row["Id"] not in removed]
    for character in user["Characters"]:
        for field in EQUIPMENT_FIELDS:
            if character.get(field) in removed:
                # Explicit null clears the slot through native CharacterInfo.Apply.
                character[field] = None
    user["Cas"] += 1
    db.execute(
        "UPDATE local_account SET profile=? WHERE id=1",
        (json.dumps(profile, separators=(",", ":")),),
    )
    # Fresh imports may predate creation of the in-game option proposal tables.
    for table in ("weapon_option_proposals", "relic_option_proposals"):
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            db.executemany(f"DELETE FROM {table} WHERE item_id=?", ((ident,) for ident in removed))
