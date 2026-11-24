# SPDX-License-Identifier: Apache-2.0
"""Run-local Kama-ZONE silver collection and node-clear costs."""

from . import kamazone
from .village import integer

# The retained tables specify tier bonuses but omit base victory payouts.
BASE_REWARD = {"Normal": 10, "Elite": 20, "Boss": 30}


def effect_amount(spec):
    values = spec.get("EffectValue")
    if not isinstance(values, list) or len(values) != 1 or not integer(values[0]):
        raise ValueError("Invalid Kama-ZONE silver effect value")
    return values[0]


def collect(value, amount, specs):
    if not integer(amount):
        raise ValueError("Invalid Kama-ZONE silver income")
    if amount == 0:
        return 0
    bonus = 0
    for artifact in value["artifacts"]:
        spec = specs[artifact["Id"]]
        if spec.get("EffectType") == "CoinConstant":
            amount = effect_amount(spec)
            bonus = 0
            break
        if spec.get("EffectType") == "CoinBonus":
            bonus += effect_amount(spec)
    gain = amount + bonus
    if not integer(value["silver_coin"] + gain):
        raise ValueError("Local Kama-ZONE silver coins exceed their native range")
    value["silver_coin"] += gain
    return gain


def charge_clear(value, source):
    if value["silver_coin"] and value["curses"]:
        specs = kamazone.artifact_specs(source, value["season_id"])
        loss = sum(
            effect_amount(specs[i])
            for i in value["curses"]
            if specs[i].get("EffectType") == "LoseCoinNodeClear"
        )
        value["silver_coin"] = max(0, value["silver_coin"] - loss)
