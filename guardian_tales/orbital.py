# SPDX-License-Identifier: Apache-2.0
"""Guarded Orbital Lift combat-entry trial; results and rewards remain unsupported."""

from .presets import integer, owned_party_preset
from .snapshots import CLIENT

ORBITAL_ENTRY_ROUTE = "/tower-infinity/start-stage"


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
    owned_party_preset(store.db, profile, body["presetId"])
    # The native success callback uses its existing floor spec and selected
    # preset, ignoring the response body. This trial authorizes loading only:
    # no selected-party migration, payment, attempt record, clear or reward.
    return {}
