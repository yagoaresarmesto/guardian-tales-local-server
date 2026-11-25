# SPDX-License-Identifier: Apache-2.0
"""Add individual, standard player equipment from the installed client catalog."""

import json
from datetime import datetime, timezone

from guardian_tales.admin_test_items import save_profile
from guardian_tales.challenges import allocate_reward_item
from guardian_tales.snapshots import CLIENT
from guardian_tales.test_item_static import item_definitions
from guardian_tales.village import MAX_REVISION, integer

from .equipment_options import generate
from .equipment_ribbons import available_in_client
from .game_save import GameSaveEditor
from .stack_quantities import HAMMERS
from .weapon_progression import LIMIT_BREAK_TYPES


class EquipmentGrants(GameSaveEditor):
    def __init__(self, database, catalog, body, tables, rules):
        super().__init__(database)
        self.rules = rules
        self.items = {}
        self.hammers = {i for i, s in catalog.specs.items() if s.get("Type") in HAMMERS}
        constants = json.loads(tables["constants"][1]) if "constants" in tables else {}
        self.base_capacity = constants.get("DefaultInventoryLimit")
        version = tuple(map(int, CLIENT["version"].split(".")))
        now = datetime.now(timezone.utc)
        for spec in item_definitions(body):
            ident = spec["Id"]
            grade = spec.get("OriginRarity")
            # Standard drops and book-listed reward gear, in their original rarity.
            if (
                spec.get("Type") != "weapon"
                or spec.get("WeaponType") not in LIMIT_BREAK_TYPES
                or not integer(grade, 4)
                or spec.get("Rarity") != grade
                or spec.get("Limited") is not False
                or spec.get("SortingNumber") == -1
                or not (spec.get("Summonable") is True or integer(spec.get("SortingNumber")))
                or not available_in_client(spec, version, now)
                or spec != catalog.specs.get(ident)
            ):
                continue
            if rules.get(ident) is None and not (
                spec.get("MinOptions") == spec.get("MaxOptions") == 0 and not spec.get("Options")
            ):
                continue
            self.items[ident] = {
                "spec": ident,
                "kind": spec["WeaponType"],
                "stars": grade + 1,
                "name": catalog.names.get(ident)
                or (spec.get("NameWithoutRarity") or spec["Name"]).replace("_", " ").title(),
            }

    def space_available(self, user):
        adjustment = user.get("InvenLimitAdj", 0)
        if not integer(self.base_capacity, minimum=1) or not integer(adjustment):
            return False
        hammer_slots = sum(
            row["ItemId"] in self.hammers and row["Amount"] > 0 for row in user["ItemStackables"]
        )
        return len(user["ItemWeapons"]) + hammer_slots < self.base_capacity + adjustment

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
        return {
            "items": list(self.items.values()),
            "version": f"{user['Id']}:{user['Cas']}",
            "spaceAvailable": self.space_available(user),
            **self.status(),
        }

    def apply_locked(self, db, body):
        if (
            not isinstance(body, dict)
            or body.keys() != {"spec", "version"}
            or not integer(body["spec"], minimum=1)
            or body["spec"] not in self.items
        ):
            raise ValueError("Select standard equipment from the catalog.")
        profile = self.profile(db)
        user = profile["User"]
        if body["version"] != f"{user['Id']}:{user['Cas']}":
            return 409, {"error": "Your inventory changed since you opened the catalog."}
        if not self.space_available(user):
            raise ValueError("An available equipment slot is required.")
        if user["Cas"] == MAX_REVISION:
            raise ValueError("The save revision has reached its limit.")
        ident = body["spec"]
        item = allocate_reward_item(user, ident)
        rules = self.rules.get(ident)
        if rules:
            levels = generate(rules, [], {})
            item["Options"] = [
                {"OptionId": key, "Level": levels[key], "Locked": False, "OptionSource": 0}
                for key in rules["options"]
                if key in levels
            ]
        user["ItemWeapons"].append(item)
        save_profile(db, profile)
        return 200, {"id": item["Id"], "spec": ident}
