# SPDX-License-Identifier: Apache-2.0
"""Panel actions on selected equipment, relic or merch copies."""

import json

from guardian_tales.item_lock import set_item_protection
from guardian_tales.item_sell import EQUIPMENT_FIELDS, gear_slots, remove_owned_items
from guardian_tales.jewel_upgrade import owned_inventory, return_one_jewel
from guardian_tales.snapshots import PRESET_OVERLAYS, preserved_read
from guardian_tales.village import MAX_REVISION, integer

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


def detach_selected(value, ids):
    slots = [(mapping, key) for mapping, key in gear_slots(value) if mapping[key] in ids]
    for mapping, key in slots:
        if key in EQUIPMENT_FIELDS:
            mapping[key] = None
        else:
            # Costume maps identify equipped costumes by slot.
            del mapping[key]
    return bool(slots)


def detach_presets(db, ids):
    presets = preserved_read(db, "/preset/get-presets") or {}
    for table, name in PRESET_OVERLAYS:
        group = presets.get(name)
        if not detach_selected(group, ids):
            continue
        if name != "CoopExpeditionSlots":
            if not integer(group.get("Cas"), MAX_REVISION - 1):
                raise ValueError("Invalid saved preset revision")
            group["Cas"] += 1
        # A freshly imported save may only have the captured resource.
        db.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
        )
        db.execute(
            f"INSERT INTO {table}(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
            (json.dumps(group, separators=(",", ":")),),
        )


class ForcedCopyRemoval(CopyRemoval):
    def __init__(self, database, inventory, specs=None, jewel_specs=()):
        super().__init__(database, inventory, specs)
        self.jewel_specs = jewel_specs

    def change(self, db, profile, ids):
        user = profile["User"]
        selected = set(ids)
        for row in user[self.inventory]:
            if row["Id"] not in selected:
                continue
            if type(row.get("Locked")) is not bool:
                raise ValueError("Invalid saved item protection")
            row["Locked"] = False
            sockets = row.get("JewelSlots")
            if sockets is None:
                continue
            if not isinstance(sockets, list):
                raise ValueError("Invalid saved jewel sockets")
            for jewel in sockets:
                if jewel is None:
                    continue
                if not integer(jewel) or (jewel and jewel not in self.jewel_specs):
                    raise ValueError(f"Unknown jewel on copy #{row['Id']}")
                if jewel:
                    return_one_jewel(user, owned_inventory(user), jewel)
            row["JewelSlots"] = []
        detach_presets(db, selected)
        detach_selected(user["Characters"], selected)
        training = user.get("TrainingSlots")
        if not isinstance(training, dict) or not all(
            isinstance(s, dict) for s in training.values()
        ):
            raise ValueError("Invalid saved Training Room slots")
        for slot in training.values():
            if integer(slot.get("ItemId")) and slot["ItemId"] in selected:
                slot["ItemId"] = 0
        return super().change(db, profile, ids)


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
