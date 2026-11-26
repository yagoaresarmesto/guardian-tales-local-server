# SPDX-License-Identifier: Apache-2.0
"""Redeem one owned equipment selection box for its chosen catalog reward."""

import json
from functools import lru_cache

from .admin_test_items import save_profile
from .challenges import allocate_reward_item
from .inventory_panel.equipment_grants import equipment_space_available
from .inventory_panel.equipment_options import roll_new_options, rules_for
from .inventory_panel.stack_quantities import HAMMERS
from .raid_static import decode, records
from .village import MAX_REVISION, integer

ROUTE = "/item/use-selection-box"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS selection_box_requests "
        "(operation_id TEXT PRIMARY KEY, box_id INTEGER NOT NULL, choice INTEGER NOT NULL, "
        "reward TEXT NOT NULL)"
    )


@lru_cache(maxsize=2)
def catalog(body):
    tables = records(decode(body))[1]
    try:
        items = {s["Id"]: s for s in json.loads(tables["items"][1])}
        effects = {s["Id"] for s in json.loads(tables["options"][1])}
        enhance = json.loads(tables["weaponenhance"][1])
        levels = enhance.get("LevelExps.Kong") or enhance["LevelExps"]
        capacity = json.loads(tables["constants"][1])["DefaultInventoryLimit"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Missing equipment selection box data") from exc
    hammers = {i for i, spec in items.items() if spec.get("Type") in HAMMERS}
    return items, effects, levels, capacity, hammers


def open_weapon_box(account, user, box_id, index):
    items, effects, levels, capacity, hammers = catalog(
        account.references.read_bytes("static_data_get.bin")
    )
    stacks = user["ItemStackables"]
    matches = [
        row
        for row in stacks
        if box_id in (row["Id"], row["ItemId"])
        and items.get(row["ItemId"], {}).get("Type") == "selectionbox"
    ]
    if len(matches) != 1 or not integer(matches[0].get("Amount"), minimum=1):
        raise ValueError("Select an owned selection box")
    box = matches[0]
    if box.get("Locked") is not False:
        raise ValueError("Unlock the selection box before opening it")
    choices = items[box["ItemId"]].get("Rewards")
    if not isinstance(choices, list) or index >= len(choices):
        raise ValueError("Unknown selection box choice")
    prize = choices[index]
    if not isinstance(prize, dict) or not integer(prize.get("Amount"), 1, 1):
        raise ValueError("Select a single equipment reward")
    spec = items.get(prize.get("ItemId"))
    level = prize.get("Level", 0)
    if not spec or spec.get("Type") != "weapon" or not integer(level, len(levels)):
        raise ValueError("Select an equipment reward in this box")
    if not equipment_space_available(user, capacity, hammers):
        raise ValueError("An available equipment slot is required")
    rules = rules_for(spec, effects)
    if rules is None and not (
        spec.get("MinOptions") == spec.get("MaxOptions") == 0 and not spec.get("Options")
    ):
        raise ValueError("Invalid equipment reward options")
    xp = levels[level - 1]["TotalExps"] if level else 0
    if not integer(xp):
        raise ValueError("Invalid equipment reward experience")
    weapon = allocate_reward_item(user, spec["Id"])
    weapon.update(Experience=xp, Options=roll_new_options(rules) if rules else None)
    user["ItemWeapons"].append(weapon)
    box["Amount"] -= 1
    if not box["Amount"]:
        stacks.remove(box)
    return weapon


def redeem(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"boxId", "index"}
        or not integer(body["boxId"], minimum=1)
        or not integer(body["index"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid selection box request")
    box_id, index = body["boxId"], body["index"]
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user = profile["User"]
        receipt = db.execute(
            "SELECT box_id,choice,reward FROM selection_box_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if receipt:
            if receipt[:2] != (box_id, index):
                raise ValueError("Selection box retry targets a different box or reward")
            reward = json.loads(receipt[2])
        else:
            if not integer(user.get("Cas"), MAX_REVISION - 1):
                raise ValueError("Invalid saved user revision")
            reward = open_weapon_box(account, user, box_id, index)
            save_profile(db, profile)
            db.execute(
                "INSERT INTO selection_box_requests VALUES(?,?,?,?)",
                (operation_id, box_id, index, json.dumps(reward, separators=(",", ":"))),
            )
    return {"User": user, "AddedItems": [reward], "AddedCharacters": []}
