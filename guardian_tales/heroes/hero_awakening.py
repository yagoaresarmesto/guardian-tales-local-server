# SPDX-License-Identifier: Apache-2.0
"""Save individual and auto awakening selections when the hero screen closes."""

import base64
import json
import struct
from collections import Counter
from datetime import datetime, timezone

from guardian_tales.settlement.village import GOLD, INT_MAX, MAX_REVISION, integer
from guardian_tales.summons.summon_payment import spend_tickets as spend_stackables

from .awakening_catalog import catalog
from .characters import hero_resource, hero_transaction, owned_character

ROUTE = "/user/open-awakening-node-all"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS hero_awakening_requests "
        "(operation_id TEXT PRIMARY KEY, selection TEXT NOT NULL)"
    )


def saved_mask(hero, node_count):
    encoded = hero.get("AwakeningTree")
    if encoded in (None, ""):
        prefix, raw = struct.pack("<I", hero["CharacterId"]), b""
    else:
        if not isinstance(encoded, str) or len(encoded) > 2048 or encoded.count("|") != 1:
            raise ValueError("Invalid saved awakening tree")
        prefix, raw = (base64.b64decode(part, validate=True) for part in encoded.split("|"))
        if len(prefix) != 4 or len(raw) > 125:
            raise ValueError("Invalid saved awakening mask")
    return prefix, bytearray(raw.ljust((node_count + 7) // 8, b"\0"))


def gold_discount(user, requested, rate):
    if not requested:
        return 0
    until = user.get("Options", {}).get("AccountBuffs", {}).get("AwakeningDc")
    if not isinstance(until, str):
        raise ValueError("The awakening gold discount is inactive")
    expiry = datetime.fromisoformat(until)
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("The awakening gold discount expired")
    return rate


def apply_nodes(user, hero, tree, rank, indices, discount, *, free=False):
    prefix, mask = saved_mask(hero, len(tree.nodes))
    opened = {i for i in range(len(tree.nodes)) if mask[i // 8] & (1 << (i % 8))}
    new = set(indices) - opened
    breaks = hero.get("LimitBreaks", 0)
    if not integer(breaks):
        raise ValueError("Invalid hero limit breaks")
    tree.unlock(indices, opened, rank, breaks)
    if not new:
        return
    if not integer(user.get("Cas"), MAX_REVISION - 1):
        raise ValueError("Invalid saved awakening revision")
    if not free:
        pay_for_nodes(user, hero, tree, new, discount)
    for i in new:
        mask[i // 8] |= 1 << (i % 8)
    hero["AwakeningTree"] = "|".join(base64.b64encode(part).decode() for part in (prefix, mask))
    user["Cas"] += 1


def pay_for_nodes(user, hero, tree, indices, discount):
    materials = Counter()
    gold = 0
    for i in indices:
        node = tree.nodes[i]
        gold += round(node.gold * (1 - discount))
        for item, amount in node.stones:
            materials[item] += amount
    balances = [row for row in user["Assets"] if row["Id"] == GOLD]
    if len(balances) != 1 or not integer(balances[0].get("Amount"), minimum=gold):
        raise ValueError("Not enough gold to awaken the selected nodes")
    asset = balances[0]
    if not integer(asset.get("Spent"), INT_MAX - gold, -INT_MAX - 1) or not integer(
        hero.get("AwakeningTreeGold", 0), INT_MAX - gold
    ):
        raise ValueError("Invalid saved awakening expenditure or revision")
    for item, amount in materials.items():
        spend_stackables(user, item, amount)
    asset["Amount"] -= gold
    asset["Spent"] += gold
    hero["AwakeningTreeGold"] = hero.get("AwakeningTreeGold", 0) + gold


def awaken(account, body, operation_id, *, free=False):
    if (
        not isinstance(body, dict)
        or set(body) != {"CharacterId", "NodeIndices", "discountBuff"}
        or not integer(body["CharacterId"], minimum=1)
        or type(body["discountBuff"]) is not bool
        or not isinstance(body["NodeIndices"], list)
        or not 1 <= len(body["NodeIndices"]) <= 1000
        or not all(integer(i, 999) for i in body["NodeIndices"])
        or len(set(body["NodeIndices"])) != len(body["NodeIndices"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select awakening nodes on an owned hero")
    ident, indices, requested = body["CharacterId"], body["NodeIndices"], body["discountBuff"]
    selection = json.dumps([ident, sorted(indices), requested], separators=(",", ":"))
    db = account.db
    with hero_transaction(db):
        profile = account.profile()
        user = profile["User"]
        prior = db.execute(
            "SELECT selection FROM hero_awakening_requests WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if prior:
            if prior[0] != selection:
                raise ValueError("Awakening identity already belongs to another selection")
            return {"User": hero_resource(user, "Assets", "ItemStackables")}
        hero = owned_character(user, ident)
        slots = user.get("TrainingSlots", {})
        if not isinstance(slots, dict) or any(
            not isinstance(slot, dict)
            or (slot.get("CharacterId") == ident and slot.get("IsAwakening"))
            for slot in slots.values()
        ):
            raise ValueError("This hero has a Training Room awakening")
        heroes, rate = catalog(account.references.read_bytes("static_data_get.bin"))
        if hero["CharacterId"] not in heroes:
            raise ValueError("Missing awakening tree for the selected hero")
        tree, rank = heroes[hero["CharacterId"]]
        apply_nodes(
            user, hero, tree, rank, indices, gold_discount(user, requested, rate), free=free
        )
        db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        db.execute("INSERT INTO hero_awakening_requests VALUES(?,?)", (operation_id, selection))
    return {"User": hero_resource(user, "Assets", "ItemStackables")}
