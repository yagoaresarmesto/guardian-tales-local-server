# SPDX-License-Identifier: Apache-2.0
"""Shared local draw payments, including independent daily paid-gem discounts."""

import json
from datetime import datetime, timezone
from functools import lru_cache

from .raid_static import decode, records
from .village import MAX_REVISION, integer

CHARACTER_ROUTE = "/summon/character"
WEAPON_ROUTE = "/summon/weapon"
PAID_GEMS = 70002
FREE_GEMS = 70003


def validate_request(body, regular=False):
    fields = {"Count", "SummonCostType"}
    if regular:
        fields |= {"IsPickUp", "PickUpKey"}
    if (
        not isinstance(body, dict)
        or set(body) != fields
        or type(body["Count"]) is not int
        or body["Count"] not in (1, 10)
        or type(body["SummonCostType"]) is not int
        or body["SummonCostType"] not in ((0, 1, 3, 4) if regular else (0, 3, 5))
        or (regular and (body["IsPickUp"] is not False or not integer(body["PickUpKey"], 0)))
        or (body["SummonCostType"] == 1 and body["Count"] != 1)
    ):
        raise ValueError("Unsupported draw count, payment or pickup banner")


@lru_cache(maxsize=2)
def paid_prices(body):
    _, tables = records(decode(body))
    if "constants" not in tables:
        raise ValueError("Paid draws require matching external client constants")
    constants = json.loads(tables["constants"][1])
    keys = ("GemsForSummonDiscount", "GemsForSummon", "PaidGemforSummonTen")
    if not isinstance(constants, dict) or any(
        not integer(constants.get(k), 1000000, 1) for k in keys
    ):
        raise ValueError("Invalid paid summon prices")
    return tuple(constants[k] for k in keys)


def utc_now():
    return datetime.now(timezone.utc)


def pay(profile, catalog, body, references, kind):
    user, shop = profile["User"], profile["UserShop"]
    count, cost_type = body["Count"], body["SummonCostType"]
    if cost_type in (0, 1, 4):
        asset_id = FREE_GEMS if cost_type == 0 else PAID_GEMS
        rows = [a for a in user["Assets"] if isinstance(a, dict) and a.get("Id") == asset_id]
        if (
            len(rows) != 1
            or not integer(rows[0].get("Amount"))
            or not integer(rows[0].get("Spent"), MAX_REVISION)
        ):
            raise ValueError("Invalid saved summon gem balance or spending counter")
        gems = rows[0]
        cost = catalog["gem_costs"][str(count)]
        if cost_type in (1, 4):
            discount, one, ten = paid_prices(references.read_bytes("static_data_get.bin"))
            cost = discount if cost_type == 1 else one if count == 1 else ten
        if gems["Amount"] < cost or gems["Spent"] > MAX_REVISION - cost:
            raise ValueError("Not enough selected gems or spending-counter capacity")
        if cost_type == 1:
            field = "LastDiscountSummon" + kind
            timestamps = shop.get(field)
            if (
                kind not in ("Character", "Weapon")
                or not isinstance(timestamps, dict)
                or shop.get("DiscountSummonPackage") is not None
                or not integer(shop.get("Cas"), MAX_REVISION - 1)
                or not integer(shop.get("UserId"), minimum=1)
                or shop["UserId"] != user["Id"]
            ):
                raise ValueError("Unsupported daily summon shop state or discount package")
            now = utc_now().astimezone(timezone.utc)
            # API sign-in advertises StartOfDay=00:00:00 and UTC server time.
            # The native ContentToday predicate therefore resets at UTC midnight.
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if "0" in timestamps:
                try:
                    previous = datetime.fromisoformat(timestamps["0"])
                    if previous.utcoffset() is None:
                        raise ValueError("Daily summon timestamp needs a timezone")
                    previous = previous.astimezone(timezone.utc)
                except (TypeError, OverflowError) as error:
                    raise ValueError("Invalid saved daily summon timestamp") from error
                if previous >= cutoff:
                    raise ValueError("This banner's daily paid summon has already been used")
            timestamps["0"] = now.isoformat()
            shop["Cas"] += 1
        gems["Amount"] -= cost
        gems["Spent"] += cost
        return
    ticket = catalog["ticket_item_id" if cost_type == 3 else "selectable_ticket_item_id"]
    stacks = [i for i in user["ItemStackables"] if i["ItemId"] == ticket]
    if (
        any(not integer(i.get("Amount")) for i in stacks)
        or sum(i["Amount"] for i in stacks) < count
    ):
        raise ValueError("Not enough summon tickets of the selected kind")
    left, depleted = count, set()
    for item in sorted(stacks, key=lambda i: i["Id"]):
        spent = min(left, item["Amount"])
        item["Amount"] -= spent
        left -= spent
        if spent and item["Amount"] == 0:
            depleted.add(item["Id"])
    user["ItemStackables"] = [i for i in user["ItemStackables"] if i["Id"] not in depleted]
