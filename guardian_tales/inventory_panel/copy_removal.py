# SPDX-License-Identifier: Apache-2.0
"""Delete the selected owned copy using the game's protected removal rules."""

from guardian_tales.item_sell import remove_owned_items
from guardian_tales.village import integer

from .game_save import GameSaveEditor


class CopyRemoval(GameSaveEditor):
    def __init__(self, database, inventory, specs=None):
        super().__init__(database)
        self.inventory = inventory
        self.specs = specs

    def apply_locked(self, db, body):
        if (
            not isinstance(body, dict)
            or body.keys() != {"id", "spec", "version"}
            or not integer(body["id"], minimum=1)
            or not integer(body["spec"], minimum=1)
            or (self.specs is not None and body["spec"] not in self.specs)
            or not isinstance(body["version"], str)
        ):
            raise ValueError("Select an owned copy from this inventory.")
        profile = self.profile(db)
        user = profile["User"]
        if body["version"] != self.inventory_version(user):
            return 409, {"error": "Your inventory changed. Review the copy before deleting it."}
        item = next((row for row in user[self.inventory] if row["Id"] == body["id"]), None)
        if item is None or item["ItemId"] != body["spec"] or not integer(item.get("Amount"), 1, 1):
            raise ValueError("Select a single owned copy from this inventory.")
        remove_owned_items(db, profile, {item["Id"]: 1})
        return 200, {"id": item["Id"], "revision": user["Cas"]}
