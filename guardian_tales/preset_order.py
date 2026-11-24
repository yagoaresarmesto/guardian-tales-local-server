# SPDX-License-Identifier: Apache-2.0
"""Reorder Orbital, Raid, Guild War, Expedition and Tetis preset slots."""

import json

from .presets import (
    MAX_REVISION,
    RAID_PRESET_COUNT,
    TETIS_PRESET_COUNT,
    current_group,
    integer,
    write_group,
)

ROUTE = "/preset/reorder-preset"
# Native PresetCount/GetBasePresetId map Guild War (18) to Raid (7),
# including its slot count. Tetis has a separate 15-slot character-list roster.
SLOT_COUNTS = {4: 5, 7: RAID_PRESET_COUNT, 17: TETIS_PRESET_COUNT, 18: RAID_PRESET_COUNT}


def reorder(account, body, operation_id):
    if isinstance(body, dict) and type(body.get("PresetType")) is int and body["PresetType"] == 9:
        from .multi_presets import reorder as reorder_multi

        return reorder_multi(account, body, operation_id)
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
        raise ValueError("Reorder existing slots for the selected preset type")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_reorder_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    character_list = body["PresetType"] == 17
    response_field = "UserCharacterListPreset" if character_list else "UserPartyPreset2"
    group = current_group(account.db, character_list)
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset reorder request identity was reused with different data")
        # A delayed retry never changes later ordering, deletes or recreated slots.
        return {response_field: group}
    base = 700 if body["PresetType"] == 18 else body["PresetType"] * 100
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
            write_group(account.db, group, character_list)
        account.db.execute(
            "INSERT INTO preset_reorder_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {response_field: group}
