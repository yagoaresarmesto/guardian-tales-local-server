# SPDX-License-Identifier: Apache-2.0
"""Seasonal artifact offers for a local Kama-ZONE battle victory."""

import math
import random

from guardian_tales.settlement.village import integer


def pools(mode, season, combat):
    constants = mode.get("Constants", {})
    if not any("BattleLootWeights" + kind in constants for kind in combat):
        return {}
    allowed = set(season["Artifacts"]) - set(season.get("ArtifactsException", []))
    rarities = {}
    for row in mode["Artifacts"]:
        if row["Id"] in allowed and row.get("Kind") == "Normal" and row.get("Lootable") is True:
            rarity = row.get("Rarity")
            if not integer(rarity):
                raise ValueError("Invalid seasonal battle artifact rarity")
            rarities.setdefault(rarity, []).append(row["Id"])
    result = {}
    for kind in combat:
        weights = constants.get("BattleLootWeights" + kind)
        if not isinstance(weights, list) or any(
            type(w) not in (float, int) or not math.isfinite(w) or w < 0 for w in weights
        ):
            raise ValueError("Invalid Kama-ZONE battle loot weights")
        result[kind] = [
            (weights[r], tuple(sorted(set(ids))))
            for r, ids in sorted(rarities.items())
            if r < len(weights) and weights[r] > 0
        ]
        if not result[kind]:
            raise ValueError("No eligible seasonal battle artifacts for " + kind)
    return result


def offer(pools, value, node):
    # Use an independent stream so rewards cannot change existing map rolls.
    seed = f"kamazone-battle-loot-v1:{value['season_id']}:{value['seed']}:{value['floor']}:{node['Id']}"
    rng = random.Random(seed)
    groups = [(weight, list(ids)) for weight, ids in pools.get(node["Type"], ())]
    choices = []
    while groups and len(choices) < 3:
        group = rng.choices(groups, weights=[w for w, _ in groups])[0]
        _, ids = group
        choices.append(ids.pop(rng.randrange(len(ids))))
        if not ids:
            groups.remove(group)
    return choices
