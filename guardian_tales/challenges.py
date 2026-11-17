# SPDX-License-Identifier: Apache-2.0
"""Contiguous catalog challenge steps with atomic batch and per-request receipts."""

import json


def load_challenge_catalog(references):
    value = references.json("challenge_mission_catalog.json")
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
            or group["condition"] not in ("owned_heroes", "hero_draws", "collected_gold")
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
                    or set(reward) != {"item_id", "amount"}
                    or type(reward["item_id"]) is not int
                    or not 1 <= reward["item_id"] <= 0x7FFFFFFF
                    or type(reward["amount"]) is not int
                    or not 1 <= reward["amount"] <= 0x7FFFFFFF
                ):
                    raise ValueError("Invalid challenge asset reward")
    if total > 10000:
        raise ValueError("Challenge catalog has too many steps")
    return groups


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
    catalog = load_challenge_catalog(account.references)
    if any(str(g) not in catalog for g in ids):
        raise ValueError("Only configured challenge groups can be claimed")
    profile = account.profile()
    user, mission = profile["User"], profile["UserMission"]
    claims = mission["ChallengeClaimed"]
    if not isinstance(claims, dict) or not isinstance(user["Characters"], list):
        raise ValueError("Invalid saved challenge state")
    targets = {}
    new_steps = []
    for group_id in ids:
        group = catalog[str(group_id)]
        claimed = claims.get(str(group_id), 0)
        if type(claimed) is not int or not 0 <= claimed <= len(group["steps"]):
            raise ValueError("Saved challenge step is outside the configured group")
        receipts = account.db.execute(
            "SELECT step FROM challenge_mission_claims WHERE group_id=? ORDER BY step", (group_id,)
        ).fetchall()
        if receipts != [(i,) for i in range(1, claimed + 1)]:
            raise ValueError("Challenge receipts do not match saved contiguous steps")
        if group["condition"] == "owned_heroes":
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
    notices = []
    receipts = []
    for group_id, number, rewards in new_steps:
        granted = []
        for reward in rewards:
            item_id, amount = reward["item_id"], reward["amount"]
            if item_id not in assets:
                raise ValueError("Only existing asset rewards are supported for challenge steps")
            asset = assets[item_id]
            if type(asset["Amount"]) is not int or not 0 <= asset["Amount"] <= 0x7FFFFFFF - amount:
                raise ValueError("Challenge reward balance overflow or invalid saved asset")
            asset["Amount"] += amount
            granted.append({"Id": 0, "ItemId": item_id, "Amount": amount})
        notices.extend(granted)
        receipts.append((group_id, number, json.dumps(granted, separators=(",", ":"))))
    if receipts:
        claims.update(targets)
        user["Cas"] += 1
        mission["Cas"] += 1
    with account.db:
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
