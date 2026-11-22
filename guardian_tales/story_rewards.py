# SPDX-License-Identifier: Apache-2.0
"""World map, story feature and follower milestone claims from preserved tables."""

import base64
import json
from functools import lru_cache

from .campaign import STAGE_CLEARED, STAGE_OPENED
from .guild_war_static import FEATURE_ID as GUILD_WAR_FEATURE
from .raid_static import decode, records
from .story_data import load
from .story_quests import grant, save_profile
from .village import integer

CHAPTER = "/user/claim-chapter-progress-rewards"
FOLLOWER = "/user/claim-sns-follower-rewards"
FEATURE = "/user/claim-unlock-feature-rewards"
ROUTES = (CHAPTER, FOLLOWER)


def is_story_feature(route, body):
    return route == FEATURE and isinstance(body, dict) and body.get("Feature") != GUILD_WAR_FEATURE


@lru_cache(maxsize=2)
def reward_tables(body):
    _, tables = records(decode(body))

    def table(name, default):
        return json.loads(tables[name][1]) if name in tables else default

    chapters = {
        r["StageType"] * 1000 + r["Difficulty"] * 100 + r["ChapterId"]: r["Rewards"]
        for r in table("chapterprogressreward", [])
        if r["StageType"] == 10
    }
    followers = {r["Id"]: r for r in table("followers", {}).get("Rewards", [])}
    features = {r["Id"]: r for r in table("unlockfeature", [])}
    guardian_levels = {
        r["Level"]: r["TotalExp"] - r["NeedExp"]
        for r in table("guardianlevel", {}).get("GuardianLevel", [])
    }
    return chapters, followers, features, guardian_levels


def claim(account, route, request):
    field = {CHAPTER: "ChapterCode", FEATURE: "Feature", FOLLOWER: "SnsFollowerRewardId"}[route]
    if (
        not isinstance(request, dict)
        or set(request) != {field}
        or not integer(request[field], minimum=1)
        or account.needs_prologue()
    ):
        raise ValueError("Invalid story reward claim")
    key = request[field]
    chapters, followers, features, guardian_levels = reward_tables(
        account.references.read_bytes("static_data_get.bin")
    )
    profile = account.profile()
    progress, claimed = profile["UserProgress"], profile["UserClaimedReward"]
    complete = {q["Id"] for q in progress["QuestProgresses"] if q["Grade"] >= 0}
    if route == CHAPTER:
        world, _, quests = load(account.references)
        if key not in chapters or key not in world:
            raise ValueError("No configured reward for this story chapter")
        claimed_worlds = claimed["ChapterProgress"]
        if key in claimed_worlds:
            return {"UserClaimedReward": claimed, "AddedItems": []}
        if (
            any(not progress["StageStates"].get(s, 0) & STAGE_CLEARED for s in world[key])
            or any(
                q["Id"] not in complete for q in quests.values() if q.get("Chapter") == key - 10000
            )
            or any(
                profile[k].get(str(key), {}).get("Current", -1)
                != profile[k].get(str(key), {}).get("Total")
                for k in ("PurpleCoins", "StarPieces")
            )
        ):
            raise ValueError("Complete this chapter and its collectibles before claiming")
        rewards = chapters[key]
        claimed_worlds.append(key)
    else:
        bit_field = "SnsFollower" if route == FOLLOWER else "UnlockFeature"
        bits = bytearray(base64.b64decode(claimed[bit_field] or "", validate=True))
        spec = (followers if route == FOLLOWER else features).get(key)
        if spec is None:
            raise ValueError("Unknown story reward")
        byte, bit = divmod(key, 8)
        if byte < len(bits) and bits[byte] & (1 << bit):
            return {"UserClaimedReward": claimed, "AddedItems": []}
        if route == FOLLOWER:
            eligible = len(set(progress.get("Followers", []))) >= spec["Count"]
        else:
            condition = spec["Type"]
            value = spec["Value"]["Default"]
            flags = progress["StageStates"].get(str(value), 0)
            if condition in ("StageClear", "StageOpen"):
                eligible = flags & (STAGE_CLEARED if condition == "StageClear" else STAGE_OPENED)
            elif condition == "QuestClear":
                eligible = value in complete
            elif condition == "HasItem":
                eligible = any(
                    r["ItemId"] == value and r["Amount"] > 0
                    for k in ("ItemWeapons", "ItemMiscs", "ItemStackables")
                    for r in profile["User"][k]
                )
            elif condition == "GuardianLevel":
                threshold = guardian_levels.get(value)
                eligible = (
                    threshold is not None and profile["User"]["GuardianExperience"] >= threshold
                )
            elif condition == "None":
                eligible = True
            else:
                raise ValueError("This feature is unlocked outside the story campaign")
        if not eligible:
            raise ValueError("The saved account has not reached this story reward")
        rewards = spec["Rewards"]
        bits.extend(bytes(max(0, byte + 1 - len(bits))))
        bits[byte] |= 1 << bit
        claimed[bit_field] = base64.b64encode(bits).decode("ascii")
    result = grant(account, profile, rewards or [])
    claimed["Cas"] += 1
    with account.db:
        save_profile(account, profile)
    return {"UserClaimedReward": claimed, **result}
