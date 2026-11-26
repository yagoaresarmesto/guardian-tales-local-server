# SPDX-License-Identifier: Apache-2.0
"""Catalog-backed defeated handles with stage-local, atomic reward deduplication."""

import json
import re

from .campaign import FIRST_MONSTER_EXP, FIRST_MONSTER_GOLD, FIRST_MONSTERS, FIRST_STAGE_ID
from .story_handles import stage_handles
from .story_quests import apply_custom


def stage_monsters(references, stage_id):
    if stage_id == FIRST_STAGE_ID:
        return {
            name: {"index": index, "experience": FIRST_MONSTER_EXP, "gold": FIRST_MONSTER_GOLD}
            for name, index in FIRST_MONSTERS.items()
        }
    if not (references.directory / "monster_catalog.json").is_file():
        return public_monsters(references, stage_id)
    value = references.json("monster_catalog.json")
    stages = value.get("stages") if isinstance(value, dict) else None
    if not isinstance(stages, dict) or not 1 <= len(stages) <= 1000:
        raise ValueError("Invalid external monster catalog")
    for key, handles in stages.items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[1-9][0-9]{0,9}", key)
            or int(key) > 0x7FFFFFFF
            or not isinstance(handles, dict)
            or not 1 <= len(handles) <= 254
        ):
            raise ValueError("Invalid monster stage definition")
        indices = set()
        for name, row in handles.items():
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", name)
                or not isinstance(row, dict)
                or set(row) != {"index", "experience", "gold"}
                or type(row["index"]) is not int
                or not 1 <= row["index"] <= 254
                or row["index"] in indices
                or any(
                    type(row[k]) is not int or not 0 <= row[k] <= 1000000
                    for k in ("experience", "gold")
                )
            ):
                raise ValueError("Invalid monster handle or local reward rule")
            indices.add(row["index"])
    if str(stage_id) not in stages:
        return public_monsters(references, stage_id)
    return stages[str(stage_id)]


def public_monsters(references, stage_id):
    return {
        name: {"index": index, "experience": 0, "gold": 0}
        for name, index in stage_handles(references, stage_id).get("10", {}).items()
    }


def record_defeated_monsters(account, request):
    if (
        not isinstance(request, dict)
        or type(request.get("StageId")) is not int
        or not isinstance(request.get("MonsterHandleNames"), list)
    ):
        raise ValueError("Malformed defeated-monster report")
    stage_id = request["StageId"]
    catalog = stage_monsters(account.references, stage_id)
    names = request["MonsterHandleNames"]
    if not 1 <= len(names) <= len(catalog) or any(
        not isinstance(name, str) or name not in catalog for name in names
    ):
        raise ValueError("Unknown defeated-monster handle")
    if account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
        stage_id,
    ):
        raise ValueError("Start the stage before reporting defeated monsters")
    profile = account.profile()
    user = profile["User"]
    exp = gold = 0
    with account.db:
        custom_changed = apply_custom(account, profile, stage_id, request.get("StageCustom"))
        added = False
        for name in sorted(set(names)):
            row = catalog[name]
            inserted = account.db.execute(
                "INSERT OR IGNORE INTO campaign_progress VALUES(?,?,?,?)",
                (stage_id, 10, row["index"], "true"),
            ).rowcount
            if inserted:
                added = True
                exp += row["experience"]
                gold += row["gold"]
        if added:
            assets = {asset["Id"]: asset for asset in user["Assets"]}
            assets[70004]["Amount"] += exp
            assets[70001]["Amount"] += gold
            user["Cas"] += 1
        if added or custom_changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"User": user, "DropExp": exp, "DropGold": gold}
