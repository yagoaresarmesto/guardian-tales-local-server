# SPDX-License-Identifier: Apache-2.0
"""Opt-in first engraving with retained hammer/gold and bounded local option rolls."""

import json
from secrets import randbelow

from .snapshots import CLIENT
from .village import MAX_REVISION, integer
from .weapon_enhance import decimal_id

ROUTE = "/item/engrave-weapon"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_engrave_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, result_options TEXT NOT NULL)"
    )


def valid_option(option):
    return (
        isinstance(option, dict)
        and set(option) == {"OptionId", "Level"}
        and integer(option["OptionId"], minimum=1)
        and integer(option["Level"], 1000, 1)
    )


def load_catalog(references):
    path = references.directory / "weapon_engrave_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("First engraving requires an explicit free engraving mock catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "client",
            "free",
            "min_experience",
            "required_limit_breaks",
            "engrave_coef",
            "max_ceiling",
            "weapons",
            "hammers",
        }
        or value["client"] != CLIENT
        or value["free"] is not True
        or not integer(value["min_experience"], minimum=1)
        or not integer(value["required_limit_breaks"], 100, 1)
        or not integer(value["engrave_coef"], 100)
        or not integer(value["max_ceiling"], 100, 1)
        or not isinstance(value["weapons"], dict)
        or not 1 <= len(value["weapons"]) <= 30000
        or not isinstance(value["hammers"], dict)
        or not 1 <= len(value["hammers"]) <= 64
        or any(not decimal_id(k) or not integer(v, 4, 3) for k, v in value["hammers"].items())
        or set(value["weapons"]) & set(value["hammers"])
    ):
        raise ValueError("Invalid free first-engraving catalog")
    for key, spec in value["weapons"].items():
        if (
            not decimal_id(key)
            or not isinstance(spec, dict)
            or set(spec) != {"origin_rarity", "options"}
            or not integer(spec["origin_rarity"], 4, 3)
            or not isinstance(spec["options"], list)
            or not 1 <= len(spec["options"]) <= 32
            or any(not valid_option(o) for o in spec["options"])
            or len({o["OptionId"] for o in spec["options"]}) != 1
            or len({o["Level"] for o in spec["options"]}) != len(spec["options"])
        ):
            raise ValueError("Invalid eligible engraving weapon or random-option tiers")
    return value


def saved_engrave_bonus(target, references):
    """Validate saved engraving before existing option/experience handlers preserve it."""
    options = target.get("EngraveOptions")
    if options in (None, []):
        return 0
    catalog = load_catalog(references)
    spec = catalog["weapons"].get(str(target.get("ItemId")))
    if (
        not spec
        or not isinstance(options, list)
        or len(options) != 1
        or not valid_option(options[0])
        or options[0] not in spec["options"]
        or not integer(target.get("EngraveCeiling"), catalog["max_ceiling"], 1)
    ):
        raise ValueError("Saved engraving is outside the supported public option tiers")
    return catalog["engrave_coef"]


def engrave(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"TargetWeaponId", "MaterialWeaponId"}
        or any(not integer(body[k], minimum=1) for k in body)
        or body["TargetWeaponId"] == body["MaterialWeaponId"]
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid first-engraving request or identity")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    previous = account.db.execute(
        "SELECT request FROM weapon_engrave_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Engraving retry differs from the saved request")
        return {"User": profile["User"]}
    catalog = load_catalog(account.references)
    user = profile["User"]
    weapons, hammers = user.get("ItemWeapons"), user.get("ItemStackables")
    if not isinstance(weapons, list) or not isinstance(hammers, list):
        raise ValueError("Invalid saved equipment or engraving material inventory")
    targets = [r for r in weapons if isinstance(r, dict) and r.get("Id") == body["TargetWeaponId"]]
    materials = [
        r for r in hammers if isinstance(r, dict) and r.get("Id") == body["MaterialWeaponId"]
    ]
    if len(targets) != 1 or len(materials) != 1:
        raise ValueError("First engraving requires one owned target and one owned hammer stack")
    target, material = targets[0], materials[0]
    if (
        not integer(target.get("Id"), minimum=1)
        or not integer(target.get("ItemId"), minimum=1)
        or str(target["ItemId"]) not in catalog["weapons"]
        or not integer(target.get("Amount"), 1, 1)
        or not integer(target.get("Experience"), minimum=catalog["min_experience"])
        or not integer(
            target.get("LimitBreaks"),
            catalog["required_limit_breaks"],
            catalog["required_limit_breaks"],
        )
        or type(target.get("Locked")) is not bool
        or target.get("EngraveOptions") not in (None, [])
        or not integer(target.get("EngraveCeiling"), 0)
        or not integer(user.get("Cas"), MAX_REVISION - 1)
    ):
        raise ValueError("Unsupported, already engraved or ineligible target equipment/revision")
    origin = catalog["weapons"][str(target["ItemId"])]
    if (
        not integer(material.get("Id"), minimum=1)
        or not integer(material.get("ItemId"), minimum=1)
        or catalog["hammers"].get(str(material["ItemId"])) != origin["origin_rarity"]
        or not integer(material.get("Amount"), minimum=1)
        or material.get("Locked") is not False
        or not integer(material.get("Experience"), 0)
        or not integer(material.get("LimitBreaks"), 0)
    ):
        raise ValueError("Unsupported, mismatched, empty or locked engraving hammer")
    # Explicit local uniform tier roll, not an implementation of official odds.
    target["EngraveOptions"] = [dict(origin["options"][randbelow(len(origin["options"]))])]
    target["EngraveCeiling"] = 1
    user["Cas"] += 1
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO weapon_engrave_requests VALUES(?,?,?)",
            (operation_id, encoded, json.dumps(target["EngraveOptions"], separators=(",", ":"))),
        )
    # The native client derives fixed engraving options from the weapon spec.
    # No gold/material is consumed and no returned-item reward is fabricated.
    return {"User": user}
