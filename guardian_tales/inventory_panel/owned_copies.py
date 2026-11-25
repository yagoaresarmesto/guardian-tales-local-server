# SPDX-License-Identifier: Apache-2.0
"""Panel actions on selected equipment or relic copies."""

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
        if not isinstance(body, dict) or not isinstance(body.get("version"), str):
            raise ValueError("Select owned copies from this inventory.")
        if body.keys() == {"id", "spec", "version"}:
            single = True
            copies = [{"id": body["id"], "spec": body["spec"]}]
        elif (
            body.keys() == {"copies", "version"}
            and isinstance(body["copies"], list)
            and body["copies"]
        ):
            single = False
            copies = body["copies"]
        else:
            raise ValueError("Select at least one owned copy.")
        profile = self.profile(db)
        user = profile["User"]
        if body["version"] != self.inventory_version(user):
            return 409, {"error": "Your inventory changed. Review your selection and try again."}
        owned = {item["Id"]: item for item in user[self.inventory]}
        ids = []
        for copy in copies:
            if (
                not isinstance(copy, dict)
                or copy.keys() != {"id", "spec"}
                or not integer(copy["id"], minimum=1)
                or not integer(copy["spec"], minimum=1)
                or (self.specs is not None and copy["spec"] not in self.specs)
            ):
                raise ValueError("Select owned copies from this inventory.")
            item = owned.get(copy["id"])
            if (
                item is None
                or item["ItemId"] != copy["spec"]
                or not integer(item.get("Amount"), 1, 1)
            ):
                raise ValueError(f"Copy #{copy['id']} does not match this inventory.")
            ids.append(copy["id"])
        if len(set(ids)) != len(ids):
            raise ValueError("Each selected copy must appear only once.")
        result = self.change(db, profile, ids)
        result["revision"] = user["Cas"]
        if single:
            result["id"] = ids[0]
        else:
            result["ids"] = ids
            result["inventoryVersion"] = self.inventory_version(user)
        return 200, result


class CopyRemoval(OwnedCopyEditor):
    @staticmethod
    def change(db, profile, ids):
        remove_owned_items(db, profile, dict.fromkeys(ids, 1))
        return {}


class CopyProtection(OwnedCopyEditor):
    def __init__(self, database, inventory, specs=None, *, locked):
        super().__init__(database, inventory, specs)
        self.locked = locked

    def change(self, db, profile, ids):
        set_item_protection(db, profile, ids, locked=self.locked)
        user = profile["User"]
        return {
            "locked": self.locked,
            "inventoryVersion": self.inventory_version(user),
        }
