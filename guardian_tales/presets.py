# SPDX-License-Identifier: Apache-2.0
"""Save party presets and manage per-mode team selections."""

import json

from .expedition import enabled as expedition_enabled
from .snapshots import CLIENT, preserved_read

GEAR_FIELDS = ("Weapon1", "Weapon2", "Accessory", "Orb1", "Orb2", "Merch", "Relic")
MAX_REVISION = 0x7FFFFFFFFFFFFFFF
SELECTION_FIELDS = {
    400: "InfiniteTower",
    600: "ColosseumAttack",
    700: "GuildRaidAndConquest",
    1300: "GuildPunchKing",
    1700: "RogueChess",
}
# Pinned 3.57.0 EU constants: PresetCountS3[mode - 1].
COLOSSEUM_PRESET_COUNT = 30
RAID_PRESET_COUNT = 30
DKA_PRESET_COUNT = 7
EXPEDITION_PRESET_COUNT = 20
TETIS_PRESET_COUNT = 15
TETIS_ROSTER_SIZE = 8
FIXED_CREATION_COUNTS = {
    600: COLOSSEUM_PRESET_COUNT,
    700: RAID_PRESET_COUNT,
    1300: DKA_PRESET_COUNT,
    1700: TETIS_PRESET_COUNT,
}


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 0x7FFFFFFF


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS character_list_preset_state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
    )
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
    db.execute(
        "CREATE TABLE IF NOT EXISTS preset_reorder_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


def current_group(db, character_list=False):
    if character_list:
        from .tetis_presets import group

        return group(db)
    captured = preserved_read(db, "/preset/get-presets")
    group = captured.get("UserPartyPreset2") if isinstance(captured, dict) else None
    presets = group.get("Presets") if isinstance(group, dict) else None
    if not isinstance(presets, list):
        raise ValueError("Captured party presets are required")
    return group


def validate_members(profile, characters, allow_empty=False, limit=4):
    if not isinstance(characters, list) or not int(not allow_empty) <= len(characters) <= limit:
        raise ValueError("Saved preset has an invalid number of characters")
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


def owned_party_preset(db, profile, preset_id, character_list=False):
    group = current_group(db, character_list)
    matches = [p for p in group["Presets"] if isinstance(p, dict) and p.get("Id") == preset_id]
    if len(matches) != 1 or not integer(matches[0]["Id"], 1):
        raise ValueError("Saved party preset is missing or ambiguous")
    validate_members(
        profile, matches[0].get("Characters"), limit=TETIS_ROSTER_SIZE if character_list else 4
    )
    return matches[0]


def validate_expedition_preset(db, profile, preset_id):
    captured = preserved_read(db, "/preset/get-presets") or {}
    group = captured.get("UserMultiPartyPreset")
    rows = group.get("Presets") if isinstance(group, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Captured Expedition presets are required")
    presets = [row for row in rows if isinstance(row, dict) and row.get("Id") == preset_id]
    parties = presets[0].get("Parties") if len(presets) == 1 else None
    if (
        not isinstance(parties, list)
        or len(parties) != 3
        or not all(isinstance(party, dict) for party in parties)
    ):
        raise ValueError("Select a saved three-party Expedition preset")
    for index, party in enumerate(parties):
        validate_members(profile, party.get("Characters"), allow_empty=index > 0)


def choose_preset(user, preset_id, field, base):
    selected, revision = user.get("SelectedPresetId"), user.get("Cas")
    if not isinstance(selected, dict):
        raise ValueError("Invalid saved party selection")
    current = selected.get(field, 0 if base in (600, 900, 1300, 1700) else None)
    if (
        not integer(current)
        or current != 0
        and not base <= current < base + 100
        or type(revision) is not int
        or not 0 <= revision <= MAX_REVISION
    ):
        raise ValueError("Invalid saved party selection or account revision")
    if current == preset_id:
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
    if (
        base == 900
        and body["PresetId"] < base + EXPEDITION_PRESET_COUNT
        and expedition_enabled(account.references)
    ):
        field = "Expedition"
    if (
        field is None
        or base in (600, 1300, 1700)
        and body["PresetId"] >= base + FIXED_CREATION_COUNTS[base]
    ):
        raise ValueError("Select an existing supported preset within its mode's slots")
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
    if base == 900:
        validate_expedition_preset(account.db, profile, body["PresetId"])
    else:
        owned_party_preset(account.db, profile, body["PresetId"], character_list=base == 1700)
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
    count = orbital_slot_count(references) if base == 400 else FIXED_CREATION_COUNTS[base]
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


def write_group(db, group, character_list=False):
    table = "character_list_preset_state" if character_list else "party_preset_state"
    db.execute(
        f"INSERT INTO {table} VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
        (json.dumps(group, separators=(",", ":")),),
    )


def save_party(account, body, operation_id, character_list=False):
    request_field = "CharacterListPreset" if character_list else "PartyPreset"
    response_field = "UserCharacterListPreset" if character_list else "UserPartyPreset2"
    if (
        not isinstance(body, dict)
        or set(body) != {request_field, "SetSelected"}
        or type(body["SetSelected"]) is not bool
        or not isinstance(body[request_field], dict)
        or set(body[request_field]) != {"Id", "Name", "Order", "Characters"}
        or not integer(body[request_field]["Id"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Save one party preset with a Boolean SetSelected")
    incoming = body[request_field]
    base = incoming["Id"] // 100 * 100
    if (
        base not in ((1700,) if character_list else (400, 600, 700, 1300))
        or base in (600, 1300, 1700)
        and incoming["Id"] >= base + FIXED_CREATION_COUNTS[base]
    ):
        raise ValueError("Use an available preset slot for this mode and preset type")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_edit_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    profile = account.profile()
    group = current_group(account.db, character_list)
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset edit request identity was reused with different data")
        return {response_field: group, "User": selection_resource(profile["User"])}
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
    limit = TETIS_ROSTER_SIZE if character_list else 4
    if not isinstance(characters, list) or len(characters) > limit:
        raise ValueError("Preset exceeds the roster size for this mode")
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
    validate_members(profile, canonical, allow_empty=not body["SetSelected"], limit=limit)
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
            write_group(account.db, group, character_list)
        if selected_changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute("INSERT INTO preset_edit_requests VALUES(?,?)", (operation_id, encoded))
    return {response_field: group, "User": selection_resource(profile["User"])}


def delete_existing(account, body, operation_id, character_list=False):
    response_field = "UserCharacterListPreset" if character_list else "UserPartyPreset2"
    if (
        not isinstance(body, dict)
        or set(body) != {"PresetId"}
        or not integer(body["PresetId"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Delete an existing preset in a supported slot after the prologue")
    base = body["PresetId"] // 100 * 100
    if (
        base not in ((1700,) if character_list else (400, 700, 1300))
        or base in (1300, 1700)
        and body["PresetId"] >= base + FIXED_CREATION_COUNTS[base]
    ):
        raise ValueError("Delete an existing preset in a supported slot after the prologue")
    field = SELECTION_FIELDS[base]
    encoded = json.dumps(body, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM preset_delete_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    profile = account.profile()
    group = current_group(account.db, character_list)
    if previous:
        if previous[0] != encoded:
            raise ValueError("Preset deletion request identity was reused with different data")
        # A delayed retry returns current state, without deleting another preset
        # or resurrecting definitions from the immutable captured seed.
        return {response_field: group, "User": selection_resource(profile["User"])}
    matches = [
        i
        for i, preset in enumerate(group["Presets"])
        if isinstance(preset, dict) and preset.get("Id") == body["PresetId"]
    ]
    if len(matches) != 1:
        raise ValueError("Deletion requires one existing unambiguous preset")
    revision = group.get("Cas")
    if type(revision) is not int or not 0 <= revision < MAX_REVISION:
        raise ValueError("Invalid preset group revision")
    user = profile["User"]
    selected = user.get("SelectedPresetId")
    current = selected.get(field, 0) if isinstance(selected, dict) else None
    # Zero means no saved selection. Choosing a replacement remains an explicit
    # client action; deleting a definition never selects an unrelated team.
    selected_changed = choose_preset(
        user, 0 if current == body["PresetId"] else current, field, base
    )
    del group["Presets"][matches[0]]
    group["Cas"] += 1
    with account.db:
        write_group(account.db, group, character_list)
        if selected_changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO preset_delete_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {response_field: group, "User": selection_resource(user)}
