# SPDX-License-Identifier: Apache-2.0
"""Select an owned frame using the client's inventory-to-design ID contract."""

import json

from guardian_tales.inventory.cosmetic_items import cosmetic_specs
from guardian_tales.settlement.village import MAX_REVISION, integer

ROUTE = "/user/set-portrait-frame"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS portrait_frame_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


def frame_specs(body):
    return cosmetic_specs(body, "portraitframe")


def resource(user):
    # The callback only redraws the portrait. Shared User.Apply consumes this
    # nullable design ID; the request instead contains an inventory item ID.
    return {key: user[key] for key in ("Id", "Cas", "FrameId")}


def select(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"FrameId"}
        or (body["FrameId"] is not None and not integer(body["FrameId"], minimum=1))
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select one owned frame inventory ID, or null, after the prologue")
    profile = account.profile()
    user = profile["User"]
    items = user.get("ItemMiscs")
    revision, current = user.get("Cas"), user.get("FrameId")
    if (
        not integer(user.get("Id"), minimum=1)
        or not integer(revision, MAX_REVISION)
        or "FrameId" not in user
        or (current is not None and not integer(current))
        or not isinstance(items, list)
        or any(
            not isinstance(item, dict)
            or any(not integer(item.get(key), minimum=1) for key in ("Id", "ItemId"))
            or not integer(item.get("Amount"))
            for item in items
        )
        or len({item["Id"] for item in items}) != len(items)
    ):
        raise ValueError("Invalid saved portrait frame, inventory or revision")
    specs = frame_specs(account.references.read_bytes("static_data_get.bin"))
    owned = {
        item["Id"]: item["ItemId"]
        for item in items
        if item["Amount"] > 0 and item["ItemId"] in specs
    }
    if current not in (None, 0) and current not in owned.values():
        raise ValueError("Saved portrait frame must identify an owned frame design")
    encoded = json.dumps(body, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM portrait_frame_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Portrait-frame request identity was reused with different data")
        return {"User": resource(user)}
    requested = body["FrameId"]
    if requested is not None and requested not in owned:
        raise ValueError("Portrait frame must be a positive-amount owned frame inventory item")
    selected = None if requested is None else owned[requested]
    changed = current != selected
    if changed:
        if revision == MAX_REVISION:
            raise ValueError("Portrait-frame revision overflow")
        user["FrameId"] = selected
        user["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO portrait_frame_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {"User": resource(user)}
