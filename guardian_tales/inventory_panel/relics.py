# SPDX-License-Identifier: Apache-2.0
"""Read the working save and apply bounded relic edits while its backend is stopped."""

import json
from threading import Lock

from guardian_tales.administration.admin_test_items import save_profile
from guardian_tales.inventory.item_sell import gear_references
from guardian_tales.inventory.relic_options import target_item
from guardian_tales.settlement.village import MAX_REVISION, integer

from .game_save import GameSaveEditor

# Native coefficients convert saved option levels into the values on the item card.
# A flat unit uses multiplier 1. Percentage fractions use 100.
EFFECTS = {
    "relic_base_atk_scale": ("ATK", "AttackScaleAdd", 100, "%"),
    "relic_base_def_scale": ("DEF", "DefenseScaleAdd", 100, "%"),
    "relic_base_hp_scale": ("HP", "HpScaleAdd", 100, "%"),
    "relic_base_recovery_scale": ("Heal", "RecoveryScaleAdd", 100, "%"),
    "relic_base_super_skill_scale": ("Skill damage", "AttackScaleAdd", 100, "%"),
    "relic_base_crit_probability_permill": ("Critical hit chance", "CriticalUpAdd", 1, "%"),
    "relic_pve_protection": ("Damage reduction in PvE", "PveModifierAdd", 100, "%"),
    "relic_boss_damage_boost": ("Damage to bosses", "BossModifierAdd", 100, "%"),
    "relic_pvp_damage_boost": ("PvP damage", "PvpModifierAdd", 100, "%"),
    "relic_crit_scale_up": ("Critical hit multiplier", "CriticalUpAdd", 100, "%"),
    "relic_hp_recovery_period": ("HP recovery", "HpRecoveryAdd", 100, "%"),
    "relic_extra_melee_range_atk": ("Melee area damage", "DamageRate", 100, "%"),
    "relic_extra_projectile_range_atk": ("Ranged area damage", "DamageRate", 100, "%"),
    "relic_exorcism_up": ("Mystic Resistance", "ExorcismAdd", 1, ""),
}
FAMILIES = {
    "relic_candelabrum": "Candelabrum",
    "relic_holygrail": "Grail",
    "relic_scripture": "Scripture",
    "relic_bell": "Bell",
}
OPTION_SOURCES = {"main": 1, "bonus": 2}
POOL_FIELDS = {"main": "mainPools", "bonus": "pools"}


def option_groups(item):
    options = item.get("RelicOptions") or []
    return {
        name: [o for o in options if o["OptionSource"] == source]
        for name, source in OPTION_SOURCES.items()
    }


def display_effect(spec):
    conversion = EFFECTS.get(spec["Name"])
    if not conversion:
        return None
    label, coefficient, multiplier, unit = conversion
    step = spec[coefficient] * multiplier
    base = spec.get(coefficient.removesuffix("Add") + "Base", 0) * multiplier
    if "Interval" in spec:
        label += f' every {spec["Interval"]} s'
    return dict(name=label, step=round(step, 6), base=round(base, 6), unit=unit)


class RelicEditor(GameSaveEditor):
    def __init__(self, database, catalog, tables):
        super().__init__(database)
        self.guard = Lock()
        self.initial = {}
        self.effects = {
            s["Id"]: effect
            for s in json.loads(tables["options"][1])
            if (effect := display_effect(s))
        }
        self.specs = {}
        for spec in catalog.specs.values():
            if spec.get("Type") != "relic":
                continue
            key = spec.get("NameWithoutRarity", "")
            family = FAMILIES.get(key, key.replace("_", " ").title() or "Relic")
            self.specs[spec["Id"]] = dict(
                name=catalog.names.get(spec["Id"], family),
                family=family,
                stars=spec["OriginRarity"] + 1,
                mainPools=self.slot_pools(spec.get("BaseOptions", [])),
                pools=self.slot_pools(spec.get("ChangeOptions", [])),
            )

    def slot_pools(self, slots):
        return [
            {
                o["OptionId"]: (o["MinLevel"], o["MaxLevel"])
                for o in pool
                if o["OptionId"] in self.effects and o["Probability"] > 0
            }
            for pool in slots
        ]

    def info(self):
        with self.guard, self.reader() as db:
            user = self.profile(db)["User"]
            pending = self.pending_items(db, "relic_option_proposals")
            result = self.listing(user, pending)
        return {**result, **self.status()}

    def listing(self, user, pending):
        equipped = gear_references(user["Characters"])
        copies = []
        for item in user["ItemMiscs"]:
            ident = item["Id"]
            if item["ItemId"] not in self.specs:
                continue
            groups = option_groups(item)
            original = {}
            for group, slots in groups.items():
                original[group] = [
                    self.initial.setdefault(
                        (user["Id"], ident, item["ItemId"], group, i), (o["OptionId"], o["Level"])
                    )
                    for i, o in enumerate(slots)
                ]
            copies.append(
                dict(
                    id=ident,
                    spec=item["ItemId"],
                    locked=item["Locked"],
                    equipped=ident in equipped,
                    jewels=sum(bool(j) for j in item.get("JewelSlots") or []),
                    **groups,
                    initialMain=original["main"],
                    initial=original["bonus"],
                    version=self.option_version(user, item, "RelicOptions"),
                    pending=ident in pending,
                )
            )
        return dict(
            copies=copies,
            specs=self.specs,
            effects=self.effects,
            revision=user["Cas"],
            inventoryVersion=self.inventory_version(user),
        )

    def apply(self, body):
        if (
            not isinstance(body, dict)
            or set(body) != {"id", "revision", "version", "changes"}
            or not integer(body["id"], minimum=1)
            or not integer(body["revision"], MAX_REVISION)
            or not isinstance(body["version"], str)
            or len(body["version"]) != 64
            or not isinstance(body["changes"], list)
            or not 1 <= len(body["changes"]) <= 32
        ):
            raise ValueError("Select a relic and its options.")
        return self.write(body)

    def apply_locked(self, db, body):
        profile = self.profile(db)
        user = profile["User"]
        # Unrelated game progress is retained from the current transaction. The
        # per-item version below detects conflicting edits to this specific relic.
        if body["revision"] > user["Cas"]:
            return 409, {
                "error": "The game save has changed. Review the current relic options again."
            }
        item = target_item(user, body["id"])
        if self.option_version(user, item, "RelicOptions") != body["version"]:
            return 409, {"error": "This relic has changed. Review its current options again."}
        spec = self.specs.get(item["ItemId"])
        if spec is None or item["Id"] in self.pending_items(db, "relic_option_proposals"):
            raise ValueError("This relic is unavailable for editing.")
        slots = option_groups(item)
        seen = set()
        updates = []
        for change in body["changes"]:
            if (
                not isinstance(change, dict)
                or set(change) - {"group"} != {"slot", "option", "level"}
                or not integer(change["option"], minimum=1)
                or type(change["level"]) is not int
            ):
                raise ValueError("Select an existing relic slot and a valid effect.")
            group = change.get("group", "bonus")
            if not isinstance(group, str) or group not in slots:
                raise ValueError("Unknown relic option group.")
            pools = spec[POOL_FIELDS[group]]
            index, option, level = change["slot"], change["option"], change["level"]
            if not integer(index, min(len(slots[group]), len(pools)) - 1):
                raise ValueError("Select an existing relic slot.")
            row = slots[group][index]
            bounds = pools[index].get(option)
            if (
                (group, index) in seen
                or row["Locked"]
                or not bounds
                or not bounds[0] <= level <= bounds[1]
            ):
                raise ValueError("The option or value is not allowed for this slot.")
            seen.add((group, index))
            if (option, level) != (row["OptionId"], row["Level"]):
                updates.append((row, option, level))
        if updates:
            if not integer(user["Cas"], MAX_REVISION - 1):
                raise ValueError("The game save revision has reached its limit.")
            for row, option, level in updates:
                row.update(OptionId=option, Level=level)
            save_profile(db, profile)
        return 200, {"revision": user["Cas"]}
