# SPDX-License-Identifier: Apache-2.0
"""Configured clear exits preserve earned progress without inventing clear rewards."""

import json
import re

from .campaign import STAGE_CLEARED, STAGE_UNLOCKED
from .story import load_story_catalog, open_eligible_stages


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


def complete_catalog_stage(account, request):
    if (
        not isinstance(request, dict)
        or type(request.get("StageId")) is not int
        or request.get("IsClearExit") is not True
        or not isinstance(request.get("ExitName"), str)
    ):
        raise ValueError("Malformed configured clear exit")
    hit_count, no_damage = completion_custom(request.get("StageCustom"))
    if not (account.references.directory / "completion_catalog.json").is_file():
        raise ValueError("No completion catalog for this stage")
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
    stage_id = request["StageId"]
    key = str(stage_id)
    row = stages.get(key)
    if row is None or row["exit_name"] != request["ExitName"]:
        raise ValueError("Unknown configured clear exit")
    profile = account.profile()
    progress = profile["UserProgress"]
    state = progress["StageStates"].get(key, 0)
    completed = account.db.execute(
        "SELECT exit_name FROM campaign_completions WHERE stage_id=?", (stage_id,)
    ).fetchone()
    if completed:
        if completed != (row["exit_name"],) or not state & STAGE_CLEARED:
            raise ValueError("Completion receipt does not match saved stage state")
    else:
        if not state & STAGE_UNLOCKED or account.db.execute(
            "SELECT stage_id FROM campaign_session WHERE id=1"
        ).fetchone() != (stage_id,):
            raise ValueError("Start the unlocked stage before completing it")
        for index in row["required_monsters"]:
            marker = account.db.execute(
                "SELECT value FROM campaign_progress WHERE stage_id=? AND category=10 AND key=?",
                (stage_id, index),
            ).fetchone()
            if marker != ("true",):
                raise ValueError("Defeat the configured encounters before completing this stage")
        progress["StageStates"][key] = state | STAGE_CLEARED
        progress["Cas"] += 1
    opened_next = open_eligible_stages(profile, load_story_catalog(account.references))
    with account.db:
        if not completed:
            account.db.execute(
                "INSERT INTO campaign_completions VALUES(?,?,?,?)",
                (stage_id, row["exit_name"], hit_count, no_damage),
            )
            account.db.execute("DELETE FROM campaign_session WHERE id=1")
        if not completed or opened_next:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {
        "User": profile["User"],
        "UserProgress": progress,
        "StageState": progress["StageStates"][key],
        "StageProgress": account.stage_progress(stage_id),
        "AddedItems": [],
    }
