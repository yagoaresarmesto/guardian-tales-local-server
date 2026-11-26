# SPDX-License-Identifier: Apache-2.0
"""Temporary inventory preview, backed by a separate in-memory save."""

import uuid
from threading import Lock

from guardian_tales.accounts.account import AccountStore
from guardian_tales.inventory.item_lock import INVENTORIES, LOCK, UNLOCK
from guardian_tales.inventory.item_sell import gear_references

GROUPS = dict(zip(INVENTORIES, ("Equipment", "Miscellaneous", "Stackables")))


class Sandbox:
    def __init__(self, db, references, catalog):
        self.db = db
        self.refs = references
        self.guard = Lock()
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("The save copy failed its integrity check.")
        if db.execute("SELECT schema_version FROM local_account WHERE id=1").fetchone() != (3,):
            raise ValueError("This preview requires a local schema-3 save.")
        self.account = AccountStore(db, references.directory)
        self.equipment = catalog.equipment
        self.specs = catalog.specs
        self.names = catalog.names
        self.has_icons = catalog.has_icons
        user = self.account.profile()["User"]
        self.original = {r["Id"]: r["Locked"] for k in INVENTORIES for r in user[k]}

    def rows(self):
        user = self.account.profile()["User"]
        equipped = gear_references(user["Characters"])
        training = {slot.get("ItemId") for slot in user.get("TrainingSlots", {}).values()}
        rows = []
        for group in INVENTORIES:
            for r in user[group]:
                ident, item = r["Id"], r["ItemId"]
                spec = self.specs.get(item, {})
                key = spec.get("Name", "")
                name = self.names.get(item) or (
                    spec.get("NameWithoutRarity") or key or f"Item {item}"
                ).replace("_", " ")
                rows.append(
                    dict(
                        id=ident,
                        spec=item,
                        name=name,
                        key=key,
                        group=GROUPS[group],
                        kind=spec.get("WeaponType") or spec.get("Type") or "",
                        amount=r["Amount"],
                        locked=r["Locked"],
                        original=self.original[ident],
                        equipped=ident in equipped,
                        breaks=r.get("LimitBreaks") or 0,
                        **(
                            self.equipment.facts(r, spec, training)
                            if group == "ItemWeapons"
                            else {}
                        ),
                    )
                )
        return rows, user["Cas"]

    def listing(self):
        with self.guard:
            rows, rev = self.rows()
            return dict(rows=rows, revision=rev, hasIcons=self.has_icons, equipmentView=True)

    def change(self, body):
        if (
            not isinstance(body, dict)
            or set(body) != {"id", "locked", "revision"}
            or type(body["id"]) is not int
            or body["id"] not in self.original
            or type(body["locked"]) is not bool
            or type(body["revision"]) is not int
        ):
            raise ValueError("Select a valid item copy.")
        with self.guard:
            if self.account.profile()["User"]["Cas"] != body["revision"]:
                return 409, {"error": "The copy changed in another tab. Reload before saving."}
            user = self.account.change_item_locks(
                {"itemIndexes": [body["id"]]},
                "inventory-preview:" + uuid.uuid4().hex,
                LOCK if body["locked"] else UNLOCK,
            )["User"]
            return 200, {"revision": user["Cas"]}
