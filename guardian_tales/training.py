# SPDX-License-Identifier: Apache-2.0
"""Catalog-driven training, with request receipts independent of experience costs."""

import json

from .campaign import FIRST_STAGE_ID, STAGE_CLEARED


def train_characters(account, request, operation_id, *, free=False):
    if (
        not isinstance(request, dict)
        or set(request) != {"Experiences"}
        or not isinstance(request["Experiences"], dict)
        or not 1 <= len(request["Experiences"]) <= 32
        or any(
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or type(value) is not int
            or not 0 < value <= 0x7FFFFFFF
            for key, value in request["Experiences"].items()
        )
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 128
    ):
        raise ValueError("Invalid character training request or request identity")
    profile = account.profile()
    user, progress, record = profile["User"], profile["UserProgress"], profile["UserRecord"]
    if (
        account.needs_prologue()
        or not progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED
    ):
        raise ValueError("Complete Inn before training characters")
    characters = {str(c["Id"]): c for c in user["Characters"]}
    changes = request["Experiences"]
    if any(
        key not in characters
        or characters[key]["CharacterId"] not in (1, 2)
        or characters[key].get("LimitBreaks", 0)
        or characters[key].get("BlessLevel", 0)
        for key in changes
    ):
        raise ValueError(
            "Training currently supports owned knights without limit breaks or blessings"
        )
    canonical = json.dumps(changes, sort_keys=True, separators=(",", ":"))
    receipt = account.db.execute(
        "SELECT request,targets FROM character_training_requests WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if receipt:
        if receipt[0] != canonical or any(
            key not in characters or characters[key]["Experience"] < target
            for key, target in json.loads(receipt[1]).items()
        ):
            raise ValueError("Training request identity conflicts with its saved receipt")
        return {"User": user, "UserRecord": record}

    catalog = account.references.json("training_catalog.json")
    if not isinstance(catalog, dict):
        raise ValueError("Invalid external training catalog")
    levels, caps = catalog.get("experience_by_level"), catalog.get("caps")
    if (
        not isinstance(levels, list)
        or not 2 <= len(levels) <= 1000
        or any(type(v) is not int or not 0 <= v <= 0x7FFFFFFF for v in levels)
        or levels[0] != 0
        or any(a >= b for a, b in zip(levels, levels[1:]))
        or not isinstance(caps, list)
        or not 1 <= len(caps) <= 1000
        or any(
            not isinstance(c, dict)
            or set(c) != {"opened_stage_id", "max_level"}
            or type(c["opened_stage_id"]) is not int
            or c["opened_stage_id"] < 0
            or type(c["max_level"]) is not int
            or not 1 <= c["max_level"] <= len(levels)
            for c in caps
        )
    ):
        raise ValueError("Invalid external training catalog")
    cap = caps[0]["max_level"]
    for row in caps[1:]:
        if progress["StageStates"].get(str(row["opened_stage_id"]), 0) & 1:
            cap = row["max_level"]
    allowed_targets = set(levels[1:cap])
    targets = {key: characters[key]["Experience"] + delta for key, delta in changes.items()}
    if any(target not in allowed_targets for target in targets.values()):
        # Recover older cost-only tutorial receipts and a completed request after
        # a fresh client session, but never treat a valid new level-up as a retry.
        previous = account.db.execute(
            "SELECT targets FROM character_training_requests WHERE request=?", (canonical,)
        ).fetchall()
        legacy = (
            changes == {"1": 37}
            and account.db.execute(
                "SELECT experience FROM first_knight_training WHERE character_id=1"
            ).fetchone()
            == (37,)
            and characters["1"]["Experience"] >= 37
        )
        if legacy or any(
            all(characters[key]["Experience"] >= value for key, value in json.loads(r[0]).items())
            for r in previous
        ):
            return {"User": user, "UserRecord": record}
        raise ValueError("Training must reach a catalog level within the saved story cap")
    spent = sum(changes.values())
    if not free:
        experience = next(a for a in user["Assets"] if a["Id"] == 70004)
        if spent > experience["Amount"]:
            raise ValueError("Insufficient experience for character training")
        experience["Amount"] -= spent
    for key, target in targets.items():
        characters[key]["Experience"] = target
    record["AddCharacterExperienceAmount"] += spent
    record["Cas"] += 1
    user["Cas"] += 1
    with account.db:
        account.db.execute(
            "INSERT INTO character_training_requests VALUES(?,?,?)",
            (operation_id, canonical, json.dumps(targets, sort_keys=True)),
        )
        if "1" in characters and characters["1"]["Experience"] >= 37:
            account.db.execute("INSERT OR IGNORE INTO first_knight_training VALUES(1,37)")
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
    return {"User": user, "UserRecord": record}
