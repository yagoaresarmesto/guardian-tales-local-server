# SPDX-License-Identifier: Apache-2.0
"""Persist quest checkpoints and the validated portion of native quest results."""

import json

from .campaign import STAGE_OPENED
from .campaign_complete import campaign_test_enabled
from .characters import new_character
from .story import open_eligible_stages
from .story_data import load, stage_quest
from .story_handles import stage_handles
from .village import integer

CLEAR = "/stage/clear-quest"
SET_CUSTOM = "/stage/set-custom"
SET_QUEST_CUSTOM = "/stage/set-quest-custom-state"
ROUTES = (CLEAR, SET_CUSTOM, SET_QUEST_CUSTOM)


def custom_state(value):
    if (
        not isinstance(value, dict)
        or len(value) > 1024
        or any(
            not isinstance(key, str)
            or not 1 <= len(key) <= 200
            or not integer(v, minimum=-0x80000000)
            for key, v in value.items()
        )
    ):
        raise ValueError("Quest custom state must contain named 32-bit integer values")
    return value


def save_profile(account, profile):
    account.db.execute(
        "UPDATE local_account SET profile=? WHERE id=1",
        (json.dumps(profile, separators=(",", ":")),),
    )


def grant(account, profile, rewards):
    from .story_loot import grant_item

    user = profile["User"]
    response = {"AddedItems": [], "AddedCharacters": []}
    for reward in rewards:
        if {"ItemId", "Amount"} <= reward.keys() <= {"ItemId", "Amount", "Level"}:
            response["AddedItems"].extend(
                grant_item(
                    account, user, reward["ItemId"], reward["Amount"], reward.get("Level", 0)
                )
            )
        elif set(reward) == {"CharacterId", "Level"}:
            spec_id, level = reward["CharacterId"], reward["Level"]
            if not integer(spec_id, minimum=1) or not integer(level, minimum=1):
                raise ValueError("Invalid story quest hero reward")
            if any(row["CharacterId"] == spec_id for row in user["Characters"]):
                continue
            levels = account.references.json("training_catalog.json").get("experience_by_level")
            next_id = user["CharacterIdCounter"] + 1
            if (
                not isinstance(levels, list)
                or not 1 <= level <= len(levels)
                or not integer(levels[level - 1])
                or not integer(next_id, minimum=1)
                or any(c["Id"] >= next_id for c in user["Characters"])
            ):
                raise ValueError("Invalid experience catalog or hero counter for quest reward")
            hero = new_character(next_id, spec_id)
            hero["Experience"] = levels[level - 1]
            user["CharacterIdCounter"] = next_id
            user["Characters"].append(hero)
            response["AddedCharacters"].append({"characterId": spec_id})
        else:
            raise ValueError("This story quest uses an unsupported reward type")
    if response["AddedItems"] or response["AddedCharacters"]:
        user["Cas"] += 1
        response["User"] = user
    return response


def open_stages(progress, targets, stages):
    for stage_id in targets:
        key = str(stage_id)
        if key not in stages:
            raise ValueError("Quest refers to a stage outside the story catalog")
        old = progress["StageStates"].get(key, 0)
        progress["StageStates"][key] = old | STAGE_OPENED


def save_gimmicks(account, stage_id, custom):
    category = custom.get("Category")
    if type(category) is not int or category not in (1, 6, 7, 8, 9, 11):
        raise ValueError("Invalid story custom handle category")
    handles = stage_handles(account.references, stage_id).get(str(category), {})
    values = custom.get("CustomValues")
    if not isinstance(values, list) or not 1 <= len(values) <= len(handles):
        raise ValueError("Invalid story gimmick update")
    allowed = set(handles.values())
    updates = {}
    for row in values:
        if not isinstance(row, dict) or set(row) - {
            "KeyIndex",
            "KeyName",
            "BooleanValue",
            "IntegerValue",
        }:
            raise ValueError("Invalid story gimmick value")
        index = row.get("KeyIndex")
        name = row.get("KeyName")
        b, i = row.get("BooleanValue"), row.get("IntegerValue")
        if (
            not integer(index, minimum=1)
            or index not in allowed
            or index in updates
            or name is not None
            and (not isinstance(name, str) or handles.get(name) != index)
            or not (type(b) is bool and i is None or b is None and integer(i, minimum=-0x80000000))
        ):
            raise ValueError("Unknown or invalid story gimmick value")
        updates[index] = json.dumps(i if b is None else b)
    account.db.executemany(
        "INSERT INTO campaign_progress VALUES(?,?,?,?) "
        "ON CONFLICT(stage_id,category,key) DO UPDATE SET value=excluded.value "
        "WHERE value<>excluded.value",
        [(stage_id, category, index, value) for index, value in updates.items()],
    )


def apply_custom(account, profile, stage_id, custom, quest_id=None):
    """Apply accompanying map/quest data inside the caller's transaction."""
    if custom is None:
        return False
    if not isinstance(custom, dict) or not integer(stage_id, minimum=1):
        raise ValueError("Malformed story StageCustom")
    if account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
        stage_id,
    ):
        raise ValueError("Enter the story stage before updating its map")
    fields = {k: v for k, v in custom.items() if v is not None}
    if (
        fields.keys()
        - {
            "StageId",
            "Category",
            "CustomValues",
            "QuestId",
            "QuestCustomState",
            "HitCount",
            "Score",
            "NoDamage",
            "ClearInTime",
            "ChallengeA",
            "ChallengeB",
        }
        or "StageId" in fields
        and (type(fields["StageId"]) is not int or fields["StageId"] != stage_id)
        or any(not integer(fields[k]) for k in ("HitCount", "Score") if k in fields)
        or any(
            type(fields[k]) is not bool
            for k in ("NoDamage", "ClearInTime", "ChallengeA", "ChallengeB")
            if k in fields
        )
    ):
        raise ValueError("Invalid custom story stage data")
    if {"HitCount", "Score", "NoDamage", "ClearInTime", "ChallengeA", "ChallengeB"} & fields.keys():
        if str(stage_id) not in load(account.references)[1]:
            raise ValueError("Story telemetry requires a matching native stage definition")
    if "CustomValues" in fields or "Category" in fields:
        save_gimmicks(account, stage_id, fields)
    if "QuestId" in fields and not integer(fields["QuestId"], minimum=1):
        raise ValueError("Invalid custom quest ID")
    if "QuestCustomState" not in fields:
        return False
    target = fields.get("QuestId", quest_id)
    _, stages, quests = load(account.references)
    if not integer(target, minimum=1) or not stage_quest(stages, quests, stage_id, target):
        raise ValueError("Custom quest state must belong to this stage")
    progress = profile["UserProgress"]
    quest = next((q for q in progress["QuestProgresses"] if q["Id"] == target), None)
    if quest is None:
        raise ValueError("Start the quest before saving its variables")
    values = custom_state(fields["QuestCustomState"])
    if any(quest["CustomStates"].get(k) != v for k, v in values.items()):
        quest["CustomStates"].update(values)
        progress["Cas"] += 1
        return True
    return False


def handle(account, route, request):
    if not isinstance(request, dict) or account.needs_prologue():
        raise ValueError("Story quest requests require a completed local account")
    _, stages, quests = load(account.references)
    stage_id = request.get("StageId")
    quest_id = request.get("QuestId")
    custom = request.get("StageCustom")
    if route == SET_CUSTOM:
        if set(request) != {"StageId", "StageCustom"} or not isinstance(custom, dict):
            raise ValueError("Malformed story StageCustom request")
        profile = account.profile()
        with account.db:
            if apply_custom(account, profile, stage_id, custom):
                save_profile(account, profile)
        return {}
    if route == SET_QUEST_CUSTOM:
        if set(request) != {"QuestId", "CustomState"}:
            raise ValueError("Malformed quest custom-state request")
        values = custom_state(request["CustomState"])
    else:
        field = "Grade" if route == CLEAR else "InnerProgress"
        if (
            not {"StageId", "QuestId", field} <= request.keys()
            or request.keys() - {"StageId", "QuestId", "StageCustom", field}
            or not integer(request[field])
        ):
            raise ValueError("Malformed story quest progression request")
    if not integer(quest_id, minimum=1) or quest_id not in quests:
        raise ValueError("Unknown story quest")
    if route != SET_QUEST_CUSTOM and (
        not integer(stage_id, minimum=1)
        or not stage_quest(stages, quests, stage_id, quest_id)
        or account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone()
        != (stage_id,)
    ):
        raise ValueError("Start the configured story stage before using its quest")
    profile = account.profile()
    progress = profile["UserProgress"]
    quest = next((q for q in progress["QuestProgresses"] if q["Id"] == quest_id), None)
    if quest is None:
        raise ValueError("Start the story quest before saving its progress")
    state = quest.get("CustomStates")
    if not isinstance(state, dict):
        raise ValueError("Invalid saved story quest custom state")
    if route == SET_QUEST_CUSTOM:
        if any(state.get(key) != v for key, v in values.items()):
            state.update(values)
            progress["Cas"] += 1
            with account.db:
                save_profile(account, profile)
        return {}

    spec = quests[quest_id]
    if route == CLEAR and request["Grade"] not in (spec.get("EndingGrades") or []):
        raise ValueError("Unknown ending grade for this story quest")
    already_saved = quest["Grade"] >= 0 or (
        route != CLEAR and request["InnerProgress"] <= quest["InnerProgress"]
    )
    if already_saved:
        if (
            route == CLEAR
            and quest["Grade"] != request["Grade"]
            and not campaign_test_enabled(account.db)
        ):
            raise ValueError("Story quest was already cleared with a different grade")
        with account.db:
            if apply_custom(account, profile, stage_id, custom, quest_id):
                save_profile(account, profile)
        if route == CLEAR:
            return {"OpenedStages": [], "AddedItems": [], "AddedCharacters": []}
        return {"OpenedStages": []}
    if route == CLEAR:
        grade = request["Grade"]
        rewards = list(spec.get("CommonRewards") or [])
        grade_reward = (spec.get("AdditionalRankResources") or {}).get(str(grade))
        if grade_reward:
            rewards.append(grade_reward)
        targets = spec.get("CommonOpenStages") or []
        quest["Grade"] = grade
    else:
        checkpoint = request["InnerProgress"]
        rewards = (spec.get("ProgressRewards") or {}).get(str(checkpoint), [])
        targets = (spec.get("ProgressOpenStages") or {}).get(str(checkpoint), [])
        quest["InnerProgress"] = checkpoint

    response = grant(account, profile, rewards)
    before = {key for key, flags in progress["StageStates"].items() if flags & STAGE_OPENED}
    open_stages(progress, targets, stages)
    if not open_eligible_stages(profile, stages):
        progress["Cas"] += 1
    response["OpenedStages"] = sorted(
        int(key)
        for key, flags in progress["StageStates"].items()
        if flags & STAGE_OPENED and key not in before
    )
    with account.db:
        apply_custom(account, profile, stage_id, custom, quest_id)
        save_profile(account, profile)
    return response
