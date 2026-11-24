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
    }


def edit_progress(db, catalog, payload):
    fields = {"seasonId", "clearedFloor", "experience", "abilities"}
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
        packed = catalog.validate_abilities(ident, exp, abilities)
        if packed != data["Abilities"] and data["SpellId"]:
            # Base spells remain selectable independently of training. Unequip a trained
            # spell if its node is removed, as in the client's skill reset.
            removed = set(catalog.unpacked(data["Abilities"])) - set(catalog.unpacked(packed))
            if any(
                catalog.nodes[ident][node]["SummonerSpellId"] == data["SpellId"] for node in removed
            ):
                data["SpellId"] = 0
        data.update(Exp=exp, Abilities=packed)
    save_progress(db, state)
