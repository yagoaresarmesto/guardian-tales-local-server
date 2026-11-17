# SPDX-License-Identifier: Apache-2.0
"""Guarded Orbital Lift combat-entry trial; results and rewards remain unsupported."""

from .snapshots import CLIENT, preserved_read

ORBITAL_ENTRY_ROUTE = "/tower-infinity/start-stage"
GEAR_FIELDS = ("Weapon1", "Weapon2", "Accessory", "Orb1", "Orb2", "Merch", "Relic")


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 0x7FFFFFFF


def load_entry_floors(references):
    path = references.directory / "orbital_entry_catalog.json"
    if not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ValueError("Orbital entry requires a matching external floor catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "floors"}
        or value["client"] != CLIENT
        or not isinstance(value["floors"], list)
        or not 1 <= len(value["floors"]) <= 10000
        or any(not integer(floor, 1) for floor in value["floors"])
        or len(value["floors"]) != len(set(value["floors"]))
    ):
        raise ValueError("Invalid Orbital entry floor catalog")
    return set(value["floors"])


def enter(store, body):
    if (
        not isinstance(body, dict)
        or set(body) != {"floor", "presetId"}
        or not integer(body["floor"], 1)
        or not integer(body["presetId"], 1)
        or store.account.needs_prologue()
    ):
        raise ValueError("Orbital entry requires a floor, saved preset and completed prologue")
    floors = load_entry_floors(store.references)
    profile = store.account.profile()
    tower = profile["UserProgress"].get("TowerInfinity")
    if (
        not isinstance(tower, dict)
        or type(tower.get("Floor")) is not int
        or not -0x7FFFFFFF <= tower["Floor"] <= 0x7FFFFFFF
        or body["floor"] not in floors
        or body["floor"] > abs(tower["Floor"]) + 1
    ):
        raise ValueError("Orbital floor is not configured or is beyond saved progress")
    captured = preserved_read(store.db, "/preset/get-presets")
    group = captured.get("UserPartyPreset2") if isinstance(captured, dict) else None
    presets = group.get("Presets") if isinstance(group, dict) else None
    if not isinstance(presets, list):
        raise ValueError("Orbital entry requires captured party presets")
    matches = [p for p in presets if isinstance(p, dict) and p.get("Id") == body["presetId"]]
    if len(matches) != 1 or not integer(matches[0]["Id"], 1):
        raise ValueError("Orbital party preset is missing or ambiguous")
    characters = matches[0].get("Characters")
    if not isinstance(characters, list) or not 1 <= len(characters) <= 4:
        raise ValueError("Orbital preset requires one to four owned characters")
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
            raise ValueError("Orbital preset references an invalid or repeated owned character")
        selected.add(character["Id"])
        for field in GEAR_FIELDS:
            item = character.get(field)
            if item is not None and (not integer(item) or item and item not in equipment):
                raise ValueError("Orbital preset references unowned equipment")
    # The native success callback uses its existing floor spec and selected
    # preset, ignoring the response body. This trial authorizes loading only:
    # no selected-party migration, payment, attempt record, clear or reward.
    return {}
