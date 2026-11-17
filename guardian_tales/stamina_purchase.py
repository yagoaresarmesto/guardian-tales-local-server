# SPDX-License-Identifier: Apache-2.0
"""Catalog-priced free-gem stamina purchases with daily limits and request receipts."""

import json
from datetime import datetime, timedelta, timezone

from .campaign import FREE_GEMS, RESERVE_STAMINA


def integer(value, minimum, maximum=0x7FFFFFFF):
    return type(value) is int and minimum <= value <= maximum


def load_purchase_catalog(references):
    if not (references.directory / "stamina_purchase_catalog.json").is_file():
        raise ValueError("A matching stamina-purchase catalog is required")
    value = references.json("stamina_purchase_catalog.json")
    if (
        not isinstance(value, dict)
        or set(value) != {"amount_per_charge", "gem_prices", "max_storage", "daily_limit"}
        or not integer(value["amount_per_charge"], 1, 1000000)
        or not integer(value["max_storage"], 1)
        or value["amount_per_charge"] > value["max_storage"]
        or not integer(value["daily_limit"], 1, 1000)
        or not isinstance(value["gem_prices"], list)
        or not 1 <= len(value["gem_prices"]) <= 1000
        or any(not integer(v, 1, 1000000) for v in value["gem_prices"])
    ):
        raise ValueError("Invalid stamina-purchase catalog")
    return value


def purchase_stamina(account, request, operation_id, now=None):
    if (
        not isinstance(request, dict)
        or set(request) != {"Count"}
        or not integer(request["Count"], 1, 1000)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid stamina purchase or request identity")
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
    receipt = account.db.execute(
        "SELECT request FROM stamina_gem_purchase_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if receipt:
        if receipt[0] != encoded:
            raise ValueError("Stamina request identity was already used for another purchase")
        return {"User": account.profile()["User"]}

    catalog = load_purchase_catalog(account.references)
    now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Stamina purchase clock must have a timezone")
    now = now.astimezone(timezone.utc)
    profile = account.profile()
    user = profile["User"]
    ticket = user["StaminaGemChargeTicket"]
    if (
        not isinstance(ticket, dict)
        or type(ticket.get("Type")) is not int
        or ticket["Type"] != 9
        or not integer(ticket.get("PlayCount"), 0)
        or not integer(ticket.get("RefillCount"), 0)
        or ticket.get("NextCharge") is not None
        or ticket.get("PlayLimitUpgradeExpireTime") is not None
    ):
        raise ValueError("Unsupported stamina purchase counter")
    reset = ticket.get("NextDailyReset")
    if reset is not None:
        if not isinstance(reset, str):
            raise ValueError("Invalid stamina purchase reset time")
        reset = datetime.fromisoformat(reset)
        if reset.utcoffset() is None:
            raise ValueError("Stamina purchase reset time must have a timezone")
        reset = reset.astimezone(timezone.utc)
    used = ticket["PlayCount"]
    if reset is None:
        if used or ticket["RefillCount"]:
            raise ValueError("A used stamina purchase counter needs a reset time")
    elif now >= reset:
        used = 0
    elif ticket["RefillCount"]:
        raise ValueError("Stamina purchase counter refills are unsupported")
    count = request["Count"]
    if used + count > catalog["daily_limit"]:
        raise ValueError("Daily stamina purchase limit exceeded")

    assets = {a["Id"]: a for a in user["Assets"]}
    if FREE_GEMS not in assets or RESERVE_STAMINA not in assets:
        raise ValueError("The saved account is missing stamina purchase assets")
    gems, stamina = assets[FREE_GEMS], assets[RESERVE_STAMINA]
    if any(not integer(a.get(k), 0) for a in (gems, stamina) for k in ("Amount", "Spent")):
        raise ValueError("Invalid saved stamina purchase balances")
    prices = catalog["gem_prices"]
    cost = sum(prices[min(i, len(prices) - 1)] for i in range(used, used + count))
    amount = count * catalog["amount_per_charge"]
    if gems["Amount"] < cost:
        raise ValueError("Not enough free gems for this stamina purchase")
    if gems["Spent"] + cost > 0x7FFFFFFF:
        raise ValueError("Stamina purchase spending counter overflow")
    if stamina["Amount"] + amount > catalog["max_storage"]:
        raise ValueError("Stamina storage limit exceeded")

    next_reset = (
        now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    ).isoformat()
    gems["Amount"] -= cost
    gems["Spent"] += cost
    stamina["Amount"] += amount
    ticket.update(PlayCount=used + count, RefillCount=0, NextDailyReset=next_reset)
    user["Cas"] += 1
    purchase = {
        "Count": count,
        "GemCost": cost,
        "StaminaAmount": amount,
        "PlayCountBefore": used,
        "PlayCountAfter": used + count,
        "NextDailyReset": next_reset,
    }
    with account.db:
        account.db.execute(
            "INSERT INTO stamina_gem_purchase_requests VALUES(?,?,?,?)",
            (operation_id, encoded, json.dumps(purchase, separators=(",", ":")), now.isoformat()),
        )
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
    return {"User": user}
