# SPDX-License-Identifier: Apache-2.0
"""Apply one or all remaining catalog-backed blessing levels to an owned hero."""

import json
from functools import lru_cache

from .characters import hero_resource, owned_character
from .hero_catalog import growth_tables
from .summon_payment import spend_tickets
from .village import INT_MAX, MAX_REVISION, integer

ONE = "/user/bless-character"
ALL = "/user/bless-character-all"
ROUTES = (ONE, ALL)
BLESSING_FEATURE = 114


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS hero_blessing_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, character_id INTEGER NOT NULL)"
    )


@lru_cache(maxsize=2)
def rules(body):
    tables = growth_tables(body)
    try:
        costs = {}
        for row in json.loads(tables["exps2"])["HeroBlessing"]:
            level = int(row["BlessingLevel"])
            cost = row["BlessingCosts"]
            if level in costs or not integer(level) or not integer(cost, minimum=1):
                raise ValueError("Invalid blessing cost")
            costs[level] = cost
        prices = tuple(costs[level] for level in range(len(costs)))
        if not prices:
            raise ValueError("Missing blessing levels")
        caps = {}
        for spec in json.loads(tables["heroes"]):
            tiers = spec.get("BlessingLevelOptions")
            if spec.get("Playable") is True and tiers:
                if not isinstance(tiers, list) or not all(isinstance(t, list) and t for t in tiers):
                    raise ValueError("Invalid blessing options")
                caps[spec["Id"]] = min(len(prices), len(tiers))
        (ticket,) = (
            s["Id"]
            for s in json.loads(tables["items"])
            if s.get("Type") == "ticket" and s.get("Name") == "hero_blessing_ticket"
        )
        (unlock,) = (r for r in json.loads(tables["unlockfeature"]) if r["Id"] == BLESSING_FEATURE)
        region = unlock["Value"]
        quest = region.get("KakaoGlobal", region.get("Default"))
        if (
            unlock["Type"] != "QuestClear"
            or not integer(quest, minimum=1)
            or not integer(ticket, minimum=1)
        ):
            raise ValueError("Invalid blessing feature or book")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid hero blessing catalog") from exc
    return caps, prices, ticket, quest


def bless(account, route, body, operation_id):
    if (
        route not in ROUTES
        or not isinstance(body, dict)
        or set(body) != {"CharacterId"}
        or not integer(body["CharacterId"], minimum=1)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select an owned character for blessing")
    ident = body["CharacterId"]
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user, record = profile["User"], profile["UserRecord"]
        previous = db.execute(
            "SELECT route,character_id FROM hero_blessing_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if previous:
            if tuple(previous) != (route, ident):
                raise ValueError("Blessing identity already belongs to another request")
            return {"User": hero_resource(user, "ItemStackables"), "UserRecord": record}
        hero = owned_character(user, ident)
        caps, prices, ticket, quest = rules(account.references.read_bytes("static_data_get.bin"))
        if not any(
            q["Id"] == quest and q["Grade"] >= 0 for q in profile["UserProgress"]["QuestProgresses"]
        ):
            raise ValueError("Complete the blessing unlock quest first")
        current = hero.get("BlessLevel", 0)
        cap = caps.get(hero.get("CharacterId"), 0)
        if not integer(current, cap) or current == cap:
            raise ValueError("This hero has no further blessing levels")
        slots = user.get("TrainingSlots", {})
        if not isinstance(slots, dict) or any(
            not isinstance(s, dict) or (s.get("CharacterId") == ident and s.get("IsBlessing"))
            for s in slots.values()
        ):
            raise ValueError("This hero has a Training Room blessing")
        target = cap if route == ALL else current + 1
        gained = target - current
        if record.get("Misc") is None:
            record["Misc"] = {}
        misc = record["Misc"]
        if (
            not isinstance(misc, dict)
            or not integer(misc.get("BlessCharacterCount", 0), INT_MAX - gained)
            or not integer(user.get("Cas"), MAX_REVISION - 1)
            or not integer(record.get("Cas"), MAX_REVISION - 1)
        ):
            raise ValueError("Invalid saved blessing count or revision")
        spend_tickets(user, ticket, sum(prices[current:target]))
        hero["BlessLevel"] = target
        misc["BlessCharacterCount"] = misc.get("BlessCharacterCount", 0) + gained
        user["Cas"] += 1
        record["Cas"] += 1
        db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        db.execute("INSERT INTO hero_blessing_requests VALUES(?,?,?)", (operation_id, route, ident))
    return {"User": hero_resource(user, "ItemStackables"), "UserRecord": record}
