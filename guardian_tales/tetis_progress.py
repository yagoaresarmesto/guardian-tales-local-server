# SPDX-License-Identifier: Apache-2.0
"""Single-account offline Tetis progression used by gameplay and the local editor."""

import json

from .tetis_catalog import catalog, load_catalog
from .village import integer

__all__ = [
    "catalog",
    "load_catalog",
    "stored_progress",
    "read_progress",
    "save_progress",
    "editor_view",
    "edit_progress",
    "set_loadout",
    "set_abilities",
]


def stored_progress(db):
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tetis_progress'"
    ).fetchone():
        return None
    row = db.execute("SELECT state FROM tetis_progress WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def read_progress(db, catalog):
    state = stored_progress(db)
    if state is None:
        state = {"floors": {}, "seasonData": {}, "narratives": {}, "presets": {}, "active": None}
    for season in catalog.seasons:
        key = str(season)
        state["floors"].setdefault(key, 0)
        state["seasonData"].setdefault(
            key, {"Exp": 0, "Abilities": [], "Artifacts": {}, "ArtifactId": 0, "SpellId": 0}
        )
    # Early offline sweeps counted duplicates, including after the native maximum.
    shared = state["seasonData"][str(catalog.current)]["Artifacts"]
    for ident in catalog.artifacts:
        key = str(ident)
        if shared.get(key, 0) > catalog.max_artifact_level:
            shared[key] = catalog.max_artifact_level
    return state


def save_progress(db, state):
    # Callers hold the transaction covering their complete read/modify/write operation.
    db.execute(
        "CREATE TABLE IF NOT EXISTS tetis_progress "
        "(id INTEGER PRIMARY KEY CHECK (id=1), state TEXT NOT NULL)"
    )
    db.execute(
        "INSERT INTO tetis_progress (id,state) VALUES(1,?) "
        "ON CONFLICT(id) DO UPDATE SET state=excluded.state",
        (json.dumps(state, separators=(",", ":")),),
    )


def editor_view(db, catalog):
    state = read_progress(db, catalog)
    seasons = []
    for ident, spec in catalog.seasons.items():
        data = state["seasonData"][str(ident)]
        points = catalog.unpacked(data["Abilities"])
        seasons.append(
            {
                "id": ident,
                "title": spec["TitleName"],
                "maxFloor": catalog.max_floor(ident),
                "clearedFloor": state["floors"][str(ident)],
                "level": catalog.level_for(data["Exp"]),
                "experience": data["Exp"],
                "nodes": [
                    catalog.describe_node(i, node, points)
                    for i, node in catalog.nodes[ident].items()
                ],
            }
        )
    return {
        "seasons": seasons,
        "currentSeason": catalog.current,
        "levelStarts": catalog.level_starts,
        "maxExperience": catalog.max_experience,
        "maxPoints": catalog.max_points,
        "levelPerPoint": catalog.level_per_point,
        "loadout": catalog.describe_loadout(state["seasonData"][str(catalog.current)]),
    }


def set_abilities(catalog, data, season, experience, points):
    packed = catalog.validate_abilities(season, experience, points)
    if data["SpellId"] and not catalog.spell_unlocked(
        season, data["SpellId"], catalog.unpacked(packed)
    ):
        data["SpellId"] = 0
    data.update(Exp=experience, Abilities=packed)


def set_loadout(catalog, data, spell=None, artifact=None):
    if spell is not None:
        if not integer(spell) or (
            spell
            and not catalog.spell_unlocked(
                catalog.current, spell, catalog.unpacked(data["Abilities"])
            )
        ):
            raise ValueError("Select an unlocked Guardian Spell from the current Tetis season.")
        data["SpellId"] = spell
    if artifact is not None:
        if not integer(artifact) or (
            artifact
            and (artifact not in catalog.artifacts or not data["Artifacts"].get(str(artifact)))
        ):
            raise ValueError("Acquire a current-season Tetis artifact before equipping it.")
        data["ArtifactId"] = artifact


def edit_loadout(catalog, data, payload):
    levels = payload.get("artifactLevels", {})
    if not isinstance(levels, dict) or len(levels) > len(catalog.artifacts):
        raise ValueError("Choose current-season Tetis artifact levels.")
    known = {str(ident) for ident in catalog.artifacts}
    for key, level in levels.items():
        if key not in known or not integer(level, maximum=catalog.max_artifact_level):
            raise ValueError("Unknown Tetis artifact or level outside its range.")
        if level:
            data["Artifacts"][key] = level
        else:
            data["Artifacts"].pop(key, None)
            if key == str(data["ArtifactId"]):
                data["ArtifactId"] = 0
    if any(key in payload and payload[key] is None for key in ("spellId", "artifactId")):
        raise ValueError("Choose a Tetis loadout ID, or zero to unequip.")
    set_loadout(catalog, data, payload.get("spellId"), payload.get("artifactId"))


def edit_progress(db, catalog, payload):
    fields = {
        "seasonId",
        "clearedFloor",
        "experience",
        "abilities",
        "spellId",
        "artifactId",
        "artifactLevels",
    }
    if not isinstance(payload, dict) or payload.keys() - fields or len(payload) < 2:
        raise ValueError("Choose a Tetis season and at least one progression change.")
    ident = payload.get("seasonId")
    if not integer(ident, minimum=1) or ident not in catalog.seasons:
        raise ValueError("Unknown Tetis season.")
    state = read_progress(db, catalog)
    if state.get("active"):
        raise ValueError("Finish the active Tetis battle before editing progression.")
    key = str(ident)
    if "clearedFloor" in payload:
        floor = payload["clearedFloor"]
        if not integer(floor, maximum=catalog.max_floor(ident)):
            raise ValueError("Cleared floor is outside this Tetis season.")
        state["floors"][key] = floor
    if "experience" in payload or "abilities" in payload:
        if not catalog.nodes[ident]:
            raise ValueError("This Tetis story season has no Guardian Tactic training.")
        data = state["seasonData"][key]
        exp = payload.get("experience", data["Exp"])
        if not integer(exp, maximum=catalog.max_experience):
            raise ValueError("Experience is outside the Tetis level table.")
        abilities = payload.get("abilities", catalog.unpacked(data["Abilities"]))
        set_abilities(catalog, data, ident, exp, abilities)
    edit_loadout(catalog, state["seasonData"][str(catalog.current)], payload)
    save_progress(db, state)
