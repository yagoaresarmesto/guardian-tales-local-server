# SPDX-License-Identifier: Apache-2.0
"""Display data for the current inventory and its equipment preview."""

import base64
import hashlib
from bisect import bisect_right

from guardian_tales.andras_trial_static import binary_rows
from guardian_tales.raid_custom import binary_name_hash
from guardian_tales.weapon_enhance import load_catalog

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
}


def english_inventory_names(references, specs, catalog_hash):
    # The optional local English table uses the same binding as the hero trial.
    path = references.directory / f"andras-trial-strings-{catalog_hash}.bin"
    if not path.is_file():
        return {}
    names = {}
    try:
        for spec in specs.values():
            if spec.get("Type") in CONSUMABLES or spec.get("Type") in HAMMERS:
                name = spec.get("Name")
            elif spec.get("WeaponType") or spec.get("Type") == "relic":
                name = spec.get("NameWithoutRarity")
            else:
                continue
            if name:
                names[spec["Id"]] = binary_name_hash(name)
        wanted = set(names.values())
        entries = binary_rows(
            base64.b64encode(path.read_bytes()).decode(), require_id=False, max_count=500000
        )
        strings = {key: raw.decode("utf-8") for _, key, raw in entries if key in wanted}
    except (OSError, ValueError):
        return {}
    return {ident: strings[key] for ident, key in names.items() if key in strings}


class EquipmentDisplay:
    def __init__(self, references, specs, catalog_bytes):
        self.names = english_inventory_names(
            references, specs, hashlib.sha256(catalog_bytes).hexdigest()
        )
        self.thresholds = ()
        self.hammer_exp = {}
        if (references.directory / "weapon_enhance_debug_catalog.json").is_file():
            enhancement = load_catalog(references)
            self.thresholds = enhancement["level_total_exps"]
            self.hammer_exp = enhancement["hammer_exp"]

    def facts(self, item, spec, training):
        xp = item.get("Experience")
        level = None
        rarity = spec.get("Rarity")
        if isinstance(xp, int) and self.thresholds:
            level = min(bisect_right(self.thresholds, xp) + 1, len(self.thresholds))
        return {
            "level": level,
            "stars": rarity + 1 if isinstance(rarity, int) else None,
            "grade": spec.get("OriginRarity"),
            "training": item["Id"] in training,
        }
