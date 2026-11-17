# SPDX-License-Identifier: Apache-2.0
"""Select captured Orbital party presets without applying gear or editing teams."""

import json

from .snapshots import preserved_read

GEAR_FIELDS = ("Weapon1", "Weapon2", "Accessory", "Orb1", "Orb2", "Merch", "Relic")
MAX_REVISION = 0x7FFFFFFFFFFFFFFF


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 0x7FFFFFFF


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS preset_selection_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


def owned_party_preset(db, profile, preset_id):
    captured = preserved_read(db, "/preset/get-presets")
    group = captured.get("UserPartyPreset2") if isinstance(captured, dict) else None
    presets = group.get("Presets") if isinstance(group, dict) else None
    if not isinstance(presets, list):
        raise ValueError("Captured party presets are required")
    matches = [p for p in presets if isinstance(p, dict) and p.get("Id") == preset_id]
    if len(matches) != 1 or not integer(matches[0]["Id"], 1):
        raise ValueError("Saved party preset is missing or ambiguous")
    characters = matches[0].get("Characters")
    if not isinstance(characters, list) or not 1 <= len(characters) <= 4:
        raise ValueError("Saved party preset requires one to four owned characters")
    user = profile["User"]
    owned = {row["Id"] for row in user["Characters"]}
    equipment = {row["Id"] for kind in ("ItemWeapons", "ItemMiscs") for row in user[kind]}
    selected = set()
    for character in characters:
        if (
            not isinstance(character, dict)
            or not integer(character.get("Id"), 1)
            or character["Id"] not in owned
            or character["Id"] in selected
        ):
            raise ValueError("Saved preset references an invalid or repeated owned character")
        selected.add(character["Id"])
        for field in GEAR_FIELDS:
            item = character.get(field)
            if item is not None and (not integer(item) or item and item not in equipment):
                raise ValueError("Saved preset references unowned equipment")
    return matches[0]


def set_selected(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PresetId"}
        or not integer(body["PresetId"])
        or not 400 <= body["PresetId"] < 500
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select an existing Orbital preset after completing the prologue")
    encoded = json.dumps(body, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_selection_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    profile = account.profile()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset selection request identity was reused with different data")
        # A delayed retry must not undo a later choice or restore an old profile.
        return {"User": profile["User"]}
    owned_party_preset(account.db, profile, body["PresetId"])
    user = profile["User"]
    selected, revision = user.get("SelectedPresetId"), user.get("Cas")
    if (
        not isinstance(selected, dict)
        or not integer(selected.get("InfiniteTower"))
        or selected["InfiniteTower"] != 0
        and not 400 <= selected["InfiniteTower"] < 500
        or type(revision) is not int
        or not 0 <= revision <= MAX_REVISION
    ):
        raise ValueError("Invalid saved Orbital selection or account revision")
    changed = selected["InfiniteTower"] != body["PresetId"]
    if changed:
        if revision == MAX_REVISION:
            raise ValueError("Account revision exceeds the supported range")
        selected["InfiniteTower"] = body["PresetId"]
        user["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO preset_selection_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {"User": user}
