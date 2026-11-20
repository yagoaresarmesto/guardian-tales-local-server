# SPDX-License-Identifier: Apache-2.0
"""Reorder existing Orbital/Raid slots without changing team identities or selections."""

import json

from .presets import MAX_REVISION, RAID_PRESET_COUNT, current_group, integer

ROUTE = "/preset/reorder-preset"
# Matching 3.57.0 EU PresetCountS3 indexed by native PresetType minus one.
SLOT_COUNTS = {4: 5, 7: RAID_PRESET_COUNT}


def reorder(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PresetType", "Order"}
        or type(body["PresetType"]) is not int
        or body["PresetType"] not in SLOT_COUNTS
        or not isinstance(body["Order"], list)
        or len(body["Order"]) != SLOT_COUNTS[body["PresetType"]]
        or any(not integer(value) or value >= len(body["Order"]) for value in body["Order"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Reorder existing Orbital or Raid/Conquest slots using native positions")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_reorder_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    group = current_group(account.db)
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset reorder request identity was reused with different data")
        # A delayed retry never changes later ordering, deletes or recreated slots.
        return {"UserPartyPreset2": group}
    base = body["PresetType"] * 100
    count = SLOT_COUNTS[body["PresetType"]]
    if any(not isinstance(row, dict) or not integer(row.get("Id")) for row in group["Presets"]):
        raise ValueError("Invalid saved party preset identities")
    teams = [row for row in group["Presets"] if base <= row["Id"] < base + 100]
    ids = {row["Id"] for row in teams}
    revision = group.get("Cas")
    if (
        not teams
        or len(ids) != len(teams)
        or any(
            row["Id"] >= base + count or not integer(row.get("Order")) or row["Order"] >= 999
            for row in teams
        )
        or type(revision) is not int
        or not 0 <= revision <= MAX_REVISION
    ):
        raise ValueError("Invalid saved preset slots, order or group revision")
    positions = body["Order"]
    if sorted(positions[ident - base] for ident in ids) != list(range(len(teams))) or any(
        value != 0 and base + slot not in ids for slot, value in enumerate(positions)
    ):
        raise ValueError(
            "Assign each saved team one distinct position; unused slots must remain zero"
        )
    changed = any(row["Order"] != positions[row["Id"] - base] for row in teams)
    if changed:
        if revision == MAX_REVISION:
            raise ValueError("Preset group revision overflow")
        for row in teams:
            row["Order"] = positions[row["Id"] - base]
        group["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "INSERT INTO party_preset_state VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(group, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO preset_reorder_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {"UserPartyPreset2": group}
