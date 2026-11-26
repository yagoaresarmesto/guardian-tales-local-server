# SPDX-License-Identifier: Apache-2.0
"""Choose the next Orbital Lift floor in the existing local save."""

import json

from guardian_tales.modes.orbital.orbital import LAST_SELECTABLE_FLOOR, load_entry_floors
from guardian_tales.settlement.village import INT_MAX, MAX_REVISION, integer

from ...inventory_panel.game_save import GameSaveEditor


class OrbitalChanged(ValueError):
    pass


class OrbitalEditor(GameSaveEditor):
    def __init__(self, database, references):
        super().__init__(database)
        self.references = references

    @staticmethod
    def saved_progress(profile):
        progress = profile.get("UserProgress")
        if not isinstance(progress, dict) or not isinstance(progress.get("TowerInfinity"), dict):
            raise ValueError("The save has no valid Orbital Lift progress.")
        floor = progress["TowerInfinity"].get("Floor")
        revision = progress.get("Cas")
        if not integer(floor, INT_MAX, -INT_MAX) or not integer(revision, MAX_REVISION):
            raise ValueError("The save has invalid Orbital Lift progress.")
        return abs(floor), f"{profile['User']['Id']}:{revision}:{floor}"

    def state(self):
        catalog = load_entry_floors(self.references)
        with self.reader() as db:
            cleared, version = self.saved_progress(self.profile(db))
        return {
            "clearedFloor": cleared,
            "nextFloor": cleared + 1 if cleared + 1 in catalog else None,
            "floors": sorted(f for f in catalog if f <= LAST_SELECTABLE_FLOOR),
            "version": version,
            **self.status(),
        }

    def apply_locked(self, db, body):
        if (
            not isinstance(body, dict)
            or set(body) != {"nextFloor", "version"}
            or not isinstance(body["version"], str)
        ):
            raise ValueError("Choose the next floor from the current Orbital Lift editor.")
        target = body["nextFloor"]
        if not integer(target, LAST_SELECTABLE_FLOOR, 1) or target not in load_entry_floors(
            self.references
        ):
            raise ValueError("Choose a configured floor from 1 to 1500.")
        profile = self.profile(db)
        cleared, version = self.saved_progress(profile)
        if version != body["version"]:
            raise OrbitalChanged("Orbital Lift progress changed. Reload before applying.")
        if target - 1 != cleared:
            progress = profile["UserProgress"]
            if progress["Cas"] == MAX_REVISION:
                raise ValueError("The save has reached its maximum progress revision.")
            progress["TowerInfinity"]["Floor"] = target - 1
            progress["Cas"] += 1
            db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        return 200, {"applied": True}
