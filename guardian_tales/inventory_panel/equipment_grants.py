# SPDX-License-Identifier: Apache-2.0
"""Add individual, standard player equipment from the installed client catalog."""

import json
from datetime import datetime, timezone

from guardian_tales.snapshots import CLIENT
from guardian_tales.test_item_static import item_definitions
from guardian_tales.village import integer

from .catalog_grants import CatalogGrants
from .equipment_options import roll_new_options
from .equipment_ribbons import available_in_client, equipment_ribbons
from .stack_quantities import HAMMERS
from .weapon_progression import LIMIT_BREAK_TYPES


def grantable_edition(spec):
    if spec.get("Limited") is True:
        return integer(spec.get("CollaborationId"), minimum=1)
    return spec.get("Limited") is False


def standard_variants(body, catalog):
    native = {s["Id"]: s for s in item_definitions(body)}
    version = tuple(map(int, CLIENT["version"].split(".")))
    now = datetime.now(timezone.utc)
    for origin in native.values():
        grade = origin.get("OriginRarity")
        if (
            origin.get("Type") != "weapon"
            or origin.get("WeaponType") not in LIMIT_BREAK_TYPES
            or not integer(grade, 4)
            or origin.get("Rarity") != grade
            or not (origin.get("Summonable") is True or integer(origin.get("SortingNumber")))
        ):
            continue
        # Only follow explicit EU evolutions of an eligible player item.
        spec = origin
        for rarity in range(grade, 6):
            if (
                not spec
                or spec.get("Type") != "weapon"
                or spec.get("WeaponType") != origin["WeaponType"]
                or spec.get("OriginRarity") != grade
                or spec.get("NameWithoutRarity") != origin.get("NameWithoutRarity")
                or spec.get("Rarity") != rarity
                or not grantable_edition(spec)
                or spec.get("SortingNumber") == -1
                or not available_in_client(spec, version, now)
                or spec != catalog.specs.get(spec["Id"])
            ):
                break
            yield spec
            link = spec.get("EvolveTo") or {}
            spec = native.get(link.get("KakaoGlobal", link.get("Default")))


class EquipmentGrants(CatalogGrants):
    inventory = "ItemWeapons"

    def __init__(self, database, catalog, body, tables, rules):
        super().__init__(database)
        self.rules = rules
        self.items = {}
        self.hammers = {i for i, s in catalog.specs.items() if s.get("Type") in HAMMERS}
        constants = json.loads(tables["constants"][1]) if "constants" in tables else {}
        self.base_capacity = constants.get("DefaultInventoryLimit")
        for spec in standard_variants(body, catalog):
            ident = spec["Id"]
            if rules.get(ident) is None and not (
                spec.get("MinOptions") == spec.get("MaxOptions") == 0 and not spec.get("Options")
            ):
                continue
            self.items[ident] = {
                "spec": ident,
                "kind": spec["WeaponType"],
                "collaborationId": spec.get("CollaborationId"),
                "ribbons": equipment_ribbons({}, spec, ()),
                **catalog.equipment.catalog_facts(spec),
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

    def initialize_copy(self, item):
        rules = self.rules.get(item["ItemId"])
        if rules:
            item["Options"] = roll_new_options(rules)
