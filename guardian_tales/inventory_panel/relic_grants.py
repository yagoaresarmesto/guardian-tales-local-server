# SPDX-License-Identifier: Apache-2.0
"""Build standard relic copies with their native per-star option slots."""

import json
from datetime import datetime, timezone

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.inventory.relic_options import roll_slot, valid_pools
from guardian_tales.settlement.village import integer

from .catalog_grants import CatalogGrants
from .equipment_ribbons import available_in_client
from .relics import FAMILIES


class RelicGrants(CatalogGrants):
    inventory = "ItemMiscs"

    def __init__(self, database, catalog, specs, tables):
        super().__init__(database)
        constants = json.loads(tables["constants"][1]) if "constants" in tables else {}
        self.capacity = constants.get("DefaultRelicInventoryLimit")
        self.specs = specs
        self.items = {}
        self.pools = {}
        version = tuple(map(int, CLIENT["version"].split(".")))
        now = datetime.now(timezone.utc)
        for ident, info in specs.items():
            definition = catalog.specs[ident]
            if (
                definition.get("NameWithoutRarity") not in FAMILIES
                or not integer(definition.get("OriginRarity"), 4)
                or not available_in_client(definition, version, now)
            ):
                continue
            # The client pads the basic slot array with empty trailing pools on lower rarities.
            pools = {
                source: [
                    {
                        str(option["OptionId"]): [option["MinLevel"], option["MaxLevel"]]
                        for option in pool
                        if option["Probability"] > 0
                    }
                    for pool in definition.get(field, [])
                    if pool
                ]
                for source, field in (("1", "BaseOptions"), ("2", "ChangeOptions"))
            }
            if not pools["1"] or not pools["2"] or not valid_pools(pools):
                continue
            self.pools[ident] = pools
            self.items[ident] = dict(
                spec=ident,
                kind=info["family"],
                name=info["name"],
                stars=info["stars"],
                basicSlots=len(pools["1"]),
                bonusSlots=len(pools["2"]),
            )

    def space_available(self, user):
        return (
            integer(self.capacity, minimum=1)
            and sum(item["ItemId"] in self.specs for item in user[self.inventory]) < self.capacity
        )

    def initialize_copy(self, item):
        item["RelicOptions"] = [
            dict(roll_slot(pool), OptionSource=int(source), Locked=False)
            for source, slots in self.pools[item["ItemId"]].items()
            for pool in slots
        ]
