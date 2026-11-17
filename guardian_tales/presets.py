# SPDX-License-Identifier: Apache-2.0
"""Select and edit existing Orbital presets without changing owned heroes or gear."""

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
    db.execute(
        "CREATE TABLE IF NOT EXISTS party_preset_state "
        "(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS preset_edit_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


def current_group(db):
    captured = preserved_read(db, "/preset/get-presets")
    group = captured.get("UserPartyPreset2") if isinstance(captured, dict) else None
    presets = group.get("Presets") if isinstance(group, dict) else None
    if not isinstance(presets, list):
        raise ValueError("Captured party presets are required")
    return group


def validate_members(profile, characters, allow_empty=False):
    if not isinstance(characters, list) or not int(not allow_empty) <= len(characters) <= 4:
        raise ValueError("Saved party preset requires up to four owned characters")
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


def owned_party_preset(db, profile, preset_id):
    group = current_group(db)
    matches = [p for p in group["Presets"] if isinstance(p, dict) and p.get("Id") == preset_id]
    if len(matches) != 1 or not integer(matches[0]["Id"], 1):
        raise ValueError("Saved party preset is missing or ambiguous")
    validate_members(profile, matches[0].get("Characters"))
    return matches[0]


def choose_orbital(user, preset_id):
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
    if selected["InfiniteTower"] == preset_id:
        return False
    if revision == MAX_REVISION:
        raise ValueError("Account revision exceeds the supported range")
    selected["InfiniteTower"] = preset_id
    user["Cas"] += 1
    return True


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
    changed = choose_orbital(user, body["PresetId"])
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


def save_existing(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PartyPreset", "SetSelected"}
        or type(body["SetSelected"]) is not bool
        or not isinstance(body["PartyPreset"], dict)
        or set(body["PartyPreset"]) != {"Id", "Name", "Order", "Characters"}
        or not integer(body["PartyPreset"]["Id"])
        or not 400 <= body["PartyPreset"]["Id"] < 500
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Save one existing Orbital party preset with a Boolean SetSelected")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_edit_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    profile = account.profile()
    group = current_group(account.db)
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset edit request identity was reused with different data")
        return {"UserPartyPreset2": group, "User": profile["User"]}
    incoming = body["PartyPreset"]
    matches = [
        i
        for i, p in enumerate(group["Presets"])
        if isinstance(p, dict) and p.get("Id") == incoming["Id"]
    ]
    if len(matches) != 1:
        raise ValueError("Editing requires one existing unambiguous Orbital preset")
    index = matches[0]
    original = group["Presets"][index]
    name = incoming["Name"]
    try:
        valid_name = (
            isinstance(name, str)
            and len(name.encode("utf-16le")) // 2 <= 64
            and not any(ord(c) < 32 or ord(c) == 127 for c in name)
        )
    except UnicodeError:
        valid_name = False
    if (
        not valid_name
        or type(incoming["Order"]) is not int
        or type(original.get("Order")) is not int
        or incoming["Order"] != original.get("Order")
    ):
        raise ValueError("Invalid preset name or unsupported preset reordering")
    characters = incoming["Characters"]
    if not isinstance(characters, list) or len(characters) > 4:
        raise ValueError("Preset characters must be a list of up to four members")
    canonical = []
    for character in characters:
        if (
            not isinstance(character, dict)
            or "Id" not in character
            or set(character) - {"Id", *GEAR_FIELDS}
        ):
            raise ValueError("Unsupported character preset fields")
        # Native serialization omits nullable gear slots. An absent slot means
        # unequipped, rather than retaining the previous saved equipment.
        canonical.append(
            {"Id": character["Id"], **{key: character.get(key) for key in GEAR_FIELDS}}
        )
    validate_members(profile, canonical, allow_empty=not body["SetSelected"])
    edited = dict(original, Name=name, Characters=canonical)
    changed = edited != original
    revision = group.get("Cas")
    if (
        type(revision) is not int
        or not 0 <= revision <= MAX_REVISION
        or changed
        and revision == MAX_REVISION
    ):
        raise ValueError("Invalid preset group revision")
    if changed:
        group["Presets"][index] = edited
        group["Cas"] += 1
    selected_changed = (
        choose_orbital(profile["User"], edited["Id"]) if body["SetSelected"] else False
    )
    with account.db:
        if changed:
            account.db.execute(
                "INSERT INTO party_preset_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(group, separators=(",", ":")),),
            )
        if selected_changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute("INSERT INTO preset_edit_requests VALUES(?,?)", (operation_id, encoded))
    return {"UserPartyPreset2": group, "User": profile["User"]}
