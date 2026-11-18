# SPDX-License-Identifier: Apache-2.0
"""Opt-in free equipment experience from owned hammers, with atomic retry receipts."""

import json

from .snapshots import CLIENT
from .village import INT_MAX, MAX_REVISION, integer

ROUTE = "/item/enhance-weapon"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_enhance_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, "
        "experience_before INTEGER NOT NULL, experience_after INTEGER NOT NULL)"
    )


def decimal_id(value):
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and len(value) <= 10
        and integer(int(value), minimum=1)
        and str(int(value)) == value
    )


def load_catalog(references):
    path = references.directory / "weapon_enhance_debug_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Equipment enhancement requires an explicit free-enhancement catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "client",
            "free",
            "level_total_exps",
            "weapons",
            "hammer_exp",
            "limit_break_coef",
            "max_limit_breaks",
            "myth_coef",
        }
        or value["client"] != CLIENT
        or value["free"] is not True
        or not isinstance(value["level_total_exps"], list)
        or not 1 <= len(value["level_total_exps"]) <= 1000
        or any(not integer(i, minimum=1) for i in value["level_total_exps"])
        or any(a >= b for a, b in zip(value["level_total_exps"], value["level_total_exps"][1:]))
        or any(
            not integer(value[k], 100)
            for k in ("limit_break_coef", "max_limit_breaks", "myth_coef")
        )
    ):
        raise ValueError("Invalid free equipment enhancement catalog")
    for key, maximum in (("weapons", 5), ("hammer_exp", INT_MAX)):
        rows = value[key]
        if (
            not isinstance(rows, dict)
            or not 1 <= len(rows) <= 30000
            or any(
                not decimal_id(k) or not integer(v, maximum, 1 if key == "hammer_exp" else 0)
                for k, v in rows.items()
            )
        ):
            raise ValueError("Invalid equipment or hammer experience specifications")
    if set(value["weapons"]) & set(value["hammer_exp"]):
        raise ValueError("Equipment and hammer specifications cannot overlap")
    return value


def enhance(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"TargetWeaponId", "SourceItems", "discountBuff"}
        or not integer(body["TargetWeaponId"], minimum=1)
        or type(body["discountBuff"]) is not bool
        or not isinstance(body["SourceItems"], dict)
        or not 1 <= len(body["SourceItems"]) <= 256
        or any(
            not decimal_id(k) or not integer(v, minimum=1) for k, v in body["SourceItems"].items()
        )
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid equipment enhancement request or identity")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    previous = account.db.execute(
        "SELECT request FROM weapon_enhance_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Enhancement retry differs from the saved request")
        return {"User": profile["User"]}
    catalog = load_catalog(account.references)
    user = profile["User"]
    weapons, hammers = user.get("ItemWeapons"), user.get("ItemStackables")
    if not isinstance(weapons, list) or not isinstance(hammers, list):
        raise ValueError("Invalid saved equipment inventory")
    matches = [r for r in weapons if isinstance(r, dict) and r.get("Id") == body["TargetWeaponId"]]
    if len(matches) != 1:
        raise ValueError("Enhancement requires one owned target equipment item")
    target = matches[0]
    if (
        not integer(target.get("ItemId"), minimum=1)
        or str(target["ItemId"]) not in catalog["weapons"]
        or type(target.get("Amount")) is not int
        or target["Amount"] != 1
        or not integer(target.get("Experience"))
        or not integer(target.get("LimitBreaks"), catalog["max_limit_breaks"])
        or type(target.get("Locked")) is not bool
        or target.get("EngraveOptions") not in (None, [])
        or not integer(user.get("Cas"), MAX_REVISION - 1)
    ):
        raise ValueError("Unsupported target equipment, engraving or account revision")
    unlocked = user.get("Unlocked")
    maximums = unlocked.get("MaxLevel") if isinstance(unlocked, dict) else None
    base = maximums.get("Weapon") if isinstance(maximums, dict) else None
    if not integer(base, len(catalog["level_total_exps"]), 1):
        raise ValueError("Invalid saved weapon level cap")
    cap_level = base + target["LimitBreaks"] * catalog["limit_break_coef"]
    if catalog["weapons"][str(target["ItemId"])] > 4:
        cap_level += catalog["myth_coef"]
    if cap_level > len(catalog["level_total_exps"]):
        raise ValueError("Equipment level cap is not covered by the matching catalog")
    cap_exp = catalog["level_total_exps"][cap_level - 1]
    if target["Experience"] >= cap_exp:
        raise ValueError("Target equipment is already at its supported level cap")
    gained = 0
    for key, count in body["SourceItems"].items():
        if int(key) == body["TargetWeaponId"]:
            raise ValueError("Target equipment cannot be an enhancement material")
        rows = [r for r in hammers if isinstance(r, dict) and r.get("Id") == int(key)]
        if len(rows) != 1:
            raise ValueError("Enhancement materials must identify owned hammer stacks")
        material = rows[0]
        if (
            not integer(material.get("ItemId"), minimum=1)
            or str(material["ItemId"]) not in catalog["hammer_exp"]
            or not integer(material.get("Amount"), minimum=count)
            or material.get("Locked") is not False
            or not integer(material.get("Experience"), 0)
            or not integer(material.get("LimitBreaks"), 0)
        ):
            raise ValueError("Unsupported, locked or insufficient owned enhancement hammers")
        gained += catalog["hammer_exp"][str(material["ItemId"])] * count
    if not integer(gained, minimum=1):
        raise ValueError("Enhancement experience exceeds the supported integer range")
    before = target["Experience"]
    target["Experience"] = min(before + gained, cap_exp)
    user["Cas"] += 1
    # Explicit free policy: gold, hammer quantities and account buffs stay intact.
    # Only the target experience and the user revision change; no mission credit
    # or unrelated item/progression updates are fabricated.
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO weapon_enhance_requests VALUES(?,?,?,?)",
            (operation_id, encoded, before, target["Experience"]),
        )
    return {"User": user}
