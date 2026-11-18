# SPDX-License-Identifier: Apache-2.0
"""Contiguous catalog challenge steps with atomic batch and per-request receipts."""

import json

from .challenge_progress import CONDITIONS, MAX_LONG, integer, progress_value
from .items import inventory_item
from .snapshots import CLIENT, is_imported


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS imported_challenge_baselines "
        "(group_id INTEGER PRIMARY KEY, step INTEGER NOT NULL)"
    )


def load_challenge_catalog(references, imported=False):
    name = (
        "imported_challenge_mission_catalog.json" if imported else "challenge_mission_catalog.json"
    )
    if imported:
        path = references.directory / name
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Imported challenges require a matching external catalog")
    value = references.json(name)
    if imported and (not isinstance(value, dict) or value.get("client") != CLIENT):
        raise ValueError("Invalid imported challenge catalog client")
    groups = value.get("groups") if isinstance(value, dict) else None
    if not isinstance(groups, dict) or not 1 <= len(groups) <= 512:
        raise ValueError("Invalid challenge mission catalog")
    total = 0
    for key, group in groups.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or int(key) > 0x7FFFFFFF
            or not isinstance(group, dict)
            or set(group) != {"condition", "steps"}
            or not isinstance(group["condition"], str)
            or group["condition"]
            not in (CONDITIONS if imported else ("owned_heroes", "hero_draws", "collected_gold"))
            or not isinstance(group["steps"], list)
            or not 1 <= len(group["steps"]) <= 1000
        ):
            raise ValueError("Invalid challenge mission group")
        total += len(group["steps"])
        previous = 0
        for step in group["steps"]:
            if (
                not isinstance(step, dict)
                or set(step) != {"threshold", "rewards"}
                or type(step["threshold"]) is not int
                or not previous < step["threshold"] <= 0x7FFFFFFF
                or not isinstance(step["rewards"], list)
                or not 1 <= len(step["rewards"]) <= 32
            ):
                raise ValueError("Challenge steps need increasing positive thresholds")
            previous = step["threshold"]
            for reward in step["rewards"]:
                if (
                    not isinstance(reward, dict)
                    or set(reward)
                    != ({"item_id", "amount", "storage"} if imported else {"item_id", "amount"})
                    or imported
                    and reward.get("storage") not in ("asset", "stackable", "misc")
                    or type(reward["item_id"]) is not int
                    or not 1 <= reward["item_id"] <= 0x7FFFFFFF
                    or type(reward["amount"]) is not int
                    or not 1 <= reward["amount"] <= 0x7FFFFFFF
                    or reward.get("storage") == "misc"
                    and reward["amount"] != 1
                ):
                    raise ValueError("Invalid challenge asset reward")
    if total > 10000:
        raise ValueError("Challenge catalog has too many steps")
    return groups


def allocate_reward_item(user, item_id):
    counter = user.get("ItemIdCounter")
    owned = [
        row["Id"] for kind in ("ItemWeapons", "ItemMiscs", "ItemStackables") for row in user[kind]
    ]
    if (
        not integer(counter, 0x7FFFFFFE)
        or any(not integer(v) or v > counter for v in owned)
        or len(set(owned)) != len(owned)
    ):
        raise ValueError(
            "Invalid inventory counter or duplicate IDs for challenge reward allocation"
        )
    user["ItemIdCounter"] += 1
    return inventory_item(user["ItemIdCounter"], item_id)


def grant_reward(user, assets, reward):
    item_id, amount = reward["item_id"], reward["amount"]
    if reward.get("storage", "asset") == "asset":
        if item_id not in assets or not integer(assets[item_id].get("Amount"), 0x7FFFFFFF - amount):
            raise ValueError("Unsupported challenge asset reward or balance overflow")
        assets[item_id]["Amount"] += amount
        inventory_id = 0
    elif reward["storage"] == "misc":
        if item_id in assets or any(row["ItemId"] == item_id for row in user["ItemMiscs"]):
            raise ValueError(
                "An already owned unique challenge cosmetic needs a duplicate reward policy"
            )
        item = allocate_reward_item(user, item_id)
        user["ItemMiscs"].append(item)
        inventory_id = item["Id"]
    else:
        if item_id in assets:
            raise ValueError("A challenge asset cannot be stored as a stackable")
        stacks = user.get("ItemStackables")
        if not isinstance(stacks, list):
            raise ValueError("Invalid saved challenge stackable inventory")
        matches = [row for row in stacks if row.get("ItemId") == item_id]
        if any(
            not integer(row.get("Amount")) or not integer(row.get("Id")) or row["Id"] == 0
            for row in matches
        ):
            raise ValueError("Invalid saved challenge reward stack")
        active = [row for row in matches if row["Amount"]]
        if len(active) > 1:
            raise ValueError("Challenge reward stack is ambiguous")
        item = (active or matches or [None])[0]
        if item is None:
            item = allocate_reward_item(user, item_id)
            item["Amount"] = 0
            stacks.append(item)
        if not integer(item["Amount"], 0x7FFFFFFF - amount):
            raise ValueError("Challenge reward stack overflow")
        item["Amount"] += amount
        inventory_id = item["Id"]
    return {"Id": inventory_id, "ItemId": item_id, "Amount": amount}


def response(profile, rewards):
    return {"User": profile["User"], "UserMission": profile["UserMission"], "AddedItems": rewards}


def claim_challenges(account, request, operation_id, all_steps):
    if (
        not isinstance(request, dict)
        or set(request) != {"missionIds"}
        or not isinstance(request["missionIds"], list)
        or not 1 <= len(request["missionIds"]) <= 512
        or any(type(v) is not int or not 1 <= v <= 0x7FFFFFFF for v in request["missionIds"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or type(all_steps) is not bool
        or account.needs_prologue()
    ):
        raise ValueError("Invalid challenge claim batch or request identity")
    ids = list(dict.fromkeys(request["missionIds"]))
    encoded = json.dumps({"groups": sorted(ids), "all_steps": all_steps}, separators=(",", ":"))
    receipt = account.db.execute(
        "SELECT request,rewards FROM challenge_mission_requests WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if receipt:
        if receipt[0] != encoded:
            raise ValueError("Challenge request identity was already used for another batch")
        return response(account.profile(), json.loads(receipt[1]))
    imported = is_imported(account.db)
    catalog = load_challenge_catalog(account.references, imported)
    if any(str(g) not in catalog for g in ids):
        raise ValueError("Only configured challenge groups can be claimed")
    profile = account.profile()
    user, mission = profile["User"], profile["UserMission"]
    claims = mission["ChallengeClaimed"]
    if not isinstance(claims, dict) or not isinstance(user["Characters"], list):
        raise ValueError("Invalid saved challenge state")
    if imported and (
        mission.get("UserId") != user.get("Id")
        or not integer(user.get("Cas"), MAX_LONG)
        or not integer(mission.get("Cas"), MAX_LONG)
    ):
        raise ValueError("Invalid imported challenge ownership or revisions")
    targets = {}
    new_steps = []
    baselines = []
    for group_id in ids:
        group = catalog[str(group_id)]
        claimed = claims.get(str(group_id), 0)
        if type(claimed) is not int or not 0 <= claimed <= len(group["steps"]):
            raise ValueError("Saved challenge step is outside the configured group")
        receipts = account.db.execute(
            "SELECT step FROM challenge_mission_claims WHERE group_id=? ORDER BY step", (group_id,)
        ).fetchall()
        base = 0
        if imported:
            saved = account.db.execute(
                "SELECT step FROM imported_challenge_baselines WHERE group_id=?", (group_id,)
            ).fetchone()
            if saved is None:
                if receipts:
                    raise ValueError("Imported challenge receipts require their original baseline")
                base = claimed
                baselines.append((group_id, base))
            else:
                base = saved[0]
                if not integer(base, claimed):
                    raise ValueError("Imported challenge baseline exceeds saved progress")
        if receipts != [(i,) for i in range(base + 1, claimed + 1)]:
            raise ValueError("Challenge receipts do not match saved contiguous steps")
        if imported:
            progress = progress_value(profile, group["condition"])
        elif group["condition"] == "owned_heroes":
            progress = len(user["Characters"])
        elif group["condition"] == "hero_draws":
            progress = profile["UserRecord"]["SummonCharacterCount"]
        else:
            gold = [a for a in user["Assets"] if a["Id"] == 70001]
            if len(gold) != 1 or any(
                type(gold[0].get(k)) is not int or not 0 <= gold[0][k] <= bound
                for k, bound in (("Amount", 0x7FFFFFFF), ("Spent", 0x7FFFFFFFFFFFFFFF))
            ):
                raise ValueError("Invalid saved gold collection progress")
            progress = min(gold[0]["Amount"] + gold[0]["Spent"], 0x7FFFFFFF)
        if type(progress) is not int or progress < 0:
            raise ValueError("Invalid saved challenge progress")
        if not claimed and progress < group["steps"][0]["threshold"]:
            raise ValueError("Complete every requested challenge before claiming the batch")
        target = claimed
        for number in range(claimed + 1, len(group["steps"]) + 1):
            step = group["steps"][number - 1]
            if progress < step["threshold"]:
                break
            new_steps.append((group_id, number, step["rewards"]))
            target = number
            if not all_steps:
                break
        targets[str(group_id)] = target

    assets = {a["Id"]: a for a in user["Assets"]}
    if imported and len(assets) != len(user["Assets"]):
        raise ValueError("Imported challenge asset IDs must be unambiguous")
    notices = []
    receipts = []
    for group_id, number, rewards in new_steps:
        granted = []
        for reward in rewards:
            granted.append(grant_reward(user, assets, reward))
        notices.extend(granted)
        receipts.append((group_id, number, json.dumps(granted, separators=(",", ":"))))
    if receipts:
        if imported and (user["Cas"] == MAX_LONG or mission["Cas"] == MAX_LONG):
            raise ValueError("Imported challenge revision overflow")
        claims.update(targets)
        user["Cas"] += 1
        mission["Cas"] += 1
    with account.db:
        for row in baselines:
            account.db.execute("INSERT INTO imported_challenge_baselines VALUES(?,?)", row)
        for row in receipts:
            account.db.execute("INSERT INTO challenge_mission_claims VALUES(?,?,?)", row)
        account.db.execute(
            "INSERT INTO challenge_mission_requests VALUES(?,?,?,?)",
            (
                operation_id,
                encoded,
                json.dumps(notices, separators=(",", ":")),
                json.dumps(targets, separators=(",", ":")),
            ),
        )
        if receipts:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return response(profile, notices)
