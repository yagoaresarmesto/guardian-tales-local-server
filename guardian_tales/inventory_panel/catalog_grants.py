# SPDX-License-Identifier: Apache-2.0
"""Add one selected catalog copy under the same offline lock as other save edits."""

from guardian_tales.admin_test_items import save_profile
from guardian_tales.challenges import allocate_reward_item
from guardian_tales.village import MAX_REVISION, integer

from .game_save import GameSaveEditor


class CatalogGrants(GameSaveEditor):
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
            raise ValueError("Select a standard item from this catalog.")
        profile = self.profile(db)
        user = profile["User"]
        if body["version"] != f"{user['Id']}:{user['Cas']}":
            return 409, {"error": "Your inventory changed since you opened the catalog."}
        if not self.space_available(user):
            raise ValueError("An available inventory slot is required.")
        if user["Cas"] == MAX_REVISION:
            raise ValueError("The save revision has reached its limit.")
        item = allocate_reward_item(user, body["spec"])
        self.initialize_copy(item)
        user[self.inventory].append(item)
        save_profile(db, profile)
        return 200, {"id": item["Id"], "spec": item["ItemId"]}
