# SPDX-License-Identifier: Apache-2.0
"""Recruit a missing roster hero in its native starting form."""

from datetime import datetime, timezone

from guardian_tales.account import AccountStore
from guardian_tales.admin_test_items import save_profile
from guardian_tales.characters import new_character
from guardian_tales.snapshots import CLIENT
from guardian_tales.summon_draw import CATEGORIES
from guardian_tales.village import INT_MAX, MAX_REVISION, integer

from .equipment_ribbons import available_in_client
from .game_save import GameSaveEditor

# The two Knights and the two martial artists each share one story choice.
STORY_ALTERNATIVES = (frozenset({1, 2}), frozenset({52, 53}))


class HeroGrants(GameSaveEditor):
    def __init__(self, editor):
        super().__init__(editor.database)
        self.editor = editor

    def missing_origins(self, user):
        specs = self.editor.specs
        origins = set()
        copy_ids = set()
        roster = user.get("Characters")
        if not isinstance(roster, list):
            raise ValueError("Cannot verify the saved hero roster.")
        for hero in roster:
            if not isinstance(hero, dict) or not integer(hero.get("CharacterId"), minimum=1):
                raise ValueError("Cannot identify a hero in the saved roster.")
            ident = hero.get("Id")
            if not integer(ident, minimum=1) or ident in copy_ids:
                raise ValueError("The saved roster contains an invalid or repeated hero ID.")
            copy_ids.add(ident)
            origin = specs.get(hero["CharacterId"], {}).get("OriginId")
            if not integer(origin, minimum=1) or specs.get(origin, {}).get("OriginId") != origin:
                raise ValueError("Cannot identify the original form of every owned hero.")
            if origin in origins:
                raise ValueError("The saved roster already contains two copies of the same hero.")
            origins.add(origin)
        counter = user.get("CharacterIdCounter")
        if not integer(counter) or counter < max(copy_ids, default=0):
            raise ValueError("Invalid saved character counter.")

        for alternatives in STORY_ALTERNATIVES:
            if origins.intersection(alternatives):
                origins.update(alternatives)

        version = tuple(map(int, CLIENT["version"].split(".")))
        now = datetime.now(timezone.utc)
        return [
            spec["Id"]
            for spec in specs.values()
            if spec.get("Playable") is True
            and spec.get("SummonCategory") in CATEGORIES
            and integer(spec.get("Rank"), 4)
            and spec["Id"] == spec.get("OriginId")
            and spec["Id"] not in origins
            and available_in_client(spec, version, now)
        ]

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
            missing = self.missing_origins(user)
            return {
                "heroes": [
                    self.editor.summary(new_character(origin, origin)) for origin in missing
                ],
                "version": self.inventory_version(user),
                **self.status(),
            }

    def apply_locked(self, db, body):
        if (
            not isinstance(body, dict)
            or set(body) != {"spec", "version"}
            or not integer(body["spec"], minimum=1)
        ):
            raise ValueError("Select a missing hero.")
        profile = self.profile(db)
        user = profile["User"]
        if body["version"] != self.inventory_version(user):
            return 409, {"error": "The roster has changed."}
        if body["spec"] not in self.missing_origins(user):
            raise ValueError("Only a missing hero in its starting form can be added.")
        if AccountStore(db, self.editor.catalog.refs.directory, initialize=False).needs_prologue():
            raise ValueError("Complete the prologue before adding a hero.")
        if user["CharacterIdCounter"] == INT_MAX or user["Cas"] == MAX_REVISION:
            raise ValueError("The save has reached its hero ID or revision limit.")
        ident = user["CharacterIdCounter"] + 1
        user["Characters"].append(new_character(ident, body["spec"]))
        user["CharacterIdCounter"] = ident
        save_profile(db, profile)
        return 200, {"id": ident, "spec": body["spec"]}
