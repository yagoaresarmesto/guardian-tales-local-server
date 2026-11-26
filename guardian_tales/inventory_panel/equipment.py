# SPDX-License-Identifier: Apache-2.0
"""Display data for the current inventory and its equipment preview."""

import hashlib
from bisect import bisect_right

from guardian_tales.panel_common.labels import english_labels
from guardian_tales.weapon_enhance import load_catalog

from .equipment_ribbons import equipment_ribbons
from .stack_quantities import CONSUMABLES, HAMMERS

TYPE_ICONS = {
    "all": "ic_filter_00",
    "inventory": "ic_inventory_00",
    "equipment": "ic_equip_wp_00",
    "onehandsword": "ic_wp_sword1_00",
    "twohandsword": "ic_wp_sword2_00",
    "assaultrifle": "ic_wp_rifle_00",
    "bow": "ic_wp_bow_00",
    "basket": "ic_wp_basket_00",
    "staff": "ic_wp_staff_00",
    "gauntlet": "ic_wp_gauntlet_00",
    "claw": "ic_wp_claw_00",
    "shield": "ic_wp_shield_00",
    "accessory": "ic_wp_acc_00",
    "lock": "ic_lock_00",
    "warrior": "ic_atk_type_warrior",
    "ranged": "ic_atk_type_sniper",
    "tank": "ic_atk_type_tanker",
    "support": "ic_atk_type_support",
    "mastery-point": "ic_guardian_mastery_point",
    "book-complete": "ic_slot_book_mark_00",
    "exclusive": "ic_slot_only_mark_00",
    "exclusive-collab": "ic_slot_only_mark_collab_00",
    "engraved": "ic_slot_only_mark_engrave_00",
    "engraved-max": "ic_slot_only_mark_engrave_01",
    "engraved-collab": "slot_only_mark_engrave_collab_00",
}


def english_inventory_names(references, specs, catalog_hash, hero_name_keys):
    names = {}
    for spec in specs.values():
        if spec.get("Type") in CONSUMABLES or spec.get("Type") in HAMMERS:
            name = spec.get("Name")
        elif spec.get("WeaponType") or spec.get("Type") in ("relic", "merch"):
            name = spec.get("NameWithoutRarity")
        else:
            continue
        if name:
            names[spec["Id"]] = name
    strings = english_labels(
        references, catalog_hash, set(names.values()) | set(hero_name_keys.values())
    )
    return (
        {ident: strings[key] for ident, key in names.items() if key in strings},
        {ident: strings[key] for ident, key in hero_name_keys.items() if key in strings},
    )


class EquipmentDisplay:
    def __init__(
        self, references, specs, catalog_bytes, thresholds, hero_name_keys, completed_books
    ):
        self.names, self.hero_names = english_inventory_names(
            references, specs, hashlib.sha256(catalog_bytes).hexdigest(), hero_name_keys
        )
        self.thresholds = thresholds
        self.completed_books = completed_books
        self.hammer_exp = {}
        if (references.directory / "weapon_enhance_debug_catalog.json").is_file():
            enhancement = load_catalog(references)
            self.thresholds = thresholds or enhancement["level_total_exps"]
            self.hammer_exp = enhancement["hammer_exp"]

    def catalog_facts(self, spec):
        rarity = spec.get("Rarity")
        hero = spec.get("ExclusiveCharacterId") or None
        return {
            "stars": rarity + 1 if isinstance(rarity, int) else None,
            "grade": spec.get("OriginRarity"),
            "exclusiveHero": hero,
            "exclusiveHeroName": self.hero_names.get(hero),
        }

    def facts(self, item, spec, training):
        xp = item.get("Experience")
        level = None
        if isinstance(xp, int) and self.thresholds:
            level = min(bisect_right(self.thresholds, xp) + 1, len(self.thresholds))
        return {
            **self.catalog_facts(spec),
            "level": level,
            "ribbons": equipment_ribbons(item, spec, self.completed_books),
            "training": item["Id"] in training,
        }
