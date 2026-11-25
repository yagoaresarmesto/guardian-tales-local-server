# SPDX-License-Identifier: Apache-2.0
"""Apply paid limit breaks to the selected owned hero."""

import json
from functools import lru_cache

from .characters import hero_resource, owned_character
from .hero_catalog import growth_tables
from .village import INT_MAX, MAX_REVISION, integer

ROUTE = "/user/limitbreak-character/v2"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS hero_limit_break_requests "
        "(operation_id TEXT PRIMARY KEY, character_id INTEGER NOT NULL, break_count INTEGER NOT NULL)"
    )


@lru_cache(maxsize=2)
def rules(body):
    tables = growth_tables(body)
    try:
        exp = json.loads(tables["exps2"])
        maximum = exp["Constants"]["MaxLimitBreak"]
        rows = exp["LimitBreaks"]
        if not integer(maximum, minimum=1) or len(rows) != maximum:
            raise ValueError("Invalid limit break count")
        by_step = {r["LimitBreak"]: r for r in rows}
        costs = {
            category: tuple(by_step[i]["HeroCrystalReq" + category] for i in range(maximum))
            for category in ("Normal", "Story", "Unique")
        }
        if not all(integer(cost, minimum=1) for prices in costs.values() for cost in prices):
            raise ValueError("Invalid limit break price")
        heroes = {
            h["Id"]: costs[h["SummonCategory"]]
            for h in json.loads(tables["heroes"])
            if h.get("Playable") is True
            and integer(h.get("Rank"), minimum=4)
            and h.get("SummonCategory") in costs
        }
        (crystal,) = (
            i["Id"]
            for i in json.loads(tables["items"])
            if i.get("Name") == "herocrystal" and i.get("Type") == "goods"
        )
        if not integer(crystal, minimum=1):
            raise ValueError("Invalid Hero Crystal item")
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Missing or invalid hero limit break catalog") from exc
    return heroes, crystal


def limit_break(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"CharacterId", "LimitBreakCount"}
        or not integer(body["CharacterId"], minimum=1)
        or not integer(body["LimitBreakCount"], minimum=1)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select an owned hero and a positive limit break count")
    ident, count = body["CharacterId"], body["LimitBreakCount"]
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user, record = profile["User"], profile["UserRecord"]
        prior = db.execute(
            "SELECT character_id,break_count FROM hero_limit_break_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if prior:
            if tuple(prior) != (ident, count):
                raise ValueError("Limit break identity already belongs to another request")
            return {"User": hero_resource(user, "Assets"), "UserRecord": record}
        hero = owned_character(user, ident)
        heroes, crystal = rules(account.references.read_bytes("static_data_get.bin"))
        prices = heroes.get(hero.get("CharacterId"), ())
        current = hero.get("LimitBreaks", 0)
        if not integer(current) or current + count > len(prices):
            raise ValueError("Select available limit breaks on a five-star or higher hero")
        slots = user.get("TrainingSlots", {})
        if not isinstance(slots, dict) or any(
            not isinstance(slot, dict)
            or (slot.get("CharacterId") == ident and slot.get("IsLimitBreak"))
            for slot in slots.values()
        ):
            raise ValueError("This hero has a Training Room limit break")
        total = sum(prices[current : current + count])
        balances = [row for row in user["Assets"] if row["Id"] == crystal]
        if len(balances) != 1 or not integer(balances[0].get("Amount"), minimum=total):
            raise ValueError("Insufficient Hero Crystals")
        asset = balances[0]
        if (
            not integer(asset.get("Spent"), MAX_REVISION - total)
            or not integer(record.get("LimitBreakCharacterCount", 0), INT_MAX - count)
            or not integer(user.get("Cas"), MAX_REVISION - 1)
            or not integer(record.get("Cas"), MAX_REVISION - 1)
        ):
            raise ValueError("Invalid saved limit break spending, mission count or revision")
        asset["Amount"] -= total
        asset["Spent"] += total
        hero["LimitBreaks"] = current + count
        record["LimitBreakCharacterCount"] = record.get("LimitBreakCharacterCount", 0) + count
        user["Cas"] += 1
        record["Cas"] += 1
        db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        db.execute(
            "INSERT INTO hero_limit_break_requests VALUES(?,?,?)", (operation_id, ident, count)
        )
    return {"User": hero_resource(user, "Assets"), "UserRecord": record}
