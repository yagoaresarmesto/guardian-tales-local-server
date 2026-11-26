# SPDX-License-Identifier: Apache-2.0
"""Persist inventory protection flags without changing equipment or its options."""

import json

from guardian_tales.settlement.village import MAX_REVISION, integer

LOCK = "/item/lock"
UNLOCK = "/item/unlock"
ROUTES = (LOCK, UNLOCK)
INVENTORIES = ("ItemWeapons", "ItemMiscs", "ItemStackables")
MAX_BATCH = 256


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS item_lock_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL)"
    )


def change(account, body, operation_id, route):
    if (
        route not in ROUTES
        or not isinstance(body, dict)
        or set(body) != {"itemIndexes"}
        or not isinstance(body["itemIndexes"], list)
        or not 1 <= len(body["itemIndexes"]) <= MAX_BATCH
        or any(not integer(i, minimum=1) for i in body["itemIndexes"])
        or len(set(body["itemIndexes"])) != len(body["itemIndexes"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Lock or unlock a nonempty batch of distinct owned inventory IDs")
    encoded = json.dumps({"itemIndexes": sorted(body["itemIndexes"])}, separators=(",", ":"))
    profile = account.profile()
    user = profile["User"]
    if not integer(user.get("Id"), minimum=1) or not integer(user.get("Cas"), MAX_REVISION):
        raise ValueError("Invalid saved user identity or revision")
    previous = account.db.execute(
        "SELECT route,request FROM item_lock_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous != (route, encoded):
            raise ValueError("Item-lock request identity was reused with different data")
        return {"User": user}
    with account.db:
        set_item_protection(account.db, profile, body["itemIndexes"], locked=route == LOCK)
        account.db.execute(
            "INSERT INTO item_lock_requests VALUES(?,?,?)", (operation_id, route, encoded)
        )
    return {"User": user}


def set_item_protection(db, profile, item_ids, *, locked):
    """Update only the owned items' protection flags in the caller's transaction."""
    user = profile["User"]
    owned = {}
    for key in INVENTORIES:
        rows = user.get(key)
        if not isinstance(rows, list):
            raise ValueError("Invalid saved item inventory")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not integer(row.get("Id"), minimum=1)
                or row["Id"] in owned
            ):
                raise ValueError("Saved inventory IDs must be valid and globally unambiguous")
            owned[row["Id"]] = row
    targets = []
    for ident in item_ids:
        row = owned.get(ident)
        if (
            row is None
            or not integer(row.get("ItemId"), minimum=1)
            or not integer(row.get("Amount"), minimum=1)
            or type(row.get("Locked")) is not bool
        ):
            raise ValueError(
                "Lock targets must identify existing owned items with protection flags"
            )
        targets.append(row)
    changed = any(row["Locked"] != locked for row in targets)
    if changed:
        if user["Cas"] == MAX_REVISION:
            raise ValueError("Item-lock revision overflow")
        for row in targets:
            row["Locked"] = locked
        user["Cas"] += 1
        db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
