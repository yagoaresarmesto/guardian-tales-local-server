# SPDX-License-Identifier: Apache-2.0
"""Pay for a hero upgrade using the selected Dream currency and personal stones."""

from .summon_payment import spend_tickets as spend_stackables
from .village import MAX_REVISION, integer


def spend_hero_stones(user, dream, budget, stone, rate, cost):
    dream_count = min(budget, (cost + rate - 1) // rate)
    if dream_count:
        balances = [a for a in user["Assets"] if a["Id"] == dream]
        if len(balances) != 1 or not integer(balances[0].get("Amount"), minimum=dream_count):
            raise ValueError("Insufficient Dream Stones for this upgrade")
        asset = balances[0]
        if not integer(asset.get("Spent"), MAX_REVISION - dream_count):
            raise ValueError("Invalid saved Dream Stone spending counter")
        asset["Amount"] -= dream_count
        asset["Spent"] += dream_count
    remainder = cost - dream_count * rate
    if remainder > 0:
        spend_stackables(user, stone, remainder)
