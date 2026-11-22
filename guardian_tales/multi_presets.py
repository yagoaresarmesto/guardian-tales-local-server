# SPDX-License-Identifier: Apache-2.0
"""Persistent Expedition presets with three parties and route-bound retry receipts."""

import json

from .expedition import enabled
from .presets import (
    EXPEDITION_PRESET_COUNT,
    GEAR_FIELDS,
    MAX_REVISION,
    choose_preset,
    integer,
    selection_resource,
    validate_members,
)
from .snapshots import preserved_read

SAVE = "/preset/set-multi-party-preset"
DELETE = "/preset/delete-multi-party-preset"
REORDER = "/preset/reorder-preset"
ROUTES = (SAVE, DELETE)
BASE = 900


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS multi_party_preset_state "
        "(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS multi_preset_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL)"
    )


def current_group(db):
    captured = preserved_read(db, "/preset/get-presets") or {}
    group = captured.get("UserMultiPartyPreset")
    if (
        not isinstance(group, dict)
        or not isinstance(group.get("Presets"), list)
        or len(group["Presets"]) > 1000
        or any(not isinstance(row, dict) or not integer(row.get("Id")) for row in group["Presets"])
    ):
        raise ValueError("Captured multi-party presets are required")
    return group


def expedition_id(value):
    return integer(value) and BASE <= value < BASE + EXPEDITION_PRESET_COUNT


def valid_name(value, nullable=False):
    if value is None:
        return nullable
    try:
        return (
            isinstance(value, str)
            and len(value.encode("utf-16le")) <= 128
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        )
    except UnicodeError:
        return False


def begin(account, route, body, operation_id):
    if (
        not enabled(account.references)
        or account.needs_prologue()
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
    ):
        raise ValueError("Expedition preset changes require activation and a completed account")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    group = current_group(account.db)
    profile = account.profile()
    previous = account.db.execute(
        "SELECT route,request FROM multi_preset_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous and previous != (route, encoded):
        raise ValueError("Multi-party preset identity was reused for another operation")
    return group, profile, encoded, bool(previous)


def response(group, user):
    return {"UserMultiPartyPreset": group, "User": selection_resource(user)}


def persist(account, group, profile, route, encoded, operation_id, group_changed, user_changed):
    revision = group.get("Cas")
    if (
        type(revision) is not int
        or not 0 <= revision <= MAX_REVISION
        or group_changed
        and revision == MAX_REVISION
    ):
        raise ValueError("Invalid multi-party preset group revision")
    if group_changed:
        group["Cas"] += 1
    with account.db:
        if group_changed:
            account.db.execute(
                "INSERT INTO multi_party_preset_state VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(group, separators=(",", ":")),),
            )
        if user_changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO multi_preset_requests VALUES(?,?,?)", (operation_id, route, encoded)
        )


def delete(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PresetId"}
        or not expedition_id(body["PresetId"])
    ):
        raise ValueError("Delete one Expedition multi-party preset in slots 900..919")
    group, profile, encoded, replay = begin(account, DELETE, body, operation_id)
    if replay:
        return response(group, profile["User"])
    matches = [i for i, row in enumerate(group["Presets"]) if row["Id"] == body["PresetId"]]
    if len(matches) != 1:
        raise ValueError("Delete one existing unambiguous Expedition preset")
    user = profile["User"]
    selected = user.get("SelectedPresetId")
    current = selected.get("Expedition", 0) if isinstance(selected, dict) else None
    selected_changed = choose_preset(
        user, 0 if current == body["PresetId"] else current, "Expedition", BASE
    )
    del group["Presets"][matches[0]]
    persist(account, group, profile, DELETE, encoded, operation_id, True, selected_changed)
    return response(group, user)


def canonical_parties(profile, incoming, original, selected):
    if (
        not isinstance(incoming, list)
        or len(incoming) != 3
        or any(
            not isinstance(row, dict) or set(row) != {"Id", "Name", "Order", "Characters"}
            for row in incoming
        )
        or [row["Id"] for row in incoming] != [1, 2, 3]
        or any(type(row["Id"]) is not int for row in incoming)
    ):
        raise ValueError("Save three ordered Expedition parties with IDs 1, 2 and 3")
    old = original.get("Parties") if original else None
    if old is not None and (
        not isinstance(old, list) or len(old) != 3 or any(not isinstance(row, dict) for row in old)
    ):
        raise ValueError("Invalid saved Expedition party slots")
    parties, heroes = [], set()
    for index, party in enumerate(incoming):
        if (
            not valid_name(party["Name"], nullable=True)
            or not integer(party["Order"])
            or party["Order"] != (old[index].get("Order") if old else 0)
            or old
            and old[index].get("Id") != party["Id"]
            or not isinstance(party["Characters"], list)
            or len(party["Characters"]) > 4
        ):
            raise ValueError("Invalid Expedition party name, order or character list")
        characters = []
        for character in party["Characters"]:
            if (
                not isinstance(character, dict)
                or "Id" not in character
                or set(character) - {"Id", *GEAR_FIELDS}
            ):
                raise ValueError("Unsupported Expedition character preset fields")
            characters.append({"Id": character["Id"], **{k: character.get(k) for k in GEAR_FIELDS}})
        validate_members(profile, characters, allow_empty=not selected or index > 0)
        ids = {row["Id"] for row in characters}
        if heroes & ids:
            raise ValueError("An Expedition hero may occupy only one party slot")
        heroes.update(ids)
        parties.append(dict(old[index] if old else {}, **{**party, "Characters": characters}))
    return parties


def teams(group):
    rows = [row for row in group["Presets"] if BASE <= row["Id"] < BASE + 100]
    if (
        len(rows) > EXPEDITION_PRESET_COUNT
        or len({r["Id"] for r in rows}) != len(rows)
        or any(
            not expedition_id(r["Id"]) or not integer(r.get("Order")) or r["Order"] >= 999
            for r in rows
        )
    ):
        raise ValueError("Invalid saved Expedition slot identities or orders")
    return rows


def save(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"MultiPartyPreset", "SetSelected"}
        or type(body["SetSelected"]) is not bool
        or not isinstance(body["MultiPartyPreset"], dict)
        or set(body["MultiPartyPreset"]) != {"Id", "Name", "Order", "Parties"}
    ):
        raise ValueError("Save one MultiPartyPreset with a Boolean SetSelected")
    incoming = body["MultiPartyPreset"]
    if (
        not expedition_id(incoming["Id"])
        or not valid_name(incoming["Name"])
        or not integer(incoming["Order"])
    ):
        raise ValueError("Invalid Expedition preset slot, name or order")
    group, profile, encoded, replay = begin(account, SAVE, body, operation_id)
    if replay:
        return response(group, profile["User"])
    saved = teams(group)
    matches = [i for i, row in enumerate(group["Presets"]) if row["Id"] == incoming["Id"]]
    creating = not matches
    original = None if creating else group["Presets"][matches[0]]
    if (
        creating
        and (len(saved) >= EXPEDITION_PRESET_COUNT or incoming["Order"] != 999)
        or not creating
        and incoming["Order"] != original["Order"]
    ):
        raise ValueError(
            "New presets use native empty order 999; reorder existing presets separately"
        )
    order = max((row["Order"] for row in saved), default=-1) + 1 if creating else original["Order"]
    if order >= 999:
        raise ValueError("No supported order remains for a new Expedition preset")
    parties = canonical_parties(profile, incoming["Parties"], original, body["SetSelected"])
    edited = dict(
        original or {}, Id=incoming["Id"], Name=incoming["Name"], Order=order, Parties=parties
    )
    changed = edited != original
    if changed:
        if creating:
            group["Presets"].append(edited)
        else:
            group["Presets"][matches[0]] = edited
    selected_changed = (
        choose_preset(profile["User"], edited["Id"], "Expedition", BASE)
        if body["SetSelected"]
        else False
    )
    persist(account, group, profile, SAVE, encoded, operation_id, changed, selected_changed)
    return response(group, profile["User"])


def reorder(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"PresetType", "Order"}
        or type(body["PresetType"]) is not int
        or body["PresetType"] != 9
        or not isinstance(body["Order"], list)
        or len(body["Order"]) != EXPEDITION_PRESET_COUNT
        or any(not integer(n) or n >= EXPEDITION_PRESET_COUNT for n in body["Order"])
    ):
        raise ValueError("Reorder the 20 Expedition slots with PresetType 9")
    group, profile, encoded, replay = begin(account, REORDER, body, operation_id)
    if replay:
        return {"UserMultiPartyPreset": group}
    saved = teams(group)
    ids = {row["Id"] for row in saved}
    positions = body["Order"]
    if (
        not saved
        or sorted(positions[ident - BASE] for ident in ids) != list(range(len(saved)))
        or any(value != 0 and BASE + slot not in ids for slot, value in enumerate(positions))
    ):
        raise ValueError(
            "Assign each saved Expedition preset a unique position; unused slots stay zero"
        )
    changed = any(row["Order"] != positions[row["Id"] - BASE] for row in saved)
    for row in saved:
        row["Order"] = positions[row["Id"] - BASE]
    persist(account, group, profile, REORDER, encoded, operation_id, changed, False)
    return {"UserMultiPartyPreset": group}


def handle(account, route, body, operation_id):
    if route == SAVE:
        return save(account, body, operation_id)
    if route == DELETE:
        return delete(account, body, operation_id)
    raise ValueError("Unsupported multi-party preset operation")
