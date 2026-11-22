# SPDX-License-Identifier: Apache-2.0
"""Persist quest checkpoints and the validated portion of native quest results."""

import json

from .campaign import STAGE_OPENED
from .challenges import grant_reward
from .characters import new_character
from .story import open_eligible_stages
from .story_data import load
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


def stage_custom(value, stage_id, quest_id=None):
    if value is None:
        return {}
    if (
        not isinstance(value, dict)
        or value.get("StageId") not in (None, stage_id)
        or value.get("QuestId") not in (None, quest_id)
        or any(
            v is not None
            for key, v in value.items()
            if key not in {"StageId", "QuestId", "QuestCustomState"}
        )
    ):
        raise ValueError("Only quest custom state is supported in story StageCustom")
    values = value.get("QuestCustomState")
    return custom_state(values) if values is not None else {}


def commit(account, profile):
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )


def grant(account, profile, rewards):
    user = profile["User"]
    assets = {row["Id"]: row for row in user["Assets"]}
    response = {"AddedItems": [], "AddedCharacters": []}
    for reward in rewards:
        if (
            set(reward) == {"ItemId", "Amount"}
            and integer(reward["ItemId"], minimum=1)
            and integer(reward["Amount"], minimum=1)
            and reward["ItemId"] in assets
        ):
            response["AddedItems"].append(
                grant_reward(
                    user, assets, {"item_id": reward["ItemId"], "amount": reward["Amount"]}
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
    if (
        not integer(stage_id, minimum=1)
        or type(custom.get("Category")) is not int
        or custom["Category"] != 1
        or custom.get("StageId") not in (None, stage_id)
        or any(
            v is not None
            for key, v in custom.items()
            if key not in {"StageId", "Category", "CustomValues"}
        )
        or account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone()
        != (stage_id,)
    ):
        raise ValueError(
            "Named stage custom values require an active story stage and gimmick store"
        )
    handles = stage_handles(account.references, stage_id).get("1", {})
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
    with account.db:
        account.db.executemany(
            "INSERT INTO campaign_progress VALUES(?,1,?,?) "
            "ON CONFLICT(stage_id,category,key) DO UPDATE SET value=excluded.value "
            "WHERE value<>excluded.value",
            [(stage_id, index, value) for index, value in updates.items()],
        )
    return {}


def handle(account, route, request):
    if not isinstance(request, dict) or account.needs_prologue():
        raise ValueError("Story quest requests require a completed local account")
    _, stages, quests = load(account.references)
    stage_id = request.get("StageId")
    quest_id = request.get("QuestId")
    values = {}
    if route == SET_CUSTOM:
        if set(request) != {"StageId", "StageCustom"} or not isinstance(
            request["StageCustom"], dict
        ):
            raise ValueError("Malformed story StageCustom request")
        if request["StageCustom"].get("CustomValues") is not None:
            return save_gimmicks(account, stage_id, request["StageCustom"])
        quest_id = request["StageCustom"].get("QuestId")
        values = stage_custom(request["StageCustom"], stage_id, quest_id)
    elif route == SET_QUEST_CUSTOM:
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
        values = stage_custom(request.get("StageCustom"), stage_id, quest_id)
    if not integer(quest_id, minimum=1) or quest_id not in quests:
        raise ValueError("Unknown story quest")
    if route != SET_QUEST_CUSTOM and (
        not integer(stage_id, minimum=1)
        or quest_id not in stages.get(str(stage_id), {}).get("quest_ids", [])
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
    if route in (SET_CUSTOM, SET_QUEST_CUSTOM):
        if any(state.get(key) != v for key, v in values.items()):
            state.update(values)
            progress["Cas"] += 1
            commit(account, profile)
        return {}

    spec = quests[quest_id]
    if route == CLEAR:
        grade = request["Grade"]
        if grade not in (spec.get("EndingGrades") or []):
            raise ValueError("Unknown ending grade for this story quest")
        if quest["Grade"] >= 0:
            if quest["Grade"] != grade:
                raise ValueError("Story quest was already cleared with a different grade")
            return {"OpenedStages": [], "AddedItems": [], "AddedCharacters": []}
        rewards = list(spec.get("CommonRewards") or [])
        grade_reward = (spec.get("AdditionalRankResources") or {}).get(str(grade))
        if grade_reward:
            rewards.append(grade_reward)
        targets = spec.get("CommonOpenStages") or []
        quest["Grade"] = grade
    else:
        checkpoint = request["InnerProgress"]
        if quest["Grade"] >= 0 or checkpoint <= quest["InnerProgress"]:
            return {"OpenedStages": []}
        rewards = (spec.get("ProgressRewards") or {}).get(str(checkpoint), [])
        targets = (spec.get("ProgressOpenStages") or {}).get(str(checkpoint), [])
        quest["InnerProgress"] = checkpoint

    state.update(values)
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
    commit(account, profile)
    return response
