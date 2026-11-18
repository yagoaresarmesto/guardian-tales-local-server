# SPDX-License-Identifier: Apache-2.0
"""Guarded Orbital entry/exit and opt-in victory progress without rewards."""

import json

from .presets import MAX_REVISION, integer, owned_party_preset
from .snapshots import CLIENT

ORBITAL_ENTRY_ROUTE = "/tower-infinity/start-stage"
ORBITAL_EXIT_ROUTE = "/tower-infinity/end-stage"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS orbital_completion_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, "
        "floor_before INTEGER NOT NULL, floor_after INTEGER NOT NULL)"
    )


def require_no_reward_policy(references):
    path = references.directory / "orbital_completion_catalog.json"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Orbital victories require an explicit no-reward completion policy")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "no_rewards"}
        or value["client"] != CLIENT
        or value["no_rewards"] is not True
    ):
        raise ValueError("Invalid no-reward Orbital completion policy")


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


def profile_for_floor(store, floor):
    floors = load_entry_floors(store.references)
    profile = store.account.profile()
    tower = profile["UserProgress"].get("TowerInfinity")
    if (
        not isinstance(tower, dict)
        or type(tower.get("Floor")) is not int
        or not -0x7FFFFFFF <= tower["Floor"] <= 0x7FFFFFFF
        or floor not in floors
        or floor > abs(tower["Floor"]) + 1
    ):
        raise ValueError("Orbital floor is not configured or is beyond saved progress")
    return profile


def enter(store, body):
    if (
        not isinstance(body, dict)
        or set(body) != {"floor", "presetId"}
        or not integer(body["floor"], 1)
        or not integer(body["presetId"], 1)
        or store.account.needs_prologue()
    ):
        raise ValueError("Orbital entry requires a floor, saved preset and completed prologue")
    profile = profile_for_floor(store, body["floor"])
    owned_party_preset(store.db, profile, body["presetId"])
    # The native success callback uses its existing floor spec and selected
    # preset, ignoring the response body. This trial authorizes loading only:
    # no selected-party migration, payment, attempt record, clear or reward.
    return {}


def end(store, body, operation_id=None):
    if (
        not isinstance(body, dict)
        or set(body) != {"floor", "isCleared", "damages"}
        or not integer(body["floor"], 1)
        or type(body["isCleared"]) is not bool
        or not isinstance(body["damages"], list)
        or len(body["damages"]) > 4
        or any(not integer(damage) for damage in body["damages"])
        or store.account.needs_prologue()
    ):
        raise ValueError(
            "Orbital exits require a floor, Boolean clear flag and bounded party damage"
        )
    if not body["isCleared"]:
        profile_for_floor(store, body["floor"])
        # The native callback skips absent AddedItems/TowerInfinity and can exit.
        # No attempt, damage, floor, reward or revision is saved for non-clear exits.
        return {}
    if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 200:
        raise ValueError("Orbital victory requires a valid request identity")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = store.account.profile()
    previous = store.db.execute(
        "SELECT request FROM orbital_completion_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Orbital completion retry differs from the saved request")
        return {
            "UserProgress": profile["UserProgress"],
            "TowerInfinity": profile["UserProgress"]["TowerInfinity"],
        }
    require_no_reward_policy(store.references)
    profile = profile_for_floor(store, body["floor"])
    progress = profile["UserProgress"]
    if type(progress.get("Cas")) is not int or not 0 <= progress["Cas"] <= MAX_REVISION:
        raise ValueError("Invalid saved progress revision")
    tower = progress["TowerInfinity"]
    before = tower["Floor"]
    advanced = body["floor"] > abs(before)
    if advanced:
        if progress["Cas"] == MAX_REVISION:
            raise ValueError("Progress revision exceeds the supported range")
        # Explicit local policy: the highest reported clear is stored positively.
        # Repeating an older floor retains the saved signed value and revision.
        tower["Floor"] = body["floor"]
        progress["Cas"] += 1
    with store.db:
        if advanced:
            store.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        store.db.execute(
            "INSERT INTO orbital_completion_requests VALUES(?,?,?,?)",
            (operation_id, encoded, before, tower["Floor"]),
        )
    # No inventory, assets, user revision, mission credit or reward notices change.
    return {"UserProgress": progress, "TowerInfinity": tower}
