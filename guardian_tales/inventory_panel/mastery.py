# SPDX-License-Identifier: Apache-2.0
"""Preview and apply an offline Guardian Mastery allocation as a single edit."""

import hashlib
import json
from functools import cached_property

from guardian_tales.admin_test_items import save_profile
from guardian_tales.mastery import (
    MASTERY_POINTS,
    class_limits,
    invested_points,
    load_catalog,
    saved_mastery,
)
from guardian_tales.raid_static import decode, records
from guardian_tales.village import INT_MAX, MAX_REVISION, current_village, integer

from .game_save import GameSaveEditor


def version(user, levels, points, catalog):
    fields = [user["Id"], catalog, levels, points["Amount"], points["Spent"]]
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def refund_ceiling(catalog):
    costs = catalog["level_costs"]
    return min(INT_MAX, len(catalog["skills"]) * sum(costs) + costs[-1])


class MasteryEditor(GameSaveEditor):
    def __init__(self, database, references):
        super().__init__(database)
        self.references = references

    @cached_property
    def skill_details(self):
        tables = records(decode(self.references.read_bytes("static_data_get.bin")))[1]
        if "guardianlevel" not in tables:
            return {}
        options = {o["Id"]: o for o in json.loads(tables["options"][1])}
        guardian = json.loads(tables["guardianlevel"][1])
        ranks = {
            row["SkillLevel"]: row["OptionLevel"] for row in guardian.get("GuardianSkillLevel", [])
        }
        stats = {
            "TotalAttackScale": ("ATK", "AttackScale"),
            "HpScale": ("HP", "HpScale"),
            "DefenseScale": ("DEF", "DefenseScale"),
            "SuperSkillScale": ("Skill damage", "AttackScale"),
        }
        classes = {
            "Melee": "Warrior",
            "Projectile": "Ranged",
            "Tanker": "Tank",
            "Supporter": "Support",
        }
        details = {}
        for row in guardian.get("GuardianSkill", []):
            effects = row.get("OptionId") or []
            option = options.get(effects[0], {}) if effects else {}
            name, scale = stats.get(option.get("Class"), (None, None))
            bonuses = {}
            if scale and len(effects) == 1:
                step = option.get(scale + "Add")
                base = option.get(scale + "Base", 0)
                if isinstance(step, (float, int)) and isinstance(base, (float, int)):
                    bonuses = {
                        level: round(100 * (base + rank * step), 5) for level, rank in ranks.items()
                    }
                    bonuses[0] = 0
            details[str(row["SkillId"])] = dict(
                group=row["SkillCategoryId"],
                className=classes.get(option.get("CoopClassType")),
                name=name,
                bonuses=bonuses,
            )
        return details

    def state(self, db):
        catalog = load_catalog(self.references)
        profile = self.profile(db)
        user = profile["User"]
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='imported_account' AND type='table'"
        ).fetchone():
            raise ValueError("Guardian Mastery requires a saved, upgraded base camp.")
        levels, _ = saved_mastery(user, current_village(db), catalog)
        points = [
            a
            for a in user.get("Assets") or []
            if isinstance(a, dict) and a.get("Id") == MASTERY_POINTS
        ]
        if (
            len(points) != 1
            or not integer(points[0].get("Amount"))
            or not integer(points[0].get("Spent"), INT_MAX, -INT_MAX - 1)
        ):
            raise ValueError("Invalid saved mastery point balance or spending counter.")
        return catalog, profile, levels, points[0]

    def info(self):
        with self.reader() as db:
            catalog, profile, levels, points = self.state(db)
        costs = catalog["level_costs"]
        skills = []
        for key, group in catalog["skills"].items():
            details = self.skill_details.get(key, {})
            if details.get("group") != group:
                details = {}
            skills.append(
                dict(
                    id=key,
                    group=group,
                    level=levels.get(key, 0),
                    className=details.get("className") or f"Class {group}",
                    name=details.get("name") or f"Skill {key}",
                    bonuses=details.get("bonuses", {}),
                )
            )
        return dict(
            skills=skills,
            maxLevel=len(costs),
            levelCosts=costs,
            balance=points["Amount"],
            maxInvestment=len(skills) * sum(costs),
            refundCeiling=refund_ceiling(catalog),
            version=version(profile["User"], levels, points, catalog),
            **self.status(),
        )

    def preview(self, body):
        with self.reader() as db:
            return self.plan(db, body, apply=False)

    def apply_locked(self, db, body):
        return self.plan(db, body, apply=True)

    def plan(self, db, body, *, apply):
        if (
            not isinstance(body, dict)
            or set(body) != {"version", "levels"}
            or not isinstance(body["levels"], dict)
        ):
            raise ValueError("Choose a level for each mastery skill.")
        catalog, profile, levels, points = self.state(db)
        user = profile["User"]
        if body["version"] != version(user, levels, points, catalog):
            return 409, {
                "error": "Your mastery or points changed. Reload the saved allocation before applying."
            }
        target, costs = body["levels"], catalog["level_costs"]
        if target.keys() != catalog["skills"].keys() or any(
            not integer(v, len(costs)) for v in target.values()
        ):
            raise ValueError(f"Each skill needs a whole level between 0 and {len(costs)}.")
        totals, cap = class_limits(target, catalog)
        if max(totals.values()) > cap:
            raise ValueError(
                f"This allocation allows at most {cap} levels per class. Balance the four class totals."
            )
        delta = invested_points(target, costs) - invested_points(levels, costs)
        balance = points["Amount"] - delta
        if balance < 0:
            raise ValueError("This allocation costs more mastery points than you have.")
        spent = points["Spent"] + delta
        if not integer(spent, INT_MAX, -INT_MAX - 1):
            raise ValueError("This allocation exceeds the game's mastery spending-counter range.")
        # A credit ceiling only limits refunds. An existing higher balance survives a neutral edit.
        excess = max(0, balance - max(points["Amount"], refund_ceiling(catalog)))
        balance -= excess
        changed = any(levels.get(k, 0) != v for k, v in target.items())
        if changed and not integer(user["Cas"], MAX_REVISION - 1):
            raise ValueError("The save revision has reached its limit.")
        if apply and changed:
            levels.clear()
            levels.update((k, v) for k, v in target.items() if v)
            points.update(Amount=balance, Spent=spent)
            user["GuardianMasteryLevel"] = sum(target.values())
            save_profile(db, profile)
        return 200, dict(
            balance=balance,
            delta=delta,
            excess=excess,
            changed=changed,
            version=version(user, levels, points, catalog),
        )
