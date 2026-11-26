# SPDX-License-Identifier: Apache-2.0
"""Transactions used by story doors, NPCs, stone boards and the Hell stage UI."""

import json
import time

from guardian_tales.inventory.weapon_enhance import decimal_id
from guardian_tales.settlement.village import integer

from . import story_quests
from .campaign import STAGE_OPENED
from .story_data import load
from .story_handles import catalog, metadata

PAY_GOLD = "/stage/pay-gold"
PAY_ITEMS = "/stage/pay-items"
STONE = "/stage/insert-stone-piece"
FOLLOWER = "/stage/add-follower"
REVIVE = "/stage/revive-game-over"
RADAR = "/stage/enable-radar"
TIMER = "/stage/start-timer"
RANKINGS = "/stage/get-rankings"
PARTY = "/user/change-party-member/v2"
ROUTES = (PAY_GOLD, PAY_ITEMS, STONE, FOLLOWER, REVIVE, RADAR, TIMER, RANKINGS, PARTY)
RADAR_FLAG = 1 << 11


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS campaign_stone_pieces "
        "(stage_id INTEGER PRIMARY KEY, pieces INTEGER NOT NULL CHECK(pieces BETWEEN 0 AND 3))"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS campaign_stage_run "
        "(stage_id INTEGER PRIMARY KEY, revives INTEGER NOT NULL DEFAULT 0, timer_started INTEGER)"
    )
    for event in ("INSERT", "UPDATE", "DELETE"):
        db.execute(
            f"CREATE TRIGGER IF NOT EXISTS story_run_reset_{event} AFTER {event} ON campaign_session "
            "BEGIN DELETE FROM campaign_stage_run; END"
        )
    db.execute(
        "CREATE TABLE IF NOT EXISTS campaign_interaction_receipts "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, body TEXT NOT NULL, result TEXT)"
    )


def stone_count(db, stage_id):
    row = db.execute(
        "SELECT pieces FROM campaign_stone_pieces WHERE stage_id=?", (stage_id,)
    ).fetchone()
    return row[0] if row else 0


def spend(user, asset_ids, amount):
    if not integer(amount):
        raise ValueError("Invalid story payment amount")
    remaining = amount
    for asset_id in asset_ids:
        asset = next((r for r in user["Assets"] if r["Id"] == asset_id), None)
        if asset is None:
            continue
        if not integer(asset["Amount"], maximum=2**63 - 1):
            raise ValueError("Invalid saved currency balance")
        charge = min(remaining, asset["Amount"])
        asset["Amount"] -= charge
        asset["Spent"] += charge
        remaining -= charge
    if remaining:
        raise ValueError("Insufficient currency for story purchase")
    if amount:
        user["Cas"] += 1


def pay_items(user, items, specs, *, board=False):
    if not isinstance(items, dict) or not 1 <= len(items) <= 100:
        raise ValueError("Expected a map of owned item IDs to quantities")
    consumed = []
    for key, count in items.items():
        if not decimal_id(key) or not integer(count, minimum=1):
            raise ValueError("Invalid story item payment")
        matches = [
            (rows, row)
            for rows in (user["ItemMiscs"], user["ItemStackables"])
            for row in rows
            if row["Id"] == int(key)
        ]
        if len(matches) != 1:
            raise ValueError("Story item payment requires an owned item")
        rows, item = matches[0]
        spec = specs.get(item["ItemId"], {})
        if (
            spec.get("Type") not in {"artifact", "quest_item", "material"}
            or board
            and "stone_piece" not in spec.get("Name", "")
            or item.get("Locked")
            or not integer(item.get("Amount"), minimum=count)
        ):
            raise ValueError("Invalid, protected, or insufficient story consumable")
        item["Amount"] -= count
        if not item["Amount"]:
            rows.remove(item)
        consumed.append(item["ItemId"])
    user["Cas"] += 1
    return consumed


def insert_stone(account, profile, stage_id, item_id, tables):
    if not integer(item_id, minimum=1):
        raise ValueError("Invalid stone piece inventory ID")
    board = metadata(account.references, stage_id)
    rewards = board.get("StoneBoardItems")
    if rewards is None:
        raise ValueError("No stone board on this story map")
    pieces = stone_count(account.db, stage_id)
    if pieces == 3:
        return []
    (consumed,) = pay_items(profile["User"], {str(item_id): 1}, tables["items"], board=True)
    if not any(r.get("ItemSpecId") == consumed for r in board.get("Items", {}).values()):
        raise ValueError("Stone piece belongs to a different board")
    pieces += 1
    account.db.execute(
        "INSERT INTO campaign_stone_pieces VALUES(?,?) "
        "ON CONFLICT(stage_id) DO UPDATE SET pieces=excluded.pieces",
        (stage_id, pieces),
    )
    if pieces < 3:
        return []
    return story_quests.grant(
        account,
        profile,
        [
            {"ItemId": r["ItemSpecId"], "Amount": r["Amount"], "Level": r.get("Level", 0)}
            for r in rewards
        ],
    )["AddedItems"]


def change_party(user, index, character_id):
    ids = user["Party"]["Characters"]
    if not integer(index, maximum=3) or index > len(ids):
        raise ValueError("Invalid story party slot")
    if character_id is None:
        if index == len(ids):
            return
        if len(ids) == 1:
            raise ValueError("The story party needs a leader")
        ids.pop(index)
    else:
        if not integer(character_id, minimum=1) or not any(
            c["Id"] == character_id for c in user["Characters"]
        ):
            raise ValueError("Party member is not an owned character")
        if index < len(ids) and ids[index] == character_id:
            return
        if character_id in ids:
            raise ValueError("Duplicate story party member")
        ids[index : index + 1] = [character_id]
    user["Cas"] += 1


def execute(account, profile, route, body):
    user, progress = profile["User"], profile["UserProgress"]
    tables = catalog(account.references)
    current = account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone()
    stage_id = body.get("StageId")
    if route == PARTY:
        if set(body) != {"Index", "CharacterId"} or current is None:
            raise ValueError("A scripted party change requires a story stage")
        stage_id = current[0]
    elif route == RADAR:
        if len(body) != 1 or not set(body) <= {"StageId", "stageId", "Id", "id"}:
            raise ValueError("Expected a stage ID for radar")
        stage_id = next(iter(body.values()))
    if not integer(stage_id, minimum=1) or str(stage_id) not in load(account.references)[1]:
        raise ValueError("Unknown main story stage")
    if route in (RANKINGS, RADAR):
        if not progress["StageStates"].get(str(stage_id), 0) & STAGE_OPENED:
            raise ValueError("Open the story stage first")
    elif current != (stage_id,):
        raise ValueError("Start the requested story stage first")

    if route == PARTY:
        change_party(user, body["Index"], body["CharacterId"])
        return {}
    if route == RADAR:
        prices = tables.get("constants", {}).get("RadarPrices", [])
        spec = next((r for r in prices if r["Id"] == stage_id), None)
        if spec is None or spec.get("Currency") != "Gem":
            raise ValueError("Radar is unavailable for this story stage")
        if not progress["StageStates"][str(stage_id)] & RADAR_FLAG:
            spend(user, (70003, 70002), spec["Price"])
            progress["StageStates"][str(stage_id)] |= RADAR_FLAG
            progress["Cas"] += 1
        return {}
    if route in (STONE, PAY_ITEMS, PAY_GOLD):
        value = {PAY_ITEMS: "UseItems", PAY_GOLD: "Gold", STONE: "StonePieceItemId"}[route]
        if set(body) - {"StageId", value, "StageCustom"} or value not in body:
            raise ValueError("Malformed story purchase")
        story_quests.apply_custom(account, profile, stage_id, body.get("StageCustom"))
        if route == STONE:
            return {"AddedItems": insert_stone(account, profile, stage_id, body[value], tables)}
        if route == PAY_GOLD:
            spend(user, (70001,), body[value])
        else:
            pay_items(user, body[value], tables.get("items", {}))
        return {}
    if route == FOLLOWER:
        ident = body.get("FollowerId")
        if (
            set(body) != {"StageId", "FollowerId"}
            or not integer(ident)
            or not any(
                r["Id"] == ident and r.get("StageId") == stage_id
                for r in tables.get("followers", {}).get("Followers", [])
            )
        ):
            raise ValueError("Invalid SNS follower for this stage")
        if ident not in progress["Followers"]:
            progress["Followers"].append(ident)
            progress["Cas"] += 1
        return {}
    if set(body) != {"StageId"}:
        raise ValueError("Expected a single story stage ID")
    if route == RANKINGS:
        return {"Rankings": []}
    if route == TIMER:
        account.db.execute(
            "INSERT INTO campaign_stage_run(stage_id,timer_started) VALUES(?,?) "
            "ON CONFLICT(stage_id) DO UPDATE SET timer_started=coalesce(timer_started,excluded.timer_started)",
            (stage_id, int(time.time())),
        )
        return {}
    account.db.execute("INSERT OR IGNORE INTO campaign_stage_run(stage_id) VALUES(?)", (stage_id,))
    count = account.db.execute(
        "SELECT revives FROM campaign_stage_run WHERE stage_id=?", (stage_id,)
    ).fetchone()[0]
    costs = tables.get("constants", {}).get("ReviveCosts")
    limit = tables["revive_limits"][stage_id]
    if not costs or 0 <= limit <= count:
        raise ValueError("Revival is unavailable for this stage")
    spend(user, (70003, 70002), costs[min(count, len(costs) - 1)])
    account.db.execute(
        "UPDATE campaign_stage_run SET revives=revives+1 WHERE stage_id=?", (stage_id,)
    )
    return {}


def handle(account, route, body, operation_id):
    if route not in ROUTES or not isinstance(body, dict) or account.needs_prologue():
        raise ValueError("Invalid story interaction")
    if route == RANKINGS:
        return execute(account, account.profile(), route, body)
    if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 200:
        raise ValueError("Expected a story operation ID")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    with account.db:
        fresh = account.db.execute(
            "INSERT OR IGNORE INTO campaign_interaction_receipts VALUES(?,?,?,NULL)",
            (operation_id, route, encoded),
        ).rowcount
        profile = account.profile()
        if fresh:
            result = execute(account, profile, route, body)
            story_quests.save_profile(account, profile)
            account.db.execute(
                "UPDATE campaign_interaction_receipts SET result=? WHERE operation_id=?",
                (json.dumps(result, separators=(",", ":")), operation_id),
            )
        else:
            prior_route, prior_body, old_result = account.db.execute(
                "SELECT route,body,result FROM campaign_interaction_receipts WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if (prior_route, prior_body) != (route, encoded):
                raise ValueError("Story interaction identity already used for a different request")
            result = json.loads(old_result)
    if route == TIMER:
        return result
    if route in (PAY_GOLD, PAY_ITEMS, STONE, FOLLOWER, RADAR):
        result["UserProgress"] = profile["UserProgress"]
    if route != FOLLOWER:
        result["User"] = profile["User"]
    return result
