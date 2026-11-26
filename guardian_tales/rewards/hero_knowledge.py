# SPDX-License-Identifier: Apache-2.0
"""Initial acquisition knowledge for untrained base heroes, with atomic batch receipts."""

import json


def load_knowledge_catalog(references):
    value = references.json("hero_knowledge_catalog.json")
    heroes = value.get("heroes") if isinstance(value, dict) else None
    if not isinstance(heroes, dict) or not 1 <= len(heroes) <= 2000:
        raise ValueError("Invalid initial hero-knowledge catalog")
    knowledge_ids = set()
    for key, row in heroes.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or int(key) > 0x7FFFFFFF
            or not isinstance(row, dict)
            or set(row) != {"knowledge_id", "origin_id", "rewards"}
            or type(row["origin_id"]) is not int
            or str(row["origin_id"]) != key
            or type(row["knowledge_id"]) is not int
            or not 1 <= row["knowledge_id"] <= 0x7FFFFFFF
            or row["knowledge_id"] % 100 != 1
            or row["knowledge_id"] in knowledge_ids
            or not isinstance(row["rewards"], list)
            or len(row["rewards"]) > 32
        ):
            raise ValueError("Only verified initial acquisition knowledge rows are supported")
        knowledge_ids.add(row["knowledge_id"])
        for reward in row["rewards"]:
            if (
                not isinstance(reward, dict)
                or set(reward) != {"item_id", "amount"}
                or type(reward["item_id"]) is not int
                or not 1 <= reward["item_id"] <= 0x7FFFFFFF
                or type(reward["amount"]) is not int
                or not 1 <= reward["amount"] <= 0x7FFFFFFF
            ):
                raise ValueError("Invalid hero-knowledge asset reward")
    return heroes


def claim_hero_knowledge(account, request, operation_id):
    if (
        not isinstance(request, dict)
        or set(request) != {"CharacterIds"}
        or not isinstance(request["CharacterIds"], list)
        or not 1 <= len(request["CharacterIds"]) <= 512
        or any(type(i) is not int or not 1 <= i <= 0x7FFFFFFF for i in request["CharacterIds"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid hero-knowledge batch or request identity")
    ids = list(dict.fromkeys(request["CharacterIds"]))
    encoded = json.dumps({"CharacterIds": sorted(ids)}, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request,rewards FROM hero_knowledge_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Hero-knowledge request identity was already used for another batch")
        return {"User": account.profile()["User"], "AddedItems": json.loads(previous[1])}

    catalog = load_knowledge_catalog(account.references)
    profile = account.profile()
    user = profile["User"]
    characters = {c["Id"]: c for c in user["Characters"]}
    if any(i not in characters for i in ids):
        raise ValueError("Hero-knowledge IDs must identify owned inventory characters")
    pending = []
    origins = set()
    for character_id in ids:
        character = characters[character_id]
        row = catalog.get(str(character["CharacterId"]))
        if (
            row is None
            or any(
                type(character.get(k)) is not int or character[k] != 0
                for k in ("Experience", "LimitBreaks", "RankUpgrade", "BlessLevel")
            )
            or character.get("AwakeningTree") != ""
        ):
            raise ValueError("Initial knowledge currently supports untrained base heroes only")
        if row["origin_id"] in origins:
            raise ValueError("A hero-knowledge batch cannot repeat an owned hero origin")
        origins.add(row["origin_id"])
        flags = character.get("Knowledge")
        if type(flags) is not int or not 0 <= flags <= 0x7FFFFFFF:
            raise ValueError("Invalid saved hero-knowledge flags")
        saved = account.db.execute(
            "SELECT character_id,knowledge_id FROM hero_knowledge_claims WHERE character_id=? OR knowledge_id=?",
            (character_id, row["knowledge_id"]),
        ).fetchall()
        expected = [(character_id, row["knowledge_id"])] if flags & 1 else []
        if saved != expected:
            raise ValueError("Hero-knowledge receipts do not match saved acquisition flags")
        if not flags & 1:
            pending.append((character, row))

    assets = {a["Id"]: a for a in user["Assets"]}
    notices = []
    receipts = []
    for character, row in pending:
        rewards = []
        for reward in row["rewards"]:
            item_id, amount = reward["item_id"], reward["amount"]
            if item_id not in assets:
                raise ValueError("Only existing hero-knowledge asset rewards are supported")
            asset = assets[item_id]
            if type(asset["Amount"]) is not int or not 0 <= asset["Amount"] <= 0x7FFFFFFF - amount:
                raise ValueError("Hero-knowledge reward balance overflow or invalid saved asset")
            asset["Amount"] += amount
            rewards.append({"Id": 0, "ItemId": item_id, "Amount": amount})
        notices.extend(rewards)
        character["Knowledge"] |= 1
        receipts.append(
            (character["Id"], row["knowledge_id"], json.dumps(rewards, separators=(",", ":")))
        )
    if pending:
        user["Cas"] += 1
    with account.db:
        for row in receipts:
            account.db.execute("INSERT INTO hero_knowledge_claims VALUES(?,?,?)", row)
        account.db.execute(
            "INSERT INTO hero_knowledge_requests VALUES(?,?,?)",
            (
                operation_id,
                encoded,
                json.dumps(notices, separators=(",", ":")),
            ),
        )
        if pending:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"User": user, "AddedItems": notices}
