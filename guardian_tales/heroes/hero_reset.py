# SPDX-License-Identifier: Apache-2.0
"""Reset one owned hero's development without consuming or refunding items."""

import json

from guardian_tales.administration import andras_trial
from guardian_tales.settlement.village import MAX_REVISION, integer

from .characters import hero_transaction, owned_character
from .hero_equipment import catalog, resource

ROUTE = "/user/recall-character-growth/v2"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS hero_reset_requests "
        "(operation_id TEXT PRIMARY KEY, character_id INTEGER NOT NULL, receive_crystal INTEGER NOT NULL)"
    )


def reset_spec(heroes, spec_id):
    spec = heroes.get(spec_id)
    if not spec or spec.get("Playable") is not True or not integer(spec.get("Rank"), 6):
        raise ValueError("Hero Reset requires a playable hero specification")
    origin = heroes.get(spec.get("OriginId"))
    category = spec.get("SummonCategory")
    if (
        not origin
        or origin.get("OriginId") != origin["Id"]
        or origin.get("SummonCategory") != category
        or category not in ("Unique", "Story", "Normal")
    ):
        raise ValueError("Missing hero origin for Hero Reset")
    if category == "Unique":
        return origin
    # Normal and story heroes retain ordinary evolution. Ascension and Myth
    # are growth above the five-star form (catalog rank 4).
    if spec["Rank"] <= 4:
        return spec
    ordinary = [
        row
        for row in heroes.values()
        if row.get("OriginId") == origin["Id"] and row.get("Rank") == 4
    ]
    if len(ordinary) != 1:
        raise ValueError("Missing or ambiguous five-star form for Hero Reset")
    return ordinary[0]


def reset_changes(user, hero, heroes, references):
    """Plan the changes for one owned hero without modifying the save."""
    ident = hero["Id"]
    slots = user.get("TrainingSlots", {})
    if not isinstance(slots, dict) or any(
        not isinstance(slot, dict) or slot.get("CharacterId") == ident for slot in slots.values()
    ):
        raise ValueError("Remove the hero from the Training Room before resetting")
    trial = andras_trial.load(references)
    if (
        trial
        and trial["active"]
        and (trial["owner_id"], trial["inventory_id"]) == (user["Id"], ident)
    ):
        raise ValueError("Disable the experimental Andras trial before resetting her")
    spec_id = hero.get("CharacterId")
    if not integer(spec_id, minimum=1):
        raise ValueError("Invalid saved hero specification")
    target = reset_spec(heroes, spec_id)
    changes = dict(Experience=0, LimitBreaks=0, BlessLevel=0, AwakeningTree="", AwakeningTreeGold=0)
    if target["Id"] != spec_id or target["SummonCategory"] == "Unique":
        changes.update(CharacterId=target["Id"], RankUpgrade=0)
    if hero.get("SpriteRank") is not None and not integer(hero["SpriteRank"], target["Rank"]):
        changes["SpriteRank"] = None
    return {key: value for key, value in changes.items() if hero.get(key) != value}


def reset(account, body, operation_id, *, heroes=None):
    if (
        not isinstance(body, dict)
        or set(body) != {"CharacterId", "ReceiveCrystal"}
        or not integer(body["CharacterId"], minimum=1)
        or type(body["ReceiveCrystal"]) is not bool
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Hero Reset requires an owned character ID and a crystal selection")
    ident = body["CharacterId"]
    db = account.db
    with hero_transaction(db):
        profile = account.profile()
        user = profile["User"]
        prior = db.execute(
            "SELECT character_id,receive_crystal FROM hero_reset_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if prior:
            if tuple(prior) != (ident, body["ReceiveCrystal"]):
                raise ValueError("Hero Reset identity was used for a different request")
            return {"User": resource(user), "AddedItems": []}
        hero = owned_character(user, ident)
        if heroes is None:
            heroes, _ = catalog(account.references.read_bytes("static_data_get.bin"))
        changes = reset_changes(user, hero, heroes, account.references)
        if changes:
            if not integer(user.get("Cas"), MAX_REVISION - 1):
                raise ValueError("Invalid saved user revision")
            hero.update(changes)
            user["Cas"] += 1
            db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        db.execute(
            "INSERT INTO hero_reset_requests VALUES(?,?,?)",
            (operation_id, ident, body["ReceiveCrystal"]),
        )
    return {"User": resource(user), "AddedItems": []}
