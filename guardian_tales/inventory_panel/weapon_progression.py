# SPDX-License-Identifier: Apache-2.0
"""Weapon progression choices derived from the installed client enhancement tables."""

import json

from guardian_tales.village import integer
from guardian_tales.weapon_engrave import saved_option_pair, valid_option

WEAPON_TYPES = {
    "onehandsword",
    "twohandsword",
    "assaultrifle",
    "bow",
    "basket",
    "staff",
    "gauntlet",
    "claw",
}


class WeaponProgression:
    def __init__(self, tables):
        enhance = json.loads(tables["weaponenhance"][1]) if "weaponenhance" in tables else {}
        constants = enhance.get("Constants", {})
        self.max_breaks = constants.get("WeaponMaxLimitBreak")
        self.max_count = constants.get("WeaponEngravingCeiling")
        requirement = constants.get("WeaponEngravingLevelRequirement")
        self.min_xp = next(
            (
                row["TotalExps"]
                for row in enhance.get("LevelExps", [])
                if integer(requirement, minimum=1) and row["Level"] == requirement - 1
            ),
            None,
        )
        self.weights = {}
        for row in enhance.get("WeaponEngraveOptionProbability", []):
            self.weights.setdefault(row["CeilingCount"] + 1, []).append(row["OptionWeights"])

    def choices(self, item, spec):
        breaks = item.get("LimitBreaks", 0)
        if (
            spec.get("Type") != "weapon"
            or spec.get("WeaponType") not in WEAPON_TYPES
            or not integer(self.max_breaks, 100, 1)
            or not integer(breaks, self.max_breaks)
            or not integer(item.get("Amount"), 1, 1)
            or not integer(item.get("Experience"))
            or type(item.get("Locked")) is not bool
        ):
            return None
        count = item.get("EngraveCeiling", 0)
        saved = item.get("EngraveOptions")
        if saved is None:
            saved = []
        if not isinstance(saved, list) or not integer(count):
            return None
        if (saved or count) and breaks != self.max_breaks:
            return None
        result = {"maxBreaks": self.max_breaks, "engraving": None}
        options = spec.get("EngraveRandomOptions") or []
        if (
            not integer(spec.get("Rarity"), 5, 4)
            or not integer(spec.get("ExclusiveCharacterId"), minimum=1)
            or not spec.get("EngraveStaticOptions")
            or not options
            or not all(map(valid_option, options))
            or len({o["OptionId"] for o in options}) != 1
            or not integer(self.max_count, 100, 1)
            or not integer(count, self.max_count)
            or not integer(self.min_xp, minimum=1)
        ):
            return result
        if (count == 0 and saved) or (
            count and (len(saved) != 1 or saved_option_pair(saved[0]) not in options)
        ):
            return result
        current = saved[0]["Level"] if count else 0
        highest = max(o["Level"] for o in options)
        tiers = {}
        enough_xp = item["Experience"] >= self.min_xp
        locked = bool(saved and saved[0].get("Locked"))
        if enough_xp and current < highest and not locked:
            for target in range(count + 1, self.max_count + 1):
                weights = self.weights.get(target, [])
                if not weights or any(len(row) != len(options) for row in weights):
                    break
                allowed = sorted(
                    {
                        o["Level"]
                        for index, o in enumerate(options)
                        if o["Level"] >= current and any(row[index] > 0 for row in weights)
                    }
                )
                if not allowed:
                    break
                tiers[target] = allowed
                if allowed == [highest]:
                    break
        result["engraving"] = dict(
            count=count,
            maxCount=self.max_count,
            optionId=options[0]["OptionId"],
            level=current,
            highest=highest,
            enoughExperience=enough_xp,
            locked=locked,
            tiers=tiers,
        )
        return result

    def changes(self, item, spec, requested):
        choices = self.choices(item, spec)
        if (
            not choices
            or not isinstance(requested, dict)
            or not requested
            or requested.keys() - {"breaks", "engraving"}
        ):
            raise ValueError("Choose a supported weapon upgrade.")
        changes = {}
        breaks = item.get("LimitBreaks", 0)
        if "breaks" in requested:
            new = requested["breaks"]
            if not integer(new, choices["maxBreaks"], breaks + 1):
                raise ValueError("Choose a higher limit break within this weapon's cap.")
            changes["LimitBreaks"] = breaks = new
        if "engraving" in requested:
            edit = requested["engraving"]
            engraving = choices["engraving"]
            if (
                not engraving
                or breaks != choices["maxBreaks"]
                or not isinstance(edit, dict)
                or edit.keys() != {"count", "level"}
                or not integer(edit["count"], minimum=1)
                or not integer(edit["level"], minimum=1)
                or edit["level"] not in engraving["tiers"].get(edit["count"], [])
            ):
                raise ValueError("Choose an available engraving count and tier for this weapon.")
            row = (item.get("EngraveOptions") or [{}])[0]
            changes.update(
                EngraveCeiling=edit["count"],
                EngraveOptions=[dict(row, OptionId=engraving["optionId"], Level=edit["level"])],
            )
        return changes
