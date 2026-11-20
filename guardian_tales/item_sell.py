# SPDX-License-Identifier: Apache-2.0
"""Sell selected owned item quantities atomically under an explicit no-gold policy."""

import json

from .item_lock import INVENTORIES, MAX_BATCH
from .presets import GEAR_FIELDS
from .snapshots import preserved_read
from .village import MAX_REVISION, integer
from .weapon_enhance import decimal_id

ROUTE = "/item/sell"
EQUIPMENT_FIELDS = frozenset((*GEAR_FIELDS, "Accessory1", "Costume"))


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS item_sell_requests "
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


def protected_ids(account, user):
    characters, training = user.get("Characters"), user.get("TrainingSlots")
    if not isinstance(characters, list) or any(not isinstance(c, dict) for c in characters):
        raise ValueError("Invalid saved character equipment")
    if not isinstance(training, dict) or any(
        not isinstance(slot, dict) or not integer(slot.get("ItemId", 0))
        for slot in training.values()
    ):
        raise ValueError("Invalid saved Training Room assignments")
    protected = gear_references(characters)
    protected.update(slot.get("ItemId", 0) for slot in training.values())
    protected.update(gear_references(preserved_read(account.db, "/preset/get-presets")))
    return protected


def sell(account, body, operation_id):
    if (
        not isinstance(body, dict)
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
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    user = profile["User"]
    if not integer(user.get("Id"), minimum=1) or not integer(user.get("Cas"), MAX_REVISION):
        raise ValueError("Invalid saved sale owner or revision")
    previous = account.db.execute(
        "SELECT request FROM item_sell_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Sale request identity was reused with different items or quantities")
        # Never repeat a debit or restore inventory/balances from an old sale.
        return {"User": user}
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
    protected = protected_ids(account, user)
    targets = []
    for key, count in body["SellItems"].items():
        row = owned.get(int(key))
        if (
            row is None
            or not integer(row.get("ItemId"), minimum=1)
            or not integer(row.get("Amount"), minimum=1)
            or count > row["Amount"]
            or type(row.get("Locked")) is not bool
            or row["Locked"]
            or row["Id"] in protected
            or row.get("JewelSlots") is not None
            and (
                not isinstance(row["JewelSlots"], list)
                or any(jewel not in (None, 0) for jewel in row["JewelSlots"])
            )
        ):
            raise ValueError("Sale requires sufficient unlocked, unequipped and unused owned items")
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
    user["Cas"] += 1
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        for table in ("weapon_option_proposals", "relic_option_proposals"):
            account.db.executemany(
                f"DELETE FROM {table} WHERE item_id=?", ((ident,) for ident in removed)
            )
        account.db.execute("INSERT INTO item_sell_requests VALUES(?,?)", (operation_id, encoded))
    # Explicit local policy: no gold, other rewards or mission credit are granted.
    # Full current inventory arrays replace the client's lists, removing sold rows.
    return {"User": user}
