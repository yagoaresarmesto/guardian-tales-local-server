# SPDX-License-Identifier: Apache-2.0
"""Save Orbital and Raid party presets and manage per-mode team selections."""

import json

from .snapshots import CLIENT, preserved_read

GEAR_FIELDS = ("Weapon1", "Weapon2", "Accessory", "Orb1", "Orb2", "Merch", "Relic")
MAX_REVISION = 0x7FFFFFFFFFFFFFFF
SELECTION_FIELDS = {400: "InfiniteTower", 700: "GuildRaidAndConquest", 1300: "GuildPunchKing"}
# Pinned 3.57.0 EU constants: PresetCountS3[GuildRaidAndConquest - 1].
RAID_PRESET_COUNT = 30


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
    db.execute(
        "CREATE TABLE IF NOT EXISTS preset_delete_requests "
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


def choose_preset(user, preset_id, field, base):
    selected, revision = user.get("SelectedPresetId"), user.get("Cas")
    if (
        not isinstance(selected, dict)
        or not integer(selected.get(field))
        or selected[field] != 0
        and not base <= selected[field] < base + 100
        or type(revision) is not int
        or not 0 <= revision <= MAX_REVISION
    ):
        raise ValueError("Invalid saved party selection or account revision")
    if selected[field] == preset_id:
        return False
    if revision == MAX_REVISION:
        raise ValueError("Account revision exceeds the supported range")
    selected[field] = preset_id
    user["Cas"] += 1
    return True


def choose_orbital(user, preset_id):
    return choose_preset(user, preset_id, "InfiniteTower", 400)


def selection_resource(user):
    # User.Apply preserves absent fields. Include the owner ID for resource
    # routing and the complete mode map, whose native Populate replaces it.
    return {key: user[key] for key in ("Id", "Cas", "SelectedPresetId")}


def set_selected(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PresetId"}
        or not integer(body["PresetId"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select an existing supported party preset after completing the prologue")
    base = body["PresetId"] // 100 * 100
    field = SELECTION_FIELDS.get(base)
    if field is None:
        raise ValueError("Select an existing supported Orbital, Raid/Conquest or Arena preset")
    encoded = json.dumps(body, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_selection_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    profile = account.profile()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset selection request identity was reused with different data")
        # A delayed retry must not undo a later choice or restore an old profile.
        return {"User": selection_resource(profile["User"])}
    owned_party_preset(account.db, profile, body["PresetId"])
    user = profile["User"]
    changed = choose_preset(user, body["PresetId"], field, base)
    with account.db:
        if changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO preset_selection_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {"User": selection_resource(user)}


def orbital_slot_count(references):
    path = references.directory / "orbital_preset_catalog.json"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Creating an Orbital preset requires a matching external catalog")
    catalog = references.json(path.name)
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"client", "count"}
        or catalog["client"] != CLIENT
        or not integer(catalog["count"], 1)
        or catalog["count"] > 100
    ):
        raise ValueError("Invalid Orbital preset catalog")
    return catalog["count"]


def new_definition(references, group, incoming, base):
    count = RAID_PRESET_COUNT if base == 700 else orbital_slot_count(references)
    # The native list builds missing slots from the mode's base ID and uses
    # Order=999 for an unsaved definition. Existing teams keep their order.
    if (
        not base <= incoming["Id"] < base + count
        or type(incoming["Order"]) is not int
        or incoming["Order"] != 999
    ):
        raise ValueError("Create an unused configured party slot with native empty order")
    teams = [
        row
        for row in group["Presets"]
        if isinstance(row, dict) and integer(row.get("Id")) and base <= row["Id"] < base + 100
    ]
    if (
        len(teams) >= count
        or len({row["Id"] for row in teams}) != len(teams)
        or any(
            not base <= row["Id"] < base + count
            or not integer(row.get("Order"))
            or row["Order"] >= 999
            for row in teams
        )
    ):
        raise ValueError("Invalid saved slot count or order for this preset mode")
    order = max((row["Order"] for row in teams), default=-1) + 1
    if order >= 999:
        raise ValueError("No supported order remains for a new party preset")
    return {"Id": incoming["Id"], "Order": order}


def save_party(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PartyPreset", "SetSelected"}
        or type(body["SetSelected"]) is not bool
        or not isinstance(body["PartyPreset"], dict)
        or set(body["PartyPreset"]) != {"Id", "Name", "Order", "Characters"}
        or not integer(body["PartyPreset"]["Id"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Save one party preset with a Boolean SetSelected")
    incoming = body["PartyPreset"]
    base = incoming["Id"] // 100 * 100
    if base not in (400, 700):
        raise ValueError("Saving party definitions is supported for Orbital and Raid/Conquest")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_edit_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    profile = account.profile()
    group = current_group(account.db)
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset edit request identity was reused with different data")
        return {"UserPartyPreset2": group, "User": selection_resource(profile["User"])}
    matches = [
        i
        for i, p in enumerate(group["Presets"])
        if isinstance(p, dict) and p.get("Id") == incoming["Id"]
    ]
    if len(matches) > 1:
        raise ValueError("Saving requires an unambiguous party preset")
    creating = not matches
    index = matches[0] if matches else len(group["Presets"])
    original = (
        new_definition(account.references, group, incoming, base)
        if creating
        else group["Presets"][index]
    )
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
        or not creating
        and incoming["Order"] != original.get("Order")
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
        if creating:
            group["Presets"].append(edited)
        else:
            group["Presets"][index] = edited
        group["Cas"] += 1
    selected_changed = (
        choose_preset(profile["User"], edited["Id"], SELECTION_FIELDS[base], base)
        if body["SetSelected"]
        else False
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
    return {"UserPartyPreset2": group, "User": selection_resource(profile["User"])}


def delete_existing(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PresetId"}
        or not integer(body["PresetId"])
        or not 400 <= body["PresetId"] < 500
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Delete one existing Orbital preset after completing the prologue")
    encoded = json.dumps(body, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_delete_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    profile = account.profile()
    group = current_group(account.db)
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset deletion request identity was reused with different data")
        # A delayed retry returns current state, without deleting another preset
        # or resurrecting definitions from the immutable captured seed.
        return {"UserPartyPreset2": group, "User": selection_resource(profile["User"])}
    matches = [
        i
        for i, preset in enumerate(group["Presets"])
        if isinstance(preset, dict) and preset.get("Id") == body["PresetId"]
    ]
    if len(matches) != 1:
        raise ValueError("Deletion requires one existing unambiguous Orbital preset")
    revision = group.get("Cas")
    if type(revision) is not int or not 0 <= revision < MAX_REVISION:
        raise ValueError("Invalid preset group revision")
    user = profile["User"]
    selected = user.get("SelectedPresetId")
    current = selected.get("InfiniteTower") if isinstance(selected, dict) else None
    # Zero means no saved selection. Choosing a replacement remains an explicit
    # client action; deleting a definition never selects an unrelated team.
    selected_changed = choose_orbital(user, 0 if current == body["PresetId"] else current)
    del group["Presets"][matches[0]]
    group["Cas"] += 1
    with account.db:
        account.db.execute(
            "INSERT INTO party_preset_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
            (json.dumps(group, separators=(",", ":")),),
        )
        if selected_changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO preset_delete_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {"UserPartyPreset2": group, "User": selection_resource(user)}
