# SPDX-License-Identifier: Apache-2.0
"""Tetis daily sweeps and past-season coin exchange in the local account transaction."""

import random
from bisect import bisect_right
from datetime import datetime, timedelta, timezone

from guardian_tales.campaigns.story_quests import grant
from guardian_tales.settlement.village import INT_MAX, integer
from guardian_tales.summons.summon_payment import spend_gems

GOLD = 70001
RNG = random.SystemRandom()


def counter(state, catalog, now=None):
    now = now or datetime.now(timezone.utc)
    if isinstance(now, str):
        now = datetime.fromisoformat(now)
    midnight = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    next_reset = (midnight + timedelta(days=1)).isoformat()
    saved = state.get("sweepCounter", {})
    if saved.get("NextDailyReset") == next_reset:
        return saved.copy()
    return dict(
        Type=14,
        PlayCount=0,
        RefillCount=0,
        NextCharge=None,
        NextDailyReset=next_reset,
        PlayLimitUpgradeExpireTime=None,
    )


def _reward_floor(state, catalog):
    floors = state["floors"]
    if not floors.get("1"):
        raise ValueError("Clear the first Tetis story floor before sweeping.")
    floor = floors[str(catalog.current)]
    if not floor:
        cleared_stories = [
            s for s in catalog.seasons if floors[str(s)] >= catalog.data["Constants"]["MaxFloor"]
        ]
        floor = floors[str(max(cleared_stories, default=1))]
    rewards = [
        row
        for row in catalog.data["SweepRewards"]
        if row["SeasonId"] == catalog.current and row["Floor"] <= floor
    ]
    if not rewards:
        raise ValueError("No Tetis sweep reward is available for the cleared floor.")
    return max(rewards, key=lambda row: row["Floor"])


def _draw_rewards(table):
    candidate = table["Candidate"]
    groups = [candidate] * RNG.randint(candidate["MinCount"], candidate["MaxCount"])
    for group in groups + table["CandidateSet"]:
        options = group["Items"]
        outcome = RNG.choices(options, weights=[row["Probability"] for row in options])[0]
        if "Item" in outcome:
            yield outcome["Item"]


def sweep(account, profile, state, catalog, count, now=None):
    spec = catalog.sweep_counter
    if not spec or not integer(count, minimum=1, maximum=spec["PlayLimit"] + spec["RefillLimit"]):
        raise ValueError("Invalid Tetis sweep count.")
    current = counter(state, catalog, now)
    free = min(count, spec["PlayLimit"] - current["PlayCount"])
    extra = count - free
    if extra + current["RefillCount"] > spec["RefillLimit"]:
        raise ValueError("The daily Tetis sweep limit has been reached.")
    reward = _reward_floor(state, catalog)
    if extra:
        # The sweep popup quotes a fixed gem price per additional run.
        spend_gems(profile["User"], extra * spec["RefillCost"][0], max_spent=INT_MAX)
    drops = []
    artifact_ids = []
    data = state["seasonData"][str(catalog.current)]
    artifacts = list(catalog.artifacts)
    bounds = catalog.artifact_bounds
    if artifacts:
        weights = catalog.data["Constants"]["ArtifactDropWeight"]
        tactic_level = catalog.level_for(data["Exp"])
        band = min(bisect_right(bounds, tactic_level) - 1, len(weights) - 1)
    for _ in range(count):
        drops.extend(_draw_rewards(reward["SweepRewards"]))
        if artifacts and RNG.random() < catalog.data["Constants"]["SeasonArtifactDropRate"]:
            ident = RNG.choice(artifacts)
            key = str(ident)
            bucket = RNG.choices(range(len(bounds) - 1), weights=weights[band])[0]
            rolled = RNG.randrange(bounds[bucket], bounds[bucket + 1])
            data["Artifacts"][key] = max(data["Artifacts"].get(key, 0), rolled)
            artifact_ids.append(ident)
    added = grant(account, profile, drops)["AddedItems"]
    gain = min(reward["PointReward"] * count, catalog.max_experience - data["Exp"])
    data["Exp"] += gain
    current["PlayCount"] += free
    current["RefillCount"] += extra
    state["sweepCounter"] = current
    return {"AddedItems": added, "Exp": gain, "ArtifactIds": artifact_ids, "SweepCounter": current}


def exchange(account, profile, state, catalog):
    expired = {s["SeasonCoin"] for k, s in catalog.seasons.items() if k < catalog.current}
    exchanged = {}
    for row in profile["User"]["Assets"]:
        ident = row["Id"]
        if ident in expired and row["Amount"] > 0:
            if not integer(row["Spent"], maximum=0x7FFFFFFF - row["Amount"]):
                raise ValueError("Invalid Tetis coin spending counter.")
            exchanged[str(ident)] = row["Amount"]
            row["Spent"] += row["Amount"]
            row["Amount"] = 0
    gold = sum(exchanged.values()) * catalog.data["Constants"]["SeasonCoinExchangeMagnification"]
    added = (
        grant(account, profile, [{"ItemId": GOLD, "Amount": gold}])["AddedItems"] if gold else []
    )
    return {"ExchangeItems": exchanged, "AddedItems": added}
