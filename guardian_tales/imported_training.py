# SPDX-License-Identifier: Apache-2.0
"""Free owned-hero training under an explicit matching imported-account policy."""

import json

from .campaign import FIRST_STAGE_ID, STAGE_CLEARED
from .snapshots import CLIENT

MAX_INT = 0x7FFFFFFF
MAX_REVISION = 0x7FFFFFFFFFFFFFFF


def integer(value, minimum=0, maximum=MAX_INT):
    return type(value) is int and minimum <= value <= maximum


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS imported_character_training_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, targets TEXT NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / "imported_training_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Free imported training requires a matching external catalog")
    catalog = references.json(path.name)
    if not isinstance(catalog, dict) or catalog.get("client") != CLIENT:
        raise ValueError("Invalid imported training catalog client")
    levels, caps = catalog.get("experience_by_level"), catalog.get("caps")
    if (
        catalog.get("free_experience") is not True
        or not isinstance(levels, list)
        or not 2 <= len(levels) <= 1000
        or levels[0] != 0
        or any(not integer(v) for v in levels)
        or any(a >= b for a, b in zip(levels, levels[1:]))
        or not isinstance(caps, list)
        or not 1 <= len(caps) <= 1000
        or any(
            not isinstance(c, dict)
            or set(c) != {"opened_stage_id", "max_level"}
            or not integer(c["opened_stage_id"])
            or not integer(c["max_level"], 1, len(levels) - 1)
            for c in caps
        )
    ):
        raise ValueError("Invalid imported training experience table")
    for field in (
        "limit_break_coefficient",
        "blessing_coefficient",
        "myth_coefficient",
        "max_limit_breaks",
        "max_bless_level",
    ):
        if not integer(catalog.get(field), 0, 100):
            raise ValueError("Invalid imported training level modifiers")
    for field in ("character_ids", "myth_ids"):
        values = catalog.get(field)
        if (
            not isinstance(values, list)
            or len(values) > 10000
            or any(not integer(v, 1) for v in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError("Invalid imported training character catalog")
    if not catalog["character_ids"] or not set(catalog["myth_ids"]) <= set(
        catalog["character_ids"]
    ):
        raise ValueError("Invalid imported training myth variants")
    return catalog


def train(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"Experiences"}
        or not isinstance(body["Experiences"], dict)
        or not 1 <= len(body["Experiences"]) <= 32
        or any(
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or int(key) > MAX_INT
            or not integer(delta, 1)
            for key, delta in body["Experiences"].items()
        )
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 128
        or account.needs_prologue()
    ):
        raise ValueError("Invalid imported character training request or identity")
    catalog = load_catalog(account.references)
    profile = account.profile()
    user, progress, record = profile["User"], profile["UserProgress"], profile["UserRecord"]
    if not progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED:
        raise ValueError("Complete Inn before training characters")
    characters = {str(c["Id"]): c for c in user["Characters"]}
    changes = body["Experiences"]
    if len(characters) != len(user["Characters"]) or any(
        key not in characters
        or not integer(characters[key].get("CharacterId"), 1)
        or characters[key]["CharacterId"] not in catalog["character_ids"]
        or not integer(characters[key].get("Experience"))
        or not integer(characters[key].get("LimitBreaks", 0), 0, catalog["max_limit_breaks"])
        or not integer(characters[key].get("BlessLevel", 0), 0, catalog["max_bless_level"])
        for key in changes
    ):
        raise ValueError("Training requires unambiguous owned catalog heroes with valid state")
    encoded = json.dumps(changes, sort_keys=True, separators=(",", ":"))
    receipt = account.db.execute(
        "SELECT request,targets FROM imported_character_training_requests WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if receipt:
        if receipt[0] != encoded or any(
            key not in characters or characters[key]["Experience"] < target
            for key, target in json.loads(receipt[1]).items()
        ):
            raise ValueError("Training identity conflicts with its saved receipt")
        return {"User": user, "UserRecord": record}
    cap = catalog["caps"][0]["max_level"]
    for row in catalog["caps"][1:]:
        if progress["StageStates"].get(str(row["opened_stage_id"]), 0) & 1:
            cap = row["max_level"]
    targets = {}
    for key, delta in changes.items():
        hero = characters[key]
        max_level = (
            cap
            + hero.get("LimitBreaks", 0) * catalog["limit_break_coefficient"]
            + hero.get("BlessLevel", 0) * catalog["blessing_coefficient"]
            + (catalog["myth_coefficient"] if hero["CharacterId"] in catalog["myth_ids"] else 0)
        )
        target = hero["Experience"] + delta
        # Native levels are zero-based: threshold[N] reaches internal level N.
        if max_level >= len(catalog["experience_by_level"]) or not integer(
            target, 1, catalog["experience_by_level"][max_level]
        ):
            raise ValueError("Training exceeds the saved story and hero level cap")
        targets[key] = target
    applied = sum(changes.values())
    if (
        not integer(user.get("Cas"), 0, MAX_REVISION - 1)
        or not integer(record.get("Cas"), 0, MAX_REVISION - 1)
        or not integer(record.get("AddCharacterExperienceAmount"), 0, MAX_REVISION - applied)
    ):
        raise ValueError("Invalid saved training record or revision overflow")
    for key, target in targets.items():
        characters[key]["Experience"] = target
    # Count experience applied to heroes without touching the shared XP asset.
    record["AddCharacterExperienceAmount"] += applied
    record["Cas"] += 1
    user["Cas"] += 1
    with account.db:
        account.db.execute(
            "INSERT INTO imported_character_training_requests VALUES(?,?,?)",
            (operation_id, encoded, json.dumps(targets, sort_keys=True)),
        )
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
    return {"User": user, "UserRecord": record}
