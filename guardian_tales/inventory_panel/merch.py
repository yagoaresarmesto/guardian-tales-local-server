# SPDX-License-Identifier: Apache-2.0
"""Browse, grant and upgrade player merch using its released forge progression."""

import json
from bisect import bisect_right
from datetime import datetime, timezone

from guardian_tales.admin_test_items import save_profile
from guardian_tales.jewel_upgrade import owned_inventory, target_row
from guardian_tales.merch_enhance import level_thresholds
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import MAX_REVISION, integer

from .catalog_grants import CatalogGrants
from .equipment_ribbons import available_in_client
from .game_save import GameSaveEditor


def merch_name(catalog, spec):
    key = spec.get("NameWithoutRarity") or spec["Name"]
    return (
        catalog.names.get(spec["Id"]) or key.removeprefix("merch_").replace("_", " ").title()
    ).strip()


class MerchGrants(CatalogGrants):
    inventory = "ItemMiscs"

    def __init__(self, database, catalog, data):
        super().__init__(database)
        self.items = {}
        self.maximum = {}
        self.progress = {}
        self.capacity = data.get("Constants", {}).get("MaxMerchInventory")
        self.merch = {i for i, s in catalog.specs.items() if s.get("Type") == "merch"}
        self.enhancers = {i for i, s in catalog.specs.items() if s.get("Type") == "merchenhance"}
        roots = {
            ident
            for recipe in data.get("MerchRecipes", [])
            for group in recipe["CraftProbabilities"]
            if group["Probability"] > 0
            for ident in group["MerchIds"]
        }
        evolves = data.get("MerchEvolves", [])
        version = tuple(map(int, CLIENT["version"].split(".")))
        now = datetime.now(timezone.utc)
        for ident in roots & self.merch:
            root = catalog.specs[ident]
            origin = root.get("OriginRarity")
            if not root.get("Craftable") or not integer(origin, 2) or not data.get("MerchLevels"):
                continue
            family = []
            spec, progress = root, 0
            for rarity in range(origin, len(evolves)):
                if (
                    not spec
                    or spec.get("Type") != "merch"
                    or spec.get("Rarity") != rarity
                    or spec.get("GroupId") != root["GroupId"]
                    or spec.get("OriginRarity") != origin
                    or spec.get("SortingNumber") == -1
                    or not available_in_client(spec, version, now)
                ):
                    break
                family.append(spec["Id"])
                self.progress[spec["Id"]] = progress
                self.items[spec["Id"]] = dict(
                    spec=spec["Id"],
                    name=merch_name(catalog, spec),
                    kind=str(origin + 1),
                    stars=rarity + 1,
                )
                cost = evolves[rarity]["ProgressNeeded"][origin]
                if not spec.get("EvolveTo") or not integer(cost, minimum=1):
                    break
                progress += cost
                spec = catalog.specs.get(spec["EvolveTo"])
            for member in family:
                self.maximum[member] = family[-1]

    def space_available(self, user):
        copies = sum(row["ItemId"] in self.merch for row in user[self.inventory])
        stacks = sum(
            row["ItemId"] in self.enhancers and row["Amount"] > 0 for row in user["ItemStackables"]
        )
        return integer(self.capacity, minimum=1) and copies + stacks < self.capacity

    def initialize_copy(self, item):
        item["EvolveProgress"] = self.progress[item["ItemId"]]


class MerchInventory(GameSaveEditor):
    def __init__(self, database, catalog, tables):
        super().__init__(database)
        self.catalog = catalog
        data = json.loads(tables["merch"][1]) if "merch" in tables else {}
        self.grants = MerchGrants(database, catalog, data)
        levels = data.get("MerchLevels")
        self.thresholds = level_thresholds(levels) if levels else None

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
        training = {slot.get("ItemId") for slot in user.get("TrainingSlots", {}).values()}
        holders = {
            hero["Merch"]: hero.get("CharacterId")
            for hero in user["Characters"]
            if hero.get("Merch")
        }
        copies = []
        for item in user["ItemMiscs"]:
            ident = item["Id"]
            spec = self.catalog.specs.get(item["ItemId"])
            if not spec or spec.get("Type") != "merch":
                continue
            level = None
            if self.thresholds:
                level = bisect_right(
                    self.thresholds[spec["OriginRarity"]], item.get("Experience", 0)
                )
            copies.append(
                dict(
                    id=ident,
                    spec=spec["Id"],
                    name=merch_name(self.catalog, spec),
                    kind=str(spec["OriginRarity"] + 1),
                    stars=spec["Rarity"] + 1,
                    level=level,
                    locked=bool(item.get("Locked")),
                    equipped=ident in holders,
                    training=ident in training,
                    hero=self.catalog.equipment.hero_names.get(holders.get(ident)),
                )
            )
        limits = {
            ident: dict(stars=self.grants.items[last]["stars"], level=len(self.thresholds[0]))
            for ident, last in self.grants.maximum.items()
        }
        return dict(
            copies=copies, limits=limits, version=self.inventory_version(user), **self.status()
        )

    def apply_locked(self, db, body):
        if (
            not isinstance(body, dict)
            or body.keys() != {"id", "spec", "version"}
            or not integer(body["id"], minimum=1)
            or not integer(body["spec"], minimum=1)
            or body["spec"] not in self.grants.maximum
        ):
            raise ValueError("Select an owned, upgradable merch copy.")
        profile = self.profile(db)
        user = profile["User"]
        if self.inventory_version(user) != body["version"]:
            return 409, {"error": "Your inventory changed. Review the selected merch again."}
        item = target_row(user, owned_inventory(user), body["id"], "ItemMiscs")
        if (
            item["ItemId"] != body["spec"]
            or item["Amount"] != 1
            or not integer(item.get("Experience"))
        ):
            raise ValueError("This copy does not match the selected merch.")
        target = self.grants.maximum[item["ItemId"]]
        cap = self.thresholds[self.catalog.specs[target]["OriginRarity"]][-1]
        if item["ItemId"] != target or item["Experience"] < cap:
            if user["Cas"] == MAX_REVISION:
                raise ValueError("The save revision has reached its limit.")
            if item["ItemId"] != target:
                item.update(ItemId=target, EvolveProgress=self.grants.progress[target])
            item["Experience"] = max(cap, item["Experience"])
            save_profile(db, profile)
        return 200, dict(id=item["Id"], spec=target)
