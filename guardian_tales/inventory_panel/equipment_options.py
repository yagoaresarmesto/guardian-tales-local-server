# SPDX-License-Identifier: Apache-2.0
"""Per-copy weapon and accessory options from the installed item's exact specification."""

import itertools
import json
import math
from random import SystemRandom

from guardian_tales.admin_test_items import save_profile
from guardian_tales.item_sell import gear_references
from guardian_tales.raid_static import decode, records
from guardian_tales.village import MAX_REVISION, integer
from guardian_tales.weapon_options import valid_options

from .game_save import GameSaveEditor
from .stack_quantities import HAMMERS, StackQuantityEditor
from .weapon_progression import WeaponProgression

RANDOM = SystemRandom()
EDIT_FIELDS = ("Options", "LimitBreaks", "EngraveCeiling", "EngraveOptions", "Experience", "Amount")
ELEMENTS = {"none": "Basic", "ice": "Water", "darkness": "Dark"}
SCALES = {
    "HpScale": ("HP", "HpScaleAdd"),
    "DefenseScale": ("DEF", "DefenseScaleAdd"),
    "TotalAttackScale": ("ATK", "AttackScaleAdd"),
    "RecoveryScale": ("Heal", "RecoveryScaleAdd"),
    "ManaRegenScale": ("Weapon Skill Regen Speed", "ScaleAdd"),
    "SuperSkillScale": ("Skill damage", "AttackScaleAdd"),
    "WeaponDefenseUp": ("Equipment DEF", "DefUpAdd"),
    "CriticalMultiplierScaleUp": ("Critical hit multiplier", "CriticalUpAdd"),
    "HpRecoveryOnKill": ("HP restored on enemy kill", "RecoveryAdd"),
    "ShieldGenerationOnBattleStart": ("Shield on battle start", "GenerationAdd"),
    "ShieldGenerationOnKill": ("Shield on enemy kill", "GenerationAdd"),
}


def effect_display(effect, buffs):
    kind = effect["Class"]
    unit, multiplier = "%", 100
    if kind in SCALES:
        name, field = SCALES[kind]
    elif kind in ("WeaponElementalUp", "ElementalScale"):
        element = effect["Elemental"]
        name = ELEMENTS.get(element, element.title()) + " ATK"
        field = "ElementalUpAdd" if kind == "WeaponElementalUp" else "ElementalScaleAdd"
    elif kind == "DebuffResist":
        name, field = effect["ResistType"] + " debuff resistance", "ResistAdd"
    elif kind == "WeaponDamageReduction":
        name, field, unit, multiplier = "Damage reduction", "DamageReductionAdd", "", 1
    elif effect.get("ConditionType") == "EngraveOptionExclusive" and kind in (
        "CriticalChanceUp",
        "CriticalResistanceUp",
    ):
        name, field = (
            ("Critical hit chance", "CriticalUpAdd")
            if kind == "CriticalChanceUp"
            else ("Critical hit resistance", "CriticalResistanceAdd")
        )
        multiplier = 1
    elif (
        kind == "BuffOnKill"
        and effect.get("BuffId") in buffs
        and "AttackScaleAdd" in buffs[effect["BuffId"]]
    ):
        effect = buffs[effect["BuffId"]]
        name, field = "ATK on enemy kill", "AttackScaleAdd"
    else:
        # Expose native levels where this preview has no verified display conversion.
        name = {
            "CriticalResistanceUp": "Critical hit resistance",
            "ManaRecoveryOnKill": "Weapon skill recovery on kill",
        }.get(kind, effect["Name"].replace("_", " ").title())
        return {"name": name, "step": 1, "base": 0, "unit": "level"}
    return {
        "name": name,
        "step": round(effect[field] * multiplier, 6),
        "base": round(effect.get(field.removesuffix("Add") + "Base", 0) * multiplier, 6),
        "unit": unit,
    }


def rules_for(spec, effects):
    rules = {}
    for o in spec.get("Options") or []:
        ident, p = o["OptionId"], o["Probability"]
        if p == 0:
            continue
        if (
            ident in rules
            or ident not in effects
            or not 0 < p <= 1
            or not integer(o["MinLevel"])
            or not integer(o["MaxLevel"], minimum=o["MinLevel"])
        ):
            return None
        rules[ident] = {"low": o["MinLevel"], "high": o["MaxLevel"], "probability": p}
    low, high = spec.get("MinOptions"), spec.get("MaxOptions")
    if not rules or not integer(low) or not integer(high, len(rules), low):
        return None
    weights = spec.get("OptionCountWeights")
    if weights is not None and (len(weights) != high - low + 1 or any(w < 0 for w in weights)):
        return None
    required = sum(r["probability"] == 1 for r in rules.values())
    counts = [
        n for n in range(max(low, required), high + 1) if weights is None or weights[n - low] > 0
    ]
    if not counts:
        return None
    return {
        "options": rules,
        "counts": counts,
        "countWeights": {n: weights[n - low] for n in counts} if weights else {},
    }


def allowed_values(spec, levels):
    rules = spec["options"]
    return all(
        ident in rules and integer(level, rules[ident]["high"], rules[ident]["low"])
        for ident, level in levels.items()
    )


def read_levels(spec, values):
    ids = {str(i): i for i in spec["options"]}
    if not isinstance(values, dict) or not values.keys() <= ids.keys():
        raise ValueError("Choose options from this item's catalog.")
    levels = {ids[key]: level for key, level in values.items()}
    if not allowed_values(spec, levels):
        raise ValueError("Choose values within this item's option ranges.")
    return levels


def legal_levels(spec, levels):
    rules = spec["options"]
    return (
        len(levels) in spec["counts"]
        and allowed_values(spec, levels)
        and all(ident in levels for ident, rule in rules.items() if rule["probability"] == 1)
    )


def unavailable(item, spec, pending):
    if pending:
        return "This copy has a pending in-game option change."
    if not spec:
        return "This item has no supported rollable options."
    rows = item.get("Options")
    if (
        item.get("Amount") != 1
        or type(item.get("Locked")) is not bool
        or (
            rows not in (None, [])
            and (
                not valid_options(rows)
                or not legal_levels(spec, {o["OptionId"]: o["Level"] for o in rows})
            )
        )
    ):
        return "The saved options do not match this item's catalog."
    return ""


def generate(spec, rows, locked):
    rules = spec["options"]
    keep = {r["OptionId"]: r["Level"] for r in rows if rules[r["OptionId"]]["probability"] == 1}
    keep.update(locked)
    for ident, rule in rules.items():
        if rule["probability"] == 1 and ident not in keep:
            keep[ident] = RANDOM.randint(rule["low"], rule["high"])
    pool = [i for i in rules if i not in keep]
    counts = [n for n in spec["counts"] if len(keep) <= n <= len(keep) + len(pool)]
    if not counts:
        raise ValueError("Unlock a sub-option to allow a valid roll for this item.")
    if spec["countWeights"]:
        counts = RANDOM.choices(counts, [spec["countWeights"][n] for n in counts])
    choices, weights = [], []
    for count in counts:
        for subset in itertools.combinations(pool, count - len(keep)):
            choices.append(subset)
            weights.append(
                math.prod(
                    rules[i]["probability"] if i in subset else 1 - rules[i]["probability"]
                    for i in pool
                )
            )
    for ident in RANDOM.choices(choices, weights)[0]:
        keep[ident] = RANDOM.randint(rules[ident]["low"], rules[ident]["high"])
    return keep


def roll_basics(spec, locked):
    return {
        ident: locked[ident] if ident in locked else RANDOM.randint(rule["low"], rule["high"])
        for ident, rule in spec["options"].items()
        if rule["probability"] == 1
    }


class EquipmentOptionEditor(GameSaveEditor):
    def __init__(self, database, catalog):
        super().__init__(database)
        self.catalog = catalog
        self.hammers = StackQuantityEditor(database, catalog, HAMMERS)
        tables = records(decode(catalog.refs.read_bytes("static_data_get.bin")))[1]
        self.progression = WeaponProgression(tables)
        buffs = {row["Id"]: row for row in json.loads(tables["buffs"][1])}
        weapons = {i: s for i, s in catalog.specs.items() if s.get("Type") == "weapon"}
        ids = {o["OptionId"] for s in weapons.values() for o in s.get("Options") or []}
        ids.update(
            o["OptionId"] for s in weapons.values() for o in s.get("EngraveRandomOptions") or []
        )
        self.effects = {
            o["Id"]: effect_display(o, buffs)
            for o in json.loads(tables["options"][1])
            if o["Id"] in ids
        }
        self.specs = {i: rules_for(s, self.effects) for i, s in weapons.items()}

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
            pending = self.pending_items(db, "weapon_option_proposals")
        equipped = gear_references(user["Characters"])
        training = {slot.get("ItemId") for slot in user.get("TrainingSlots", {}).values()}
        rows, used = [], {}
        for item in user["ItemWeapons"]:
            ident, key = item["Id"], item["ItemId"]
            spec = self.catalog.specs.get(key, {})
            used[key] = self.specs.get(key)
            name = (
                self.catalog.names.get(key)
                or spec.get("NameWithoutRarity", f"Item {key}").replace("_", " ").title()
            )
            rows.append(
                dict(
                    id=ident,
                    spec=key,
                    name=name,
                    key=spec.get("Name", ""),
                    kind=spec.get("WeaponType", ""),
                    locked=item["Locked"],
                    equipped=ident in equipped,
                    breaks=item.get("LimitBreaks") or 0,
                    options=item.get("Options") or [],
                    version=self.option_version(user, item, *EDIT_FIELDS),
                    progression=(
                        self.progression.choices(item, spec) if ident not in pending else None
                    ),
                    unavailable=unavailable(item, used[key], ident in pending),
                    **self.catalog.equipment.facts(item, spec, training),
                )
            )
        return dict(
            rows=rows,
            hammers=self.hammers.rows(user),
            specs=used,
            effects=self.effects,
            revision=user["Cas"],
            hasIcons=self.catalog.has_icons,
            **self.status(),
        )

    def request(self, body, *, roll=False):
        required = {"id", "version", "revision"}
        optional = {"lockedValues", "group"} if roll else {"lockedValues", "options", "progression"}
        if (
            not isinstance(body, dict)
            or not required <= body.keys() <= required | optional
            or (not roll and not ({"options", "progression"} & body.keys()))
            or (not roll and "lockedValues" in body and "options" not in body)
            or (roll and body.get("group", "sub") not in ("basic", "sub"))
            or not integer(body["id"], minimum=1)
            or not integer(body["revision"], MAX_REVISION)
            or not isinstance(body["version"], str)
            or len(body["version"]) != 64
        ):
            raise ValueError("Select a current equipment copy.")
        if roll:
            with self.reader() as db:
                return self.process(db, body, roll=True)
        return self.write(body)

    def apply_locked(self, db, body):
        return self.process(db, body, roll=False)

    def process(self, db, body, *, roll):
        profile = self.profile(db)
        user = profile["User"]
        matches = [i for i in user["ItemWeapons"] if i["Id"] == body["id"]]
        if (
            len(matches) != 1
            or body["revision"] > user["Cas"]
            or self.option_version(user, matches[0], *EDIT_FIELDS) != body["version"]
        ):
            return 409, {"error": "This equipment changed. Review its current options again."}
        item = matches[0]
        spec = self.specs.get(item["ItemId"])
        pending = item["Id"] in self.pending_items(db, "weapon_option_proposals")
        if pending:
            raise ValueError("This copy has a pending in-game option change.")
        changes = {}
        if "progression" in body:
            changes = self.progression.changes(
                item, self.catalog.specs.get(item["ItemId"], {}), body["progression"]
            )
        if roll or "options" in body:
            result = self.edit_options(item, spec, body, roll=roll)
            if roll:
                return 200, {"options": result}
            if result != (item.get("Options") or []):
                changes["Options"] = result
        if changes:
            if not integer(user["Cas"], MAX_REVISION - 1):
                raise ValueError("The game save revision has reached its limit.")
            item.update(changes)
            save_profile(db, profile)
        return 200, {"revision": user["Cas"]}

    @staticmethod
    def edit_options(item, spec, body, *, roll):
        reason = unavailable(item, spec, False)
        if reason:
            raise ValueError(reason)
        rows = item.get("Options") or []
        locked = (
            read_levels(spec, body["lockedValues"])
            if "lockedValues" in body
            else {o["OptionId"]: o["Level"] for o in rows if o["Locked"]}
        )
        if roll:
            if body.get("group") == "basic":
                return roll_basics(spec, locked)
            return generate(spec, rows, locked)
        levels = read_levels(spec, body["options"])
        if not legal_levels(spec, levels):
            raise ValueError("Choose allowed effects, count and values for this exact item.")
        by_id = {o["OptionId"]: o for o in rows}
        if any(levels.get(i) != value for i, value in locked.items()):
            raise ValueError("Unlock the option before changing or removing its protected value.")
        new = [
            dict(o, Level=levels[i], Locked=i in locked) for i, o in by_id.items() if i in levels
        ]
        new.extend(
            {"OptionId": i, "Level": levels[i], "Locked": i in locked, "OptionSource": 0}
            for i in spec["options"]
            if i in levels and i not in by_id
        )
        return new
