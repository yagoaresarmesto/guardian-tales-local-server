# SPDX-License-Identifier: Apache-2.0
"""Read owned merch copies and their displayed levels from the working save."""

import json
from bisect import bisect_right

from guardian_tales.merch_enhance import level_thresholds

from .game_save import GameSaveEditor


class MerchInventory(GameSaveEditor):
    def __init__(self, database, catalog, tables):
        super().__init__(database)
        self.catalog = catalog
        levels = json.loads(tables["merch"][1]).get("MerchLevels") if "merch" in tables else None
        self.thresholds = level_thresholds(levels) if levels else None

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
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
            name = self.catalog.names.get(spec["Id"])
            if not name:
                key = spec.get("NameWithoutRarity") or spec["Name"]
                name = key.removeprefix("merch_").replace("_", " ").title()
            level = None
            if self.thresholds:
                level = bisect_right(
                    self.thresholds[spec["OriginRarity"]], item.get("Experience", 0)
                )
            copies.append(
                dict(
                    id=ident,
                    spec=spec["Id"],
                    name=name.strip(),
                    stars=spec["Rarity"] + 1,
                    level=level,
                    locked=bool(item.get("Locked")),
                    equipped=ident in holders,
                    hero=self.catalog.equipment.hero_names.get(holders.get(ident)),
                )
            )
        return {"copies": copies}
