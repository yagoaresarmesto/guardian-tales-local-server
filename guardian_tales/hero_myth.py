# SPDX-License-Identifier: Apache-2.0
"""Promote an eligible owned hero to its regional Myth form."""

import json
from functools import lru_cache

from .characters import hero_resource, owned_character
from .hero_catalog import growth_tables
from .hero_stones import spend_hero_stones
from .village import INT_MAX, MAX_REVISION, integer

ROUTE = "/user/myth-character/v2"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS hero_myth_requests "
        "(operation_id TEXT PRIMARY KEY, character_id INTEGER NOT NULL, dream_budget INTEGER NOT NULL)"
    )


@lru_cache(maxsize=2)
def rules(body):
    tables = growth_tables(body)
    try:
        constants = json.loads(tables["constants"])
        rank = constants["MythCharacterRank"]
        rate = constants["DreamMythStoneExchangeRate"]
        exp = json.loads(tables["exps2"])
        maximum = exp["Constants"]["MaxLimitBreak"]
        items = json.loads(tables["items"])
        (dream,) = (
            i["Id"]
            for i in items
            if i.get("Type") == "goods" and i.get("Name") == "dream_mythstone"
        )
        if not all(integer(n, minimum=1) for n in (rank, rate, maximum, dream)):
            raise ValueError("Invalid Myth requirements")
        stones = {
            i["Id"]
            for i in items
            if i.get("Type") == "evolve_stone" and i.get("StoneType") == "HeroMyth"
        }
        prices = {}
        for row in exp["MythCosts"]:
            if row["Rank"] == rank:
                category, cost = row["SummonCategory"], row["MythStoneCount"]
                if category in prices or not integer(cost, minimum=1):
                    raise ValueError("Invalid Myth stone price")
                prices[category] = cost
        heroes = {h["Id"]: h for h in json.loads(tables["heroes"]) if h.get("Playable") is True}
        forms = {}
        for ident, source in heroes.items():
            link = source.get("MythTo") or {}
            target_id = link.get("KakaoGlobal", link.get("Default"))
            if not target_id:
                continue
            target = heroes.get(target_id)
            category, stone = source["SummonCategory"], source["MythStoneId"]
            if (
                not target
                or target["Rank"] != rank
                or source["Rank"] >= rank
                or target["OriginId"] != source["OriginId"]
                or target["SummonCategory"] != category
                or stone not in stones
                or category not in prices
            ):
                raise ValueError("Invalid regional Myth form or stone")
            forms[ident] = (target_id, stone, prices[category])
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid official hero Myth catalog") from exc
    return forms, maximum, dream, rate


def promote(account, body, operation_id, *, free=False):
    if (
        not isinstance(body, dict)
        or set(body) != {"CharacterId", "DreamMythStoneUsageAmount"}
        or not integer(body["CharacterId"], minimum=1)
        or not integer(body["DreamMythStoneUsageAmount"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select an owned hero and a Dream Myth Stone amount")
    ident, budget = body["CharacterId"], body["DreamMythStoneUsageAmount"]
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user, record = profile["User"], profile["UserRecord"]
        previous = db.execute(
            "SELECT character_id,dream_budget FROM hero_myth_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if previous:
            if tuple(previous) != (ident, budget):
                raise ValueError("Myth identity already belongs to another request")
            return {"User": hero_resource(user, "Assets", "ItemStackables"), "UserRecord": record}
        hero = owned_character(user, ident)
        forms, maximum, dream, rate = rules(account.references.read_bytes("static_data_get.bin"))
        form = forms.get(hero.get("CharacterId"))
        if form is None:
            raise ValueError("This hero's current form has no official Myth upgrade")
        if not integer(hero.get("LimitBreaks"), maximum, maximum):
            raise ValueError("Complete this hero's limit breaks before Myth")
        slots = user.get("TrainingSlots", {})
        if not isinstance(slots, dict) or any(
            not isinstance(slot, dict) or slot.get("CharacterId") == ident
            for slot in slots.values()
        ):
            raise ValueError("Remove the hero from the Training Room before Myth")
        if record.get("Misc") is None:
            record["Misc"] = {}
        misc = record["Misc"]
        if (
            not isinstance(misc, dict)
            or not integer(misc.get("MythCharacterCount", 0), INT_MAX - 1)
            or not integer(user.get("Cas"), MAX_REVISION - 1)
            or not integer(record.get("Cas"), MAX_REVISION - 1)
        ):
            raise ValueError("Invalid saved Myth count or revision")
        target, stone, cost = form
        if not free:
            spend_hero_stones(user, dream, budget, stone, rate, cost)
        hero.update(CharacterId=target, RankUpgrade=0)
        misc["MythCharacterCount"] = misc.get("MythCharacterCount", 0) + 1
        user["Cas"] += 1
        record["Cas"] += 1
        db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        db.execute("INSERT INTO hero_myth_requests VALUES(?,?,?)", (operation_id, ident, budget))
    return {"User": hero_resource(user, "Assets", "ItemStackables"), "UserRecord": record}
