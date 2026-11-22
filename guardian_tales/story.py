# SPDX-License-Identifier: Apache-2.0
"""Catalog-controlled story entry; later stages keep independent saved progress."""

import json

from .campaign import (
    CHARGED_STAMINA,
    FIRST_STAGE_ID,
    FREE_GEMS,
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
    from .story_handles import catalog as native_catalog
    from .story_quests import apply_custom, save_profile
    from .story_unlocks import scripted_target

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
        live = account.db.execute(
            "SELECT stage_id FROM campaign_session WHERE id=1"
        ).fetchone() == (stage_id,)
        if live:
            changed = apply_custom(account, profile, stage_id, request.get("StageCustom"))
            name = (catalog or {}).get(str(stage_id), {}).get("name")
            destination = scripted_target(name, request.get("ExitName"), clear=False)
            if destination:
                target = native_catalog(account.references)["stage_ids"].get(destination)
                states = profile["UserProgress"]["StageStates"]
                if target and not states.get(str(target), 0) & STAGE_OPENED:
                    states[str(target)] = states.get(str(target), 0) | STAGE_OPENED
                    profile["UserProgress"]["Cas"] += 1
                    changed = True
            if changed:
                save_profile(account, profile)
        account.db.execute("DELETE FROM campaign_session WHERE id=1 AND stage_id=?", (stage_id,))
    return {
        "User": profile["User"],
        "UserProgress": profile["UserProgress"],
        "StageState": state,
        "StageProgress": account.stage_progress(stage_id),
        "AddedItems": [],
    }


def refresh_collectibles(account, profile, stage_id, *, previous_stage_state=None):
    """Recalculate chapter counts and grant each newly earned world-map star once."""
    from .challenges import grant_reward
    from .story_handles import catalog, stage_handles

    tables = catalog(account.references)
    if not tables.get("metadata"):
        return False
    chapters, stages, _ = load_native_story(account.references)
    chapter = stages[str(stage_id)]["chapter"]
    ids = [int(key) for key in chapters[chapter]]
    changed = False
    progress = profile["UserProgress"]
    # Preserve the original flags for passages and Hell challenge grading.
    grade_by_pickups = stage_id // 10000 == chapter and chapter // 100 != 102
    placeholders = ",".join("?" for _ in ids)
    saved = {}
    for st, cat, i in account.db.execute(
        "SELECT stage_id,category,key FROM campaign_progress WHERE category IN (2,3) "
        f"AND value='true' AND stage_id IN ({placeholders})",
        ids,
    ):
        saved.setdefault((st, cat), set()).add(i)
    counts = {2: [0, 0], 3: [0, 0]}
    state = progress["StageStates"].get(str(stage_id), 0)
    if previous_stage_state is None:
        previous_stage_state = state
    for st in ids:
        handles = stage_handles(account.references, st)
        for cat, (current, total) in counts.items():
            keys = set(handles.get(str(cat), {}).values())
            acquired = len(keys & saved.get((st, cat), set()))
            counts[cat] = [current + acquired, total + len(keys)]
            if grade_by_pickups and st == stage_id and acquired == len(keys):
                state |= 1 << (cat + 1)
    if state != progress["StageStates"].get(str(stage_id), 0):
        progress["StageStates"][str(stage_id)] = state
        progress["Cas"] += 1
        changed = True
    for cat, field in ((2, "PurpleCoins"), (3, "StarPieces")):
        current, total = counts[cat]
        value = {"Current": current, "Total": total}
        if profile.setdefault(field, {}).get(str(chapter)) != value:
            profile[field][str(chapter)] = value
            changed = True
    # WorldMapBackgroundUtils.StageClearNotice presents the same free-gem award
    # for each new clear, complete collectible set, or Hell challenge.
    new_stars = (state & ~previous_stage_state) & (STAGE_CLEARED | 8 | 16 | 512 | 1024)
    per_star = tables.get("constants", {}).get("GemsForStageClearGrade", 0)
    if new_stars and per_star:
        if type(per_star) is not int or not 0 < per_star <= 0x7FFFFFFF // 5:
            raise ValueError("Invalid world-map star reward")
        user = profile["User"]
        grant_reward(
            user,
            {row["Id"]: row for row in user["Assets"]},
            {
                "item_id": FREE_GEMS,
                "amount": new_stars.bit_count() * per_star,
            },
        )
        user["Cas"] += 1
        changed = True
    return changed
