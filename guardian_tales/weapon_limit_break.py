# SPDX-License-Identifier: Apache-2.0
"""Opt-in hammer limit-break mock retaining all materials and currency."""

import json

from .snapshots import CLIENT
from .village import INT_MAX, MAX_REVISION, integer
from .weapon_enhance import decimal_id

ROUTE = "/item/limitbreak-weapon/v2"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_limit_break_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, "
        "breaks_before INTEGER NOT NULL, breaks_after INTEGER NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / "weapon_limit_break_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Equipment limit breaks require an explicit free mock catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "free", "weapons", "hammers", "max_limit_breaks"}
        or value["client"] != CLIENT
        or value["free"] is not True
        or not integer(value["max_limit_breaks"], 100, 1)
    ):
        raise ValueError("Invalid equipment limit-break mock catalog")
    for key, maximum in (("weapons", 30000), ("hammers", 64)):
        rows = value[key]
        if (
            not isinstance(rows, dict)
            or not 1 <= len(rows) <= maximum
            or any(not decimal_id(k) or not integer(v, 4, 3) for k, v in rows.items())
        ):
            raise ValueError("Invalid target origin rarity or limit-break hammer rarity")
    if set(value["weapons"]) & set(value["hammers"]):
        raise ValueError("Equipment and limit-break hammer specs cannot overlap")
    return value


def limit_break(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"TargetWeaponId", "SourceItems", "discountBuff"}
        or not integer(body["TargetWeaponId"], minimum=1)
        or not isinstance(body["SourceItems"], dict)
        or not 1 <= len(body["SourceItems"]) <= 256
        or any(
            not decimal_id(k) or not integer(v, minimum=1) for k, v in body["SourceItems"].items()
        )
        or type(body["discountBuff"]) is not bool
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid equipment limit-break request or identity")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    previous = account.db.execute(
        "SELECT request FROM weapon_limit_break_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Limit-break retry differs from the saved request")
        return {"User": profile["User"]}
    catalog = load_catalog(account.references)
    user = profile["User"]
    weapons, hammers = user.get("ItemWeapons"), user.get("ItemStackables")
    if not isinstance(weapons, list) or not isinstance(hammers, list):
        raise ValueError("Invalid saved equipment or hammer inventory")
    targets = [r for r in weapons if isinstance(r, dict) and r.get("Id") == body["TargetWeaponId"]]
    if len(targets) != 1:
        raise ValueError("Limit breaking requires one owned target equipment item")
    target = targets[0]
    if (
        not integer(target.get("Id"), minimum=1)
        or not integer(target.get("ItemId"), minimum=1)
        or str(target["ItemId"]) not in catalog["weapons"]
        or not integer(target.get("Amount"), 1, 1)
        or not integer(target.get("Experience"))
        or not integer(target.get("LimitBreaks"), catalog["max_limit_breaks"] - 1)
        or type(target.get("Locked")) is not bool
        or target.get("EngraveOptions") not in (None, [])
        or not integer(user.get("Cas"), MAX_REVISION - 1)
    ):
        raise ValueError("Unsupported, engraved or capped equipment, or invalid user revision")
    origin = catalog["weapons"][str(target["ItemId"])]
    gained = 0
    for key, count in body["SourceItems"].items():
        if int(key) == body["TargetWeaponId"]:
            raise ValueError("Target equipment cannot be a limit-break material")
        rows = [r for r in hammers if isinstance(r, dict) and r.get("Id") == int(key)]
        if len(rows) != 1:
            raise ValueError("Limit-break materials must identify owned hammer stacks")
        material = rows[0]
        if (
            not integer(material.get("Id"), minimum=1)
            or not integer(material.get("ItemId"), minimum=1)
            or catalog["hammers"].get(str(material["ItemId"])) != origin
            or not integer(material.get("Amount"), minimum=count)
            or material.get("Locked") is not False
            or not integer(material.get("Experience"), 0)
            or not integer(material.get("LimitBreaks"), 0)
        ):
            raise ValueError("Unsupported, locked, mismatched or insufficient limit-break hammers")
        gained += count
    if not integer(gained, INT_MAX, 1):
        raise ValueError("Limit-break hammer count exceeds the supported integer range")
    before = target["LimitBreaks"]
    target["LimitBreaks"] = min(before + gained, catalog["max_limit_breaks"])
    user["Cas"] += 1
    # Local free mock: retain hammers, gold, experience, buffs and mission state.
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO weapon_limit_break_requests VALUES(?,?,?,?)",
            (operation_id, encoded, before, target["LimitBreaks"]),
        )
    return {"User": user}
