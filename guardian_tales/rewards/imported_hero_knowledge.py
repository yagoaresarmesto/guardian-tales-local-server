# SPDX-License-Identifier: Apache-2.0
"""Native hero-book objectives with nonpaying official baselines and atomic receipts."""

import base64
import binascii
import json
from bisect import bisect_right

from guardian_tales.accounts.snapshots import CLIENT

MAX_INT = 0x7FFFFFFF
MAX_LONG = 0x7FFFFFFFFFFFFFFF
TYPES = {"Get", "Evolve", "LevelUp", "LimitBreak", "AwakeningSkill", "Ascend", "Blessing", "Myth"}


def integer(value, minimum=0, maximum=MAX_INT):
    return type(value) is int and minimum <= value <= maximum


def identifier(key):
    return (
        isinstance(key, str)
        and key.isascii()
        and key.isdecimal()
        and not key.startswith("0")
        and len(key) <= 10
        and int(key) <= MAX_INT
    )


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS imported_hero_knowledge_baselines "
        "(origin_id INTEGER PRIMARY KEY, character_id INTEGER NOT NULL UNIQUE, flags INTEGER NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS imported_hero_knowledge_claims "
        "(origin_id INTEGER NOT NULL, character_id INTEGER NOT NULL, "
        "knowledge_id INTEGER PRIMARY KEY, rewards TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS imported_hero_knowledge_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, rewards TEXT NOT NULL)"
    )


def bit(knowledge_id):
    return 1 << max(knowledge_id % 100 - 1, 0)


def load_catalog(references):
    path = references.directory / "imported_hero_knowledge_catalog.json"
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Imported hero knowledge requires a matching external catalog")
    catalog = references.json(path.name)
    if not isinstance(catalog, dict) or catalog.get("client") != CLIENT:
        raise ValueError("Invalid imported hero-knowledge client")
    levels, heroes, origins = (
        catalog.get("experience_by_level"),
        catalog.get("heroes"),
        catalog.get("origins"),
    )
    if (
        not isinstance(levels, list)
        or not 2 <= len(levels) <= 1000
        or levels[0] != 0
        or any(not integer(v) for v in levels)
        or any(a >= b for a, b in zip(levels, levels[1:]))
        or not isinstance(heroes, dict)
        or not 1 <= len(heroes) <= 2000
        or not isinstance(origins, dict)
        or not 1 <= len(origins) <= 512
    ):
        raise ValueError("Invalid imported hero-knowledge catalog")
    for key, hero in heroes.items():
        if (
            not identifier(key)
            or not isinstance(hero, dict)
            or set(hero) != {"origin_id", "rank"}
            or not integer(hero["origin_id"], 1)
            or not integer(hero["rank"], 0, 6)
        ):
            raise ValueError("Invalid hero-knowledge origin or raw rank")
    knowledge_ids = set()
    for key, origin in origins.items():
        if (
            not identifier(key)
            or not isinstance(origin, dict)
            or set(origin) != {"nodes", "objectives"}
            or not isinstance(origin["nodes"], list)
            or not 1 <= len(origin["nodes"]) <= 1000
            or any(not integer(n, 0, 999) for n in origin["nodes"])
            or sorted(set(origin["nodes"])) != origin["nodes"]
            or not isinstance(origin["objectives"], list)
            or not 1 <= len(origin["objectives"]) <= 32
        ):
            raise ValueError("Invalid hero-knowledge objectives or awakening nodes")
        masks = set()
        for row in origin["objectives"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"id", "type", "value", "rewards"}
                or not integer(row["id"], 1)
                or not 1 <= row["id"] % 100 <= 31
                or row["id"] in knowledge_ids
                or bit(row["id"]) in masks
                or not isinstance(row["type"], str)
                or row["type"] not in TYPES
                or not integer(row["value"])
                or not isinstance(row["rewards"], list)
                or len(row["rewards"]) > 32
                or (row["type"] == "Ascend" and row["value"] != 5)
                or (row["type"] == "Myth" and row["value"] != 6)
                or (row["type"] == "LevelUp" and row["value"] >= len(levels))
            ):
                raise ValueError("Invalid native hero-knowledge objective")
            knowledge_ids.add(row["id"])
            masks.add(bit(row["id"]))
            for reward in row["rewards"]:
                if (
                    not isinstance(reward, dict)
                    or set(reward) != {"item_id", "amount"}
                    or type(reward["item_id"]) is not int
                    or reward["item_id"] != 70003
                    or not integer(reward["amount"], 1)
                ):
                    raise ValueError("Only verified gem hero-knowledge rewards are supported")
    return catalog


def opened_nodes(encoded, indices):
    if encoded is None or encoded == "":
        return 0
    if not isinstance(encoded, str) or len(encoded) > 2048 or encoded.count("|") != 1:
        raise ValueError("Invalid saved awakening tree")
    try:
        prefix, data = (base64.b64decode(v, validate=True) for v in encoded.split("|"))
    except (ValueError, binascii.Error) as error:
        raise ValueError("Invalid saved awakening encoding") from error
    # Evolved heroes can retain an older encoded spec ID. The native constructor
    # uses the current hero origin's node map and ignores the serialized prefix.
    if len(prefix) != 4 or len(data) > 125:
        raise ValueError("Invalid saved awakening data")
    return sum(i // 8 < len(data) and bool(data[i // 8] & (1 << (i % 8))) for i in indices)


def progress(character, hero, origin, levels):
    for field in ("Experience", "LimitBreaks", "BlessLevel", "Knowledge"):
        if not integer(character.get(field)):
            raise ValueError("Invalid saved hero-knowledge progress")
    rank = hero["rank"]
    return {
        "Get": 1,
        "Evolve": rank,
        "LevelUp": bisect_right(levels, character["Experience"]) - 1,
        "LimitBreak": character["LimitBreaks"],
        "AwakeningSkill": opened_nodes(character.get("AwakeningTree"), origin["nodes"]),
        "Ascend": int(rank == 5 or rank >= 6),
        "Blessing": character["BlessLevel"],
        "Myth": int(rank >= 6),
    }


def claim(account, request, operation_id):
    if (
        not isinstance(request, dict)
        or set(request) != {"CharacterIds"}
        or not isinstance(request["CharacterIds"], list)
        or not 1 <= len(request["CharacterIds"]) <= 512
        or any(not integer(i, 1) for i in request["CharacterIds"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid imported hero-knowledge batch or identity")
    ids = sorted(set(request["CharacterIds"]))
    encoded = json.dumps({"CharacterIds": ids}, separators=(",", ":"))
    saved = account.db.execute(
        "SELECT request,rewards FROM imported_hero_knowledge_requests WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if saved:
        if saved[0] != encoded:
            raise ValueError("Hero-knowledge identity already belongs to another batch")
        return {"User": account.profile()["User"], "AddedItems": json.loads(saved[1])}

    catalog = load_catalog(account.references)
    profile = account.profile()
    user = profile["User"]
    characters = {c["Id"]: c for c in user["Characters"]}
    if (
        len(characters) != len(user["Characters"])
        or any(not integer(i, 1) for i in characters)
        or any(i not in characters for i in ids)
        or not integer(user.get("Cas"), 0, MAX_LONG)
    ):
        raise ValueError("Hero knowledge requires unambiguous owned heroes and a valid revision")
    baselines, pending = [], []
    for character_id in ids:
        character = characters[character_id]
        hero = catalog["heroes"].get(str(character.get("CharacterId")))
        origin = catalog["origins"].get(str(hero["origin_id"])) if hero else None
        if origin is None:
            raise ValueError("Hero knowledge requires a configured owned hero origin")
        origin_id = hero["origin_id"]
        if (
            sum(
                catalog["heroes"].get(str(c.get("CharacterId")), {}).get("origin_id") == origin_id
                for c in characters.values()
            )
            != 1
        ):
            raise ValueError("Hero knowledge requires a unique owned origin")
        values = progress(character, hero, origin, catalog["experience_by_level"])
        flags = character["Knowledge"]
        previous = account.db.execute(
            "SELECT origin_id,character_id,flags FROM imported_hero_knowledge_baselines "
            "WHERE origin_id=? OR character_id=?",
            (origin_id, character_id),
        ).fetchall()
        receipts = account.db.execute(
            "SELECT origin_id,character_id,knowledge_id FROM imported_hero_knowledge_claims "
            "WHERE origin_id=? OR character_id=?",
            (origin_id, character_id),
        ).fetchall()
        if not previous:
            if receipts:
                raise ValueError("Local hero knowledge requires its original official baseline")
            base = flags
            baselines.append((origin_id, character_id, base))
        else:
            if len(previous) != 1 or previous[0][:2] != (origin_id, character_id):
                raise ValueError("Hero-knowledge baseline ownership mismatch")
            base = previous[0][2]
            if not integer(base) or base & flags != base:
                raise ValueError("Saved hero knowledge lost its official baseline")
        expected = {
            (origin_id, character_id, r["id"])
            for r in origin["objectives"]
            if flags & bit(r["id"]) and not base & bit(r["id"])
        }
        local_flags = 0
        for _, _, knowledge_id in expected:
            local_flags |= bit(knowledge_id)
        if set(receipts) != expected or base | local_flags != flags:
            raise ValueError("Hero-knowledge receipts do not match saved flags")
        for row in origin["objectives"]:
            threshold = {"Get": 1, "Ascend": 1, "Myth": 1}.get(row["type"], row["value"])
            if not flags & bit(row["id"]) and values[row["type"]] >= threshold:
                pending.append((origin_id, character, row))

    assets = {a["Id"]: a for a in user["Assets"]}
    if len(assets) != len(user["Assets"]):
        raise ValueError("Hero-knowledge asset IDs must be unique")
    notices, receipts = [], []
    for origin_id, character, row in pending:
        granted = []
        for reward in row["rewards"]:
            asset = assets.get(reward["item_id"])
            amount = reward["amount"]
            if asset is None or not integer(asset.get("Amount"), 0, MAX_INT - amount):
                raise ValueError("Invalid hero-knowledge reward balance or overflow")
            asset["Amount"] += amount
            granted.append({"Id": 0, "ItemId": reward["item_id"], "Amount": amount})
        notices.extend(granted)
        character["Knowledge"] |= bit(row["id"])
        receipts.append((origin_id, character["Id"], row["id"], json.dumps(granted)))
    if pending:
        if user["Cas"] == MAX_LONG:
            raise ValueError("Hero-knowledge revision overflow")
        user["Cas"] += 1
    with account.db:
        account.db.executemany(
            "INSERT INTO imported_hero_knowledge_baselines VALUES(?,?,?)", baselines
        )
        account.db.executemany(
            "INSERT INTO imported_hero_knowledge_claims VALUES(?,?,?,?)", receipts
        )
        account.db.execute(
            "INSERT INTO imported_hero_knowledge_requests VALUES(?,?,?)",
            (operation_id, encoded, json.dumps(notices, separators=(",", ":"))),
        )
        if pending:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"User": user, "AddedItems": notices}
