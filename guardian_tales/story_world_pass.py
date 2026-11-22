# SPDX-License-Identifier: Apache-2.0
"""World Clear Pass claims from completed story quests and already owned passes."""

from .story_handles import catalog
from .story_quests import grant, save_profile
from .village import integer

ENTER = "/worldclearpass/enter"
CLAIM = "/worldclearpass/claim/v2"
CLAIM_ALL = "/worldclearpass/claim-all"
ROUTES = (ENTER, CLAIM, CLAIM_ALL)


def tier_rewards(state, tier, gold, index):
    track = "Gold" if gold else "Free"
    claimed = state[track + "RewardClaimedList"]
    if tier["Id"] in claimed:
        return []
    rewards = tier[track + "Rewards"]
    kind = tier[track + "RewardType"]
    if kind == "Custom":
        if not integer(index, len(rewards) - 1):
            raise ValueError("Select a World Clear Pass reward from the listed choices")
        rewards = [rewards[index]]
        state["SelectedCustomSlots"].append(
            dict(PartId=tier["PartId"], Level=tier["Level"], IsGold=gold, Index=index)
        )
    elif kind != "Normal" or index != -1:
        raise ValueError("Invalid World Clear Pass reward choice")
    claimed.append(tier["Id"])
    return rewards


def claim(account, route, body):
    single = route == CLAIM
    expected = (
        {"PartId", "Level", "IsGold", "Index"} if single else {"PartId", "CustomGoldRewardIndexes"}
    )
    if (
        not isinstance(body, dict)
        or set(body) != expected
        or not integer(body["PartId"], minimum=1)
    ):
        raise ValueError("Invalid World Clear Pass claim request")
    if single and (
        not integer(body["Level"], minimum=1)
        or type(body["IsGold"]) is not bool
        or not integer(body["Index"], minimum=-1)
    ):
        raise ValueError("Invalid World Clear Pass level, track or index")
    part = body["PartId"]
    spec = catalog(account.references).get("world_pass", {})
    if not any(row["Id"] == part for row in spec.get("Part", [])):
        raise ValueError("Unknown World Clear Pass part")
    tiers = [r for r in spec["Rewards"] if r["PartId"] == part]
    profile = account.profile()
    state = profile["UserWorldClearPass"]
    owns_gold = part in state["PurchasedGoldPass"]
    cleared = {q["Id"] for q in profile["UserProgress"]["QuestProgresses"] if q["Grade"] >= 0}
    rewards = []
    if single:
        tier = next((r for r in tiers if r["Level"] == body["Level"]), None)
        if (
            tier is None
            or tier["ClearQuestId"] not in cleared
            or (body["IsGold"] and not owns_gold)
        ):
            raise ValueError("World Clear Pass level or track has not been unlocked")
        rewards = tier_rewards(state, tier, body["IsGold"], body["Index"])
    else:
        choices = body["CustomGoldRewardIndexes"]
        custom = {str(r["Level"]): r for r in tiers if r["GoldRewardType"] == "Custom"}
        if (
            not isinstance(choices, dict)
            or any(
                k not in custom or not integer(v, len(custom[k]["GoldRewards"]) - 1)
                for k, v in choices.items()
            )
            or (choices and not owns_gold)
        ):
            raise ValueError("Invalid World Clear Pass gold reward selections")
        for tier in tiers:
            if tier["ClearQuestId"] not in cleared:
                continue
            if tier["FreeRewardType"] == "Normal":
                rewards.extend(tier_rewards(state, tier, False, -1))
            level = str(tier["Level"])
            if owns_gold and (tier["GoldRewardType"] == "Normal" or level in choices):
                rewards.extend(tier_rewards(state, tier, True, choices.get(level, -1)))
    # Pass tables use zero for a newly recruited level-one hero.
    rewards = [
        dict(r, Level=1) if r.get("CharacterId") and r.get("Level") == 0 else r for r in rewards
    ]
    result = grant(account, profile, rewards)
    if result["AddedCharacters"]:
        new_ids = {r["characterId"] for r in result["AddedCharacters"]}
        result["AddedCharacters"] = [
            {"CharacterId": c["CharacterId"], "Experience": c["Experience"]}
            for c in profile["User"]["Characters"]
            if c["CharacterId"] in new_ids
        ]
    if rewards:
        state["Cas"] += 1
        save_profile(account, profile)
    result["UserWorldClearPass"] = state
    return result


def handle(account, route, body):
    if route == ENTER:
        if body not in (None, {}):
            raise ValueError("World Clear Pass entry takes no parameters")
        return {"UserWorldClearPass": account.profile()["UserWorldClearPass"]}
    if route not in (CLAIM, CLAIM_ALL):
        raise ValueError("Unknown World Clear Pass action")
    account.db.execute("SAVEPOINT world_clear_pass")
    try:
        result = claim(account, route, body)
        account.db.execute("RELEASE world_clear_pass")
    except BaseException:
        account.db.execute("ROLLBACK TO world_clear_pass")
        account.db.execute("RELEASE world_clear_pass")
        raise
    return result
