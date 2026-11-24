# SPDX-License-Identifier: Apache-2.0
"""Spend saved mastery points on one catalog-backed guardian skill level."""

import json
from collections import Counter

from .basecamp import MASTERY_POINTS
from .snapshots import CLIENT
from .village import INT_MAX, MAX_REVISION, current_village, integer

ROUTE = "/user/guardian-mastery-level-up"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS mastery_level_requests "
        "(operation_id TEXT PRIMARY KEY, skill_id INTEGER NOT NULL, cost INTEGER NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / "guardian_mastery_catalog.json"
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Mastery upgrades require a matching external catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "portal_specs", "skills", "level_costs"}
        or value["client"] != CLIENT
        or not isinstance(value["portal_specs"], list)
        or not 1 <= len(value["portal_specs"]) <= 100
        or any(not integer(i, minimum=1) for i in value["portal_specs"])
        or len(set(value["portal_specs"])) != len(value["portal_specs"])
        or not isinstance(value["skills"], dict)
        or not 1 <= len(value["skills"]) <= 1000
        or any(
            not isinstance(k, str)
            or not k.isascii()
            or not k.isdecimal()
            or not integer(int(k), minimum=1)
            or str(int(k)) != k
            or not integer(v, 4, 1)
            for k, v in value["skills"].items()
        )
        or set(value["skills"].values()) != {1, 2, 3, 4}
        or not isinstance(value["level_costs"], list)
        or not 1 <= len(value["level_costs"]) <= 1000
        or any(not integer(c, minimum=1) for c in value["level_costs"])
    ):
        raise ValueError("Invalid guardian mastery catalog")
    return value


def saved_mastery(user, village, catalog):
    """Validate shared camp ownership, skill levels and their serialized total."""
    skills, costs = catalog["skills"], catalog["level_costs"]
    buildings = village.get("Buildings")
    camps = (
        [
            b
            for b in buildings
            if isinstance(b, dict)
            and type(b.get("SpecId")) is int
            and b["SpecId"] in catalog["portal_specs"]
        ]
        if isinstance(buildings, list)
        else []
    )
    if (
        village.get("UserId") != user.get("Id")
        or len(camps) != 1
        or type(camps[0].get("Status")) is not int
        or camps[0]["Status"] != 2
    ):
        raise ValueError("Mastery operations require an opened upgraded base camp")
    options = user.get("Options")
    mastery = options.get("GuardianMastery") if isinstance(options, dict) else None
    levels = mastery.get("GuardianMasterySkill") if isinstance(mastery, dict) else None
    if not isinstance(levels, dict) or any(
        k not in skills or not integer(v, len(costs)) for k, v in levels.items()
    ):
        raise ValueError("Invalid saved guardian mastery skills")
    total = sum(levels.values())
    if not integer(user.get("GuardianMasteryLevel")) or user["GuardianMasteryLevel"] != total:
        raise ValueError("Saved mastery total differs from its skill levels")
    return levels, total


def class_limits(levels, catalog):
    skills, costs = catalog["skills"], catalog["level_costs"]
    class_levels = {
        c: sum(levels.get(k, 0) for k, v in skills.items() if v == c) for c in (1, 2, 3, 4)
    }
    # The native cap advances in tens with the lowest class total. Its maximum
    # is the largest class's skill count multiplied by the per-skill level count.
    maximum = max(Counter(skills.values()).values()) * len(costs)
    cap = min((min(class_levels.values()) // 10 + 1) * 10, maximum)
    return class_levels, cap


def invested_points(levels, costs):
    return sum(sum(costs[:level]) for level in levels.values())


def upgrade(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"SkillId"}
        or not integer(body["SkillId"], minimum=1)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Mastery upgrades require one SkillId after the prologue")
    skill_id = body["SkillId"]
    profile = account.profile()
    user = profile["User"]
    previous = account.db.execute(
        "SELECT skill_id FROM mastery_level_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != skill_id:
            raise ValueError("Mastery retry differs from the saved request")
        return {"User": user}
    catalog = load_catalog(account.references)
    skills, costs = catalog["skills"], catalog["level_costs"]
    if str(skill_id) not in skills:
        raise ValueError("Unknown guardian mastery skill")
    levels, total = saved_mastery(user, current_village(account.db), catalog)
    class_levels, cap = class_limits(levels, catalog)
    key = str(skill_id)
    level = levels.get(key, 0)
    if level >= len(costs) or class_levels[skills[key]] >= cap:
        raise ValueError("Guardian mastery skill or class is at its current limit")
    assets = user.get("Assets")
    rows = (
        [a for a in assets if isinstance(a, dict) and a.get("Id") == MASTERY_POINTS]
        if isinstance(assets, list)
        else []
    )
    cost = costs[level]
    if (
        len(rows) != 1
        or not integer(rows[0].get("Amount"))
        or not integer(rows[0].get("Spent"), INT_MAX, -INT_MAX - 1)
        or rows[0]["Amount"] < cost
        or rows[0]["Spent"] > INT_MAX - cost
        or not integer(user.get("Cas"), MAX_REVISION - 1)
    ):
        raise ValueError("Invalid or insufficient mastery points, spending counter or revision")
    rows[0]["Amount"] -= cost
    rows[0]["Spent"] += cost
    levels[key] = level + 1
    user["GuardianMasteryLevel"] = total + 1
    user["Cas"] += 1
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO mastery_level_requests VALUES(?,?,?)", (operation_id, skill_id, cost)
        )
    return {"User": user}
