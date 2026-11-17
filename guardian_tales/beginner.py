# SPDX-License-Identifier: Apache-2.0
"""Atomic beginner-reward batches with per-mission flags and persistent receipts."""

import base64
import json

from .campaign import CHARGED_STAMINA, FIRST_STAGE_ID, FREE_GEMS, RESERVE_STAMINA, STAGE_CLEARED
from .items import inventory_item
from .missions import BEGINNER_REWARDS, STAMINA_MISSION_SPEND


def load_beginner_catalog(references):
    if not (references.directory / "beginner_mission_catalog.json").is_file():
        return {}
    value = references.json("beginner_mission_catalog.json")
    rows = value.get("missions") if isinstance(value, dict) else None
    if not isinstance(rows, dict) or not 1 <= len(rows) <= 1000:
        raise ValueError("Invalid external beginner mission catalog")
    for key, row in rows.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 4
            or not 1 <= int(key) <= 8191
            or int(key) in BEGINNER_REWARDS
            or not isinstance(row, dict)
            or set(row) != {"summon_count", "rewards"}
            or type(row["summon_count"]) is not int
            or not 1 <= row["summon_count"] <= 1000000
            or not isinstance(row["rewards"], list)
            or not 1 <= len(row["rewards"]) <= 32
        ):
            raise ValueError("Invalid beginner summon milestone")
        for reward in row["rewards"]:
            if (
                not isinstance(reward, dict)
                or set(reward) != {"item_id", "amount", "storage"}
                or type(reward["item_id"]) is not int
                or not 1 <= reward["item_id"] <= 0x7FFFFFFF
                or type(reward["amount"]) is not int
                or not 1 <= reward["amount"] <= 0x7FFFFFFF
                or reward["storage"] not in ("asset", "stackable")
            ):
                raise ValueError("Only verified asset/stackable beginner rewards are supported")
    return rows


def eligible(account, profile, mission_id, catalog):
    user = profile["User"]
    progress = profile["UserProgress"]
    if mission_id == 0:
        return bool(progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED)
    if mission_id == 1:
        knight = next((c for c in user["Characters"] if c["Id"] == 1), None)
        trained = account.db.execute(
            "SELECT experience FROM first_knight_training WHERE character_id=1"
        ).fetchone()
        return trained == (37,) and knight is not None and knight["Experience"] >= 37
    if mission_id == 9:
        return (
            sum(a["Spent"] for a in user["Assets"] if a["Id"] in (CHARGED_STAMINA, RESERVE_STAMINA))
            >= STAMINA_MISSION_SPEND
        )
    count = profile["UserRecord"]["SummonCharacterCount"]
    return type(count) is int and count >= catalog[str(mission_id)]["summon_count"]


def claim_beginner(account, request):
    catalog = load_beginner_catalog(account.references)
    if (
        not isinstance(request, dict)
        or set(request) != {"missionIds"}
        or not isinstance(request["missionIds"], list)
        or not 1 <= len(request["missionIds"]) <= 512
        or any(
            type(i) is not int or i not in BEGINNER_REWARDS and str(i) not in catalog
            for i in request["missionIds"]
        )
        or account.needs_prologue()
    ):
        raise ValueError("Only known beginner missions can be claimed after the prologue")
    ids = list(dict.fromkeys(request["missionIds"]))
    profile = account.profile()
    user = profile["User"]
    mission = profile["UserMission"]
    bits = bytearray(base64.b64decode(mission["GuideClaimed"], validate=True))
    saved = {}
    for mission_id in ids:
        index, bit = divmod(mission_id, 8)
        marked = index < len(bits) and bool(bits[index] & (1 << bit))
        receipt = account.db.execute(
            "SELECT rewards FROM beginner_mission_claims WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if bool(receipt) != marked:
            raise ValueError("Mission receipt does not match saved claim flags")
        if not eligible(account, profile, mission_id, catalog):
            raise ValueError("Complete every requested beginner mission before claiming the batch")
        if receipt:
            saved[mission_id] = json.loads(receipt[0])
    new = {}
    assets = {a["Id"]: a for a in user["Assets"]}
    for mission_id in ids:
        if mission_id in saved:
            continue
        if mission_id in BEGINNER_REWARDS:
            rewards = [
                {
                    "item_id": i,
                    "amount": n,
                    "storage": "asset" if i in (FREE_GEMS, RESERVE_STAMINA) else "stackable",
                }
                for i, n in BEGINNER_REWARDS[mission_id]
            ]
        else:
            rewards = catalog[str(mission_id)]["rewards"]
        notices = []
        for reward in rewards:
            item_id, amount = reward["item_id"], reward["amount"]
            if reward["storage"] == "asset":
                if item_id not in assets:
                    raise ValueError("The saved account is missing a reward asset")
                asset = assets[item_id]
                if asset["Amount"] + amount > 0x7FFFFFFF:
                    raise ValueError("Beginner reward balance overflow")
                asset["Amount"] += amount
                inventory_id = 0
            else:
                if item_id in assets:
                    raise ValueError("An asset reward cannot be stored as an inventory item")
                item = next((i for i in user["ItemStackables"] if i["ItemId"] == item_id), None)
                if item is None:
                    if user["ItemIdCounter"] >= 0x7FFFFFFF:
                        raise ValueError("Inventory counter overflow")
                    user["ItemIdCounter"] += 1
                    item = inventory_item(user["ItemIdCounter"], item_id)
                    item["Amount"] = 0
                    user["ItemStackables"].append(item)
                if item["Amount"] + amount > 0x7FFFFFFF:
                    raise ValueError("Beginner reward stack overflow")
                item["Amount"] += amount
                inventory_id = item["Id"]
            notices.append({"Id": inventory_id, "ItemId": item_id, "Amount": amount})
        index, bit = divmod(mission_id, 8)
        bits.extend(bytes(max(0, index + 1 - len(bits))))
        bits[index] |= 1 << bit
        new[mission_id] = notices
    if new:
        mission["GuideClaimed"] = base64.b64encode(bits).decode("ascii")
        mission["Cas"] += 1
        user["Cas"] += 1
        with account.db:
            for mission_id, rewards in new.items():
                account.db.execute(
                    "INSERT INTO beginner_mission_claims VALUES(?,?)",
                    (mission_id, json.dumps(rewards, separators=(",", ":"))),
                )
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    notices = [notice for i in ids for notice in (saved[i] if i in saved else new[i])]
    return {"User": user, "UserMission": mission, "AddedItems": notices}
