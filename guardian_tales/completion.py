# SPDX-License-Identifier: Apache-2.0
"""Persist named and scripted clear exits, their targets and replay state."""

import json
import re

from .campaign import STAGE_CLEARED, STAGE_OPENED, STAGE_UNLOCKED
from .story import load_story_catalog, open_eligible_stages
from .story_data import load as load_native_story
from .story_handles import catalog, map_events, stage_handles


def completion_custom(custom):
    if custom is None:
        return None, None
    empty = {
        "StageId",
        "Category",
        "CustomValues",
        "QuestId",
        "QuestCustomState",
        "ClearInTime",
        "Score",
        "ChallengeA",
        "ChallengeB",
    }
    if (
        not isinstance(custom, dict)
        or set(custom) - empty - {"HitCount", "NoDamage"}
        or any(custom.get(key) is not None for key in empty)
        or (
            custom.get("HitCount") is not None
            and (type(custom["HitCount"]) is not int or not 0 <= custom["HitCount"] <= 1000000)
        )
        or (custom.get("NoDamage") is not None and type(custom["NoDamage"]) is not bool)
    ):
        raise ValueError("Unsupported stage completion custom state")
    return custom.get("HitCount"), custom.get("NoDamage")


def configured_exits(account):
    if not (account.references.directory / "completion_catalog.json").is_file():
        return {}
    value = account.references.json("completion_catalog.json")
    stages = value.get("stages") if isinstance(value, dict) else None
    if not isinstance(stages, dict) or not 1 <= len(stages) <= 1000:
        raise ValueError("Invalid external completion catalog")
    for key, row in stages.items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[1-9][0-9]{0,9}", key)
            or int(key) > 0x7FFFFFFF
            or not isinstance(row, dict)
            or set(row) != {"exit_name", "required_monsters"}
            or not isinstance(row["exit_name"], str)
            or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", row["exit_name"])
            or not isinstance(row["required_monsters"], list)
            or len(row["required_monsters"]) > 254
            or any(type(i) is not int or not 1 <= i <= 254 for i in row["required_monsters"])
            or len(set(row["required_monsters"])) != len(row["required_monsters"])
        ):
            raise ValueError("Invalid configured clear exit or monster prerequisites")
    return stages


def complete_catalog_stage(account, request):
    from .story import refresh_collectibles
    from .story_quests import apply_custom

    if (
        not isinstance(request, dict)
        or request.keys() - {"StageId", "IsClearExit", "ExitName", "StageCustom"}
        or type(request.get("StageId")) is not int
        or request.get("IsClearExit") is not True
        or request.get("ExitName") is not None
        and not isinstance(request["ExitName"], str)
    ):
        raise ValueError("Malformed configured clear exit")
    stage_id = request["StageId"]
    key = str(stage_id)
    exit_name = request.get("ExitName") or ""
    configured = configured_exits(account).get(key)
    _, native, _ = load_native_story(account.references)
    custom = request.get("StageCustom")
    if key not in native:
        if not configured:
            raise ValueError("No completion catalog for this stage")
        hit_count, no_damage = completion_custom(custom)
        catalog_stages = load_story_catalog(account.references)
        target = None
    else:
        if custom is not None and not isinstance(custom, dict):
            raise ValueError("Invalid stage completion custom state")
        metrics = custom or {}
        hit_count, no_damage = completion_custom(
            {k: metrics.get(k) for k in ("HitCount", "NoDamage")}
        )
        for field in ("ChallengeA", "ChallengeB"):
            if metrics.get(field) is not None and type(metrics[field]) is not bool:
                raise ValueError("Invalid Hell stage challenge result")
        events = map_events(account.references, stage_id)
        exits = events.get("exits", {})
        from .story_unlocks import scripted_target

        destination = scripted_target(native[key].get("name"), exit_name) or exits.get(exit_name)
        if not configured and destination is None:
            names = stage_handles(account.references, stage_id).get("7", {})
            if (
                exits
                and exit_name not in exits
                or not exits
                and (
                    exit_name
                    and exit_name not in names
                    or exit_name in events.get("inner_exits", {})
                )
            ):
                raise ValueError("Unknown story clear exit")
        target = catalog(account.references)["stage_ids"].get(destination)
        catalog_stages = native | (load_story_catalog(account.references) or {})
    if configured and configured["exit_name"] != exit_name:
        raise ValueError("Unknown configured clear exit")
    profile = account.profile()
    progress = profile["UserProgress"]
    states = progress["StageStates"]
    state = states.get(key, 0)
    completed = account.db.execute(
        "SELECT exit_name FROM campaign_completions WHERE stage_id=?", (stage_id,)
    ).fetchone()
    live = account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() == (
        stage_id,
    )
    if completed and not state & STAGE_CLEARED:
        raise ValueError("Completion receipt does not match saved stage state")
    if not state & STAGE_UNLOCKED or not live and completed != (exit_name,):
        raise ValueError("Start the unlocked stage before completing it")
    if not state & STAGE_CLEARED and configured:
        for index in configured["required_monsters"]:
            marker = account.db.execute(
                "SELECT value FROM campaign_progress WHERE stage_id=? AND category=10 AND key=?",
                (stage_id, index),
            ).fetchone()
            if marker != ("true",):
                raise ValueError("Defeat the configured encounters before completing this stage")
    hell = stage_id // 1000000 in (102, 112)
    current_score = None
    if hell:
        previous_score = account.db.execute(
            "SELECT value FROM campaign_progress WHERE stage_id=? AND category=9 AND key=0",
            (stage_id,),
        ).fetchone()
        previous_score = json.loads(previous_score[0]) if previous_score else None
        if previous_score == -1:
            previous_score = None
        current_score = (custom or {}).get("Score")
        if current_score is not None and (
            type(current_score) is not int or not 0 <= current_score <= 0x7FFFFFFF
        ):
            raise ValueError("Invalid Hell stage score")
        if current_score is None:
            current_score = previous_score if previous_score is not None else 0
    with account.db:
        if live:
            if key in native:
                apply_custom(account, profile, stage_id, custom)
            if completed is None:
                account.db.execute(
                    "INSERT INTO campaign_completions VALUES(?,?,?,?)",
                    (stage_id, exit_name, hit_count, no_damage),
                )
            elif completed != (exit_name,):
                account.db.execute(
                    "UPDATE campaign_completions SET exit_name=?,hit_count=?,no_damage=? WHERE stage_id=?",
                    (exit_name, hit_count, no_damage, stage_id),
                )
            if hell:
                if (custom or {}).get("Score") is not None and (
                    previous_score is None or current_score < previous_score
                ):
                    account.db.execute(
                        "INSERT INTO campaign_progress VALUES(?,9,0,?) ON CONFLICT(stage_id,category,key) DO UPDATE SET value=excluded.value",
                        (stage_id, json.dumps(current_score)),
                    )
                if (custom or {}).get("ChallengeA"):
                    state |= 512
                if (custom or {}).get("ChallengeB"):
                    state |= 1024
            previous = states[key]
            states[key] = state | STAGE_CLEARED
            changed = previous != states[key]
            targets = list(native.get(key, {}).get("open_substages", []))
            if target is not None:
                targets.append(target)
            for opened in targets:
                target_key = str(opened)
                if target_key in native and not states.get(target_key, 0) & STAGE_OPENED:
                    states[target_key] = states.get(target_key, 0) | STAGE_OPENED
                    changed = True
            if changed:
                progress["Cas"] += 1
            open_eligible_stages(profile, catalog_stages)
            if key in native:
                refresh_collectibles(account, profile, stage_id, previous_stage_state=previous)
            account.db.execute(
                "DELETE FROM campaign_session WHERE id=1 AND stage_id=?", (stage_id,)
            )
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {
        "User": profile["User"],
        "UserProgress": progress,
        "StageState": states[key],
        "StageProgress": account.stage_progress(stage_id),
        "AddedItems": [],
        **({"CurrentScore": current_score} if hell else {}),
    }
