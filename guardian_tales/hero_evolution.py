# SPDX-License-Identifier: Apache-2.0
"""Advance an owned hero through its catalog evolution steps."""

import json
from functools import lru_cache

from .characters import owned_character
from .raid_static import decode, records
from .summon_payment import spend_tickets as spend_stackables
from .village import INT_MAX, MAX_REVISION, integer

ROUTE = "/user/evolve-character/v2"
RATE_KEYS = {
    "Unique": "DreamSpiritStoneExchangeRate",
    "Story": "DreamSpiritStoneStoryExchangeRate",
    "Normal": "DreamSpiritStoneNormalExchangeRate",
}


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS hero_evolution_requests "
        "(operation_id TEXT PRIMARY KEY, character_id INTEGER NOT NULL, "
        "upgrade_count INTEGER NOT NULL, dream_budget INTEGER NOT NULL)"
    )


@lru_cache(maxsize=2)
def rules(body):
    tables = records(decode(body))[1]
    try:
        heroes = {h["Id"]: h for h in json.loads(tables["heroes"][1]) if h.get("Playable") is True}
        items = json.loads(tables["items"][1])
        stones = {i["Id"] for i in items if i.get("Type") == "evolve_stone"}
        (dream,) = (
            i["Id"]
            for i in items
            if i.get("Name") == "dream_spiritstone" and i.get("Type") == "goods"
        )
        constants = json.loads(tables["constants"][1])
        rates = {category: constants[key] for category, key in RATE_KEYS.items()}
        if not integer(dream, minimum=1) or not all(
            integer(rate, minimum=1) for rate in rates.values()
        ):
            raise ValueError("Invalid Dream Evolution Stone rules")
        forms = {}
        for ident, hero in heroes.items():
            target = heroes.get(hero.get("EvolveTo"))
            rate = rates.get(hero.get("SummonCategory"))
            if (
                target
                and rate
                and hero.get("EvolvingStoneId") in stones
                and target["OriginId"] == hero["OriginId"]
                and target["Rank"] == hero["Rank"] + 1
            ):
                forms[ident] = (hero["Rank"], target["Id"], hero["EvolvingStoneId"], rate)
        steps = {}
        for row in json.loads(tables["exps2"][1])["Evolves"]:
            rank_steps = steps.setdefault(row["Rank"], {})
            if (
                row["Upgrade"] in rank_steps
                or not integer(row["UpgradeCost"])
                or type(row["IsEvolve"]) is not bool
            ):
                raise ValueError("Invalid evolution step")
            rank_steps[row["Upgrade"]] = (row["UpgradeCost"], row["IsEvolve"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Missing or invalid hero evolution catalog") from exc
    return forms, steps, dream


def price(steps, current, count):
    if not integer(current) or current + count > len(steps):
        raise ValueError("Too many evolution steps for this rank")
    total = 0
    for index in range(current, current + count):
        cost, evolves = steps.get(index, (0, False))
        if cost <= 0 or (evolves and index != current + count - 1):
            raise ValueError("No such evolution step at this rank")
        total += cost
    return total, evolves


def pay(user, dream, budget, stone, rate, cost):
    dream_count = min(budget, (cost + rate - 1) // rate)
    if dream_count:
        balances = [a for a in user["Assets"] if a["Id"] == dream]
        if len(balances) != 1 or not integer(balances[0].get("Amount"), minimum=dream_count):
            raise ValueError("Insufficient Dream Evolution Stones")
        asset = balances[0]
        if not integer(asset.get("Spent"), MAX_REVISION - dream_count):
            raise ValueError("Invalid saved Dream Evolution Stone spending counter")
        asset["Amount"] -= dream_count
        asset["Spent"] += dream_count
    remainder = cost - dream_count * rate
    if remainder > 0:
        spend_stackables(user, stone, remainder)


def evolve(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"CharacterId", "UpgradeCount", "DreamSpiritStoneUsageAmount"}
        or not integer(body["CharacterId"], minimum=1)
        or not integer(body["UpgradeCount"], minimum=1)
        or not integer(body["DreamSpiritStoneUsageAmount"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select an owned hero, evolution steps and Dream Evolution Stone amount")
    ident, count, budget = (
        body["CharacterId"],
        body["UpgradeCount"],
        body["DreamSpiritStoneUsageAmount"],
    )
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user, record = profile["User"], profile["UserRecord"]
        previous = db.execute(
            "SELECT character_id,upgrade_count,dream_budget FROM hero_evolution_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if previous:
            if tuple(previous) != (ident, count, budget):
                raise ValueError("Evolution identity already belongs to another request")
            return {"User": user, "UserRecord": record}
        hero = owned_character(user, ident)
        forms, steps, dream = rules(account.references.read_bytes("static_data_get.bin"))
        form = forms.get(hero["CharacterId"])
        if form is None:
            raise ValueError("This hero has no further regular evolution")
        slots = user.get("TrainingSlots", {})
        if not isinstance(slots, dict) or any(
            not isinstance(s, dict)
            or (s.get("CharacterId") == ident and (s.get("IsEvolve") or s.get("IsEvolveOnly")))
            for s in slots.values()
        ):
            raise ValueError("This hero has a Training Room evolution")
        rank, target, stone, rate = form
        current = hero.get("RankUpgrade", 0)
        cost, evolves = price(steps.get(rank, {}), current, count)
        if not integer(user.get("Cas"), MAX_REVISION - 1):
            raise ValueError("Invalid saved user revision")
        if evolves:
            if not integer(record.get("EvolveCharacterCount", 0), INT_MAX - 1) or not integer(
                record.get("Cas"), MAX_REVISION - 1
            ):
                raise ValueError("Invalid saved evolution count or record revision")
            hero["CharacterId"] = target
            record["EvolveCharacterCount"] = record.get("EvolveCharacterCount", 0) + 1
            record["Cas"] += 1
        pay(user, dream, budget, stone, rate, cost)
        hero["RankUpgrade"] = 0 if evolves else current + count
        user["Cas"] += 1
        db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        db.execute(
            "INSERT INTO hero_evolution_requests VALUES(?,?,?,?)",
            (operation_id, ident, count, budget),
        )
    return {"User": user, "UserRecord": record}
