# SPDX-License-Identifier: Apache-2.0
"""Panel actions on an individual owned equipment or relic copy."""

from guardian_tales.item_lock import set_item_protection
from guardian_tales.item_sell import remove_owned_items
from guardian_tales.village import integer

from .game_save import GameSaveEditor


class OwnedCopyEditor(GameSaveEditor):
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
            return 409, {"error": "Your inventory changed. Review the selected copy and try again."}
        item = next((row for row in user[self.inventory] if row["Id"] == body["id"]), None)
        if item is None or item["ItemId"] != body["spec"] or not integer(item.get("Amount"), 1, 1):
            raise ValueError("Select a single owned copy from this inventory.")
        return 200, self.change(db, profile, item["Id"])


class CopyRemoval(OwnedCopyEditor):
    @staticmethod
    def change(db, profile, ident):
        remove_owned_items(db, profile, {ident: 1})
        return {"id": ident, "revision": profile["User"]["Cas"]}


class CopyUnlock(OwnedCopyEditor):
    def change(self, db, profile, ident):
        set_item_protection(db, profile, [ident], locked=False)
        user = profile["User"]
        return {
            "id": ident,
            "revision": user["Cas"],
            "inventoryVersion": self.inventory_version(user),
        }
