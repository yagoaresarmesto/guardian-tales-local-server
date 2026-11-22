# SPDX-License-Identifier: Apache-2.0
"""Catalog-controlled story entry; later stages keep independent saved progress."""

import json

from .campaign import (
    CHARGED_STAMINA,
    FIRST_STAGE_ID,
    RESERVE_STAMINA,
    STAGE_CLEARED,
    STAGE_OPENED,
    STAGE_UNLOCKED,
)
from .story_data import load as load_native_story


def load_story_catalog(references):
    if not (references.directory / "story_catalog.json").is_file():
        return None
    value = references.json("story_catalog.json")
    stages = value.get("stages") if isinstance(value, dict) else None
    if not isinstance(stages, dict) or not 1 <= len(stages) <= 1000:
        raise ValueError("Invalid external story catalog")
    for key, row in stages.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or int(key) > 0x7FFFFFFF
            or not isinstance(row, dict)
            or not {"stamina", "requires_cleared", "quest_ids"} <= set(row)
            or set(row) - {"stamina", "requires_cleared", "quest_ids", "requires_discovery"}
            or type(row.get("requires_discovery", False)) is not bool
            or type(row["stamina"]) is not int
            or not 0 <= row["stamina"] <= 10000
        ):
            raise ValueError("Invalid story stage specification")
        for name in ("requires_cleared", "quest_ids"):
            ids = row[name]
            if (
                not isinstance(ids, list)
                or len(ids) > 1000
                or any(type(i) is not int or not 0 < i <= 0x7FFFFFFF for i in ids)
                or len(ids) != len(set(ids))
                or (name == "requires_cleared" and int(key) in ids)
            ):
                raise ValueError("Invalid story stage prerequisites or quest IDs")
    return stages


def open_eligible_stages(profile, catalog):
    if not catalog:
        return False
    progress = profile["UserProgress"]
    states = progress["StageStates"]
    cleared_quests = {row["Id"] for row in progress["QuestProgresses"] if row["Grade"] >= 0}
    changed = False
    for key, row in catalog.items():
        required = row["requires_cleared"]
        quests = row.get("requires_quests", [])
        if (
            not row.get("requires_discovery", False)
            and (required or quests)
            and all(states.get(str(i), 0) & STAGE_CLEARED for i in required)
            and cleared_quests.issuperset(quests)
        ):
            state = states.get(key, 0)
            if not state & STAGE_OPENED:
                states[key] = state | STAGE_OPENED
                changed = True
    if changed:
        progress["Cas"] += 1
    return changed


def enter_story_stage(account, request, catalog):
    if (
        not isinstance(request, dict)
        or set(request) != {"StageId"}
        or type(request["StageId"]) is not int
        or str(request["StageId"]) not in catalog
        or account.needs_prologue()
    ):
        raise ValueError(
            "Stage entry requires a completed local account and a configured story stage"
        )
    stage_id = request["StageId"]
    key = str(stage_id)
    row = catalog[key]
    profile = account.profile()
    user, progress = profile["User"], profile["UserProgress"]
    states = progress["StageStates"]
    if any(not states.get(str(i), 0) & STAGE_CLEARED for i in row["requires_cleared"]):
        raise ValueError("Complete the preceding story stage before entering this one")
    if not {q["Id"] for q in progress["QuestProgresses"] if q["Grade"] >= 0}.issuperset(
        row.get("requires_quests", [])
    ):
        raise ValueError("Complete the required story quests before entering this stage")
    state = states.get(key, 0)
    if row.get("requires_discovery", False) and not state & STAGE_OPENED:
        raise ValueError("Discover this stage's map before entering it")
    changed = False
    if not state & STAGE_UNLOCKED:
        assets = {a["Id"]: a for a in user["Assets"]}
        charged, reserve = assets[CHARGED_STAMINA], assets[RESERVE_STAMINA]
        cost = row["stamina"]
        if charged["Amount"] + reserve["Amount"] < cost:
            raise ValueError("Not enough stamina to unlock this story stage")
        from_charge = min(charged["Amount"], cost)
        for asset, amount in ((charged, from_charge), (reserve, cost - from_charge)):
            asset["Amount"] -= amount
            asset["Spent"] += amount
        states[key] = state | STAGE_OPENED | STAGE_UNLOCKED
        user["Cas"] += 1
        changed = True
    if progress["LastPlayedStageId"] != stage_id:
        progress["LastPlayedStageId"] = stage_id
        changed = True
    if changed:
        progress["Cas"] += 1
    with account.db:
        account.db.execute(
            "INSERT INTO campaign_session VALUES(1,?) ON CONFLICT(id) DO UPDATE SET stage_id=excluded.stage_id",
            (stage_id,),
        )
        if changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {
        "User": user,
        "UserProgress": progress,
        "StageProgress": account.stage_progress(stage_id),
    }


def stage_catalog_for(account, request):
    configured = load_story_catalog(account.references)
    stage_id = request.get("StageId") if isinstance(request, dict) else None
    key = str(stage_id)
    if type(stage_id) is not int or stage_id == FIRST_STAGE_ID or configured and key in configured:
        return configured
    _, native, _ = load_native_story(account.references)
    if key in native:
        return native
    return configured


def leave_story_stage(account, request):
    stage_id = request.get("StageId")
    catalog = stage_catalog_for(account, request)
    if (
        type(stage_id) is not int
        or request.keys() - {"StageId", "ExitName", "IsClearExit", "StageCustom"}
        or request.get("ExitName") is not None
        and not isinstance(request["ExitName"], str)
        or account.needs_prologue()
        or stage_id != FIRST_STAGE_ID
        and str(stage_id) not in (catalog or {})
    ):
        raise ValueError("Invalid story stage exit")
    profile = account.profile()
    state = profile["UserProgress"]["StageStates"].get(str(stage_id), 0)
    if not state & STAGE_UNLOCKED:
        raise ValueError("Start the story stage before leaving it")
    with account.db:
        account.db.execute("DELETE FROM campaign_session WHERE id=1 AND stage_id=?", (stage_id,))
    return {
        "User": profile["User"],
        "UserProgress": profile["UserProgress"],
        "StageState": state,
        "StageProgress": account.stage_progress(stage_id),
        "AddedItems": [],
    }
