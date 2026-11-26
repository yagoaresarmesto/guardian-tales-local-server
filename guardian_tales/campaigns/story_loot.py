# SPDX-License-Identifier: Apache-2.0
"""Grant story pickups from stage definitions and keep the exact result for retries."""

import json
import secrets

from guardian_tales.rewards.challenges import allocate_reward_item, grant_reward
from guardian_tales.settlement.village import integer

from .campaign import FIRST_STAGE_ID, FIRST_STAGE_ITEMS
from .story_handles import catalog, map_events, metadata, stage_handles


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS campaign_loot "
        "(stage_id INTEGER, category INTEGER, handle INTEGER, added TEXT NOT NULL, "
        "PRIMARY KEY(stage_id, category, handle))"
    )


def grant_item(account, user, spec_id, amount=1, level=0):
    """Apply one static reward to the in-memory user; caller owns revision and transaction."""
    if not integer(spec_id, minimum=1) or not integer(amount, minimum=1) or not integer(level):
        raise ValueError("Invalid story item, level or quantity")
    tables = catalog(account.references)
    items = tables.get("items", {})
    assets = {row["Id"]: row for row in user["Assets"]}
    spec = items.get(spec_id, {})
    kind = spec.get("Type")
    if spec_id in assets or kind == "goods":
        if spec_id not in assets:
            assets[spec_id] = dict(Id=spec_id, Amount=0, Spent=0, MaxAdj=0, NextCharge=None)
            user["Assets"].append(assets[spec_id])
        return [grant_reward(user, assets, {"item_id": spec_id, "amount": amount})]
    if kind in {"material", "enhancehammer", "ticket", "limitbreakhammer"}:
        # Hammer grade/level is intrinsic to its item specification.
        return [
            grant_reward(
                user, assets, {"item_id": spec_id, "amount": amount, "storage": "stackable"}
            )
        ]
    if amount > 100:
        raise ValueError("Too many individual story reward items")
    if kind == "gachaitem" and spec.get("BoxType") == "Weapon":
        pool = [
            v["Id"]
            for v in items.values()
            if v["Type"] == "weapon"
            and v.get("Summonable") is True
            and v.get("Limited") is False
            and v.get("Rarity") == spec.get("Rarity")
            and spec.get("WeaponType") in ("All", v.get("WeaponType"))
        ]
        if not pool:
            raise ValueError("No matching equipment in the story reward box")
        # Offline practice uses a uniform draw within the source box type and rarity.
        return [
            item
            for _ in range(amount)
            for item in grant_item(account, user, secrets.choice(pool), level=level)
        ]
    if kind == "merch":
        levels = tables["merch_levels"]
        rarity = spec["OriginRarity"]
        if not integer(rarity, 2) or level > len(levels):
            raise ValueError("Unknown story merch level or rarity")
        experience = sum(row["ExpNeeded"][rarity] for row in levels[:level])
        result = []
        for _ in range(amount):
            row = allocate_reward_item(user, spec_id)
            row.update(Amount=1, Experience=experience)
            user["ItemMiscs"].append(row)
            result.append(row.copy())
        return result
    if kind == "weapon":
        levels = tables["weapon_levels"]
        if level > len(levels):
            raise ValueError("Invalid story equipment level")
        experience = levels[level - 1]["TotalExps"] if level else 0
        result = []
        for _ in range(amount):
            row = allocate_reward_item(user, spec_id)
            row["Experience"] = experience
            user["ItemWeapons"].append(row)
            result.append(row.copy())
        return result
    if kind not in {"costume", "equipcostume", "artifact", "orb", "quest_item"}:
        raise ValueError("Unknown story inventory item type")
    existing = next((it for it in user["ItemMiscs"] if it["ItemId"] == spec_id), None)
    if existing is None:
        existing = allocate_reward_item(user, spec_id)
        existing["Amount"] = amount
        user["ItemMiscs"].append(existing)
    elif kind == "quest_item":
        if not integer(existing.get("Amount"), 0x7FFFFFFF - amount):
            raise ValueError("Story quest-item balance overflow")
        existing["Amount"] += amount
    return [dict(existing, Amount=amount)]


def pickup(account, request, category):
    from .story_quests import apply_custom

    chest = category == 5
    field = "TreasureBoxKey" if chest else "StageItemKey"
    if (
        not isinstance(request, dict)
        or set(request) - {"StageId", field, "StageCustom"}
        or not integer(request.get("StageId"), minimum=1)
        or not isinstance(request.get(field), str)
    ):
        raise ValueError("Invalid story pickup")
    stage_id, key = request["StageId"], request[field]
    if account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
        stage_id,
    ):
        raise ValueError("Start the phase before collecting its items")
    legacy = stage_id == FIRST_STAGE_ID
    if legacy:
        if chest and key == "mole_glove_box":
            index, item_id, inventory = 1, 30017, "ItemMiscs"
        elif not chest and key in FIRST_STAGE_ITEMS:
            index, item_id, inventory = FIRST_STAGE_ITEMS[key]
        else:
            raise ValueError("Unknown first-phase item or treasure")
    else:
        index = stage_handles(account.references, stage_id).get(str(category), {}).get(key)
        if index is None:
            raise ValueError("Unknown story stage item or treasure")
    receipt_key = f"treasure:{key}" if chest else key
    with account.db:
        saved = account.db.execute(
            "SELECT added FROM campaign_loot WHERE stage_id=? AND category=? AND handle=?",
            (stage_id, category, index),
        ).fetchone()
        profile = account.profile()
        user = profile["User"]
        changed = False
        if saved:
            added = json.loads(saved[0])
        elif account.db.execute(
            "SELECT 1 FROM campaign_progress WHERE stage_id=? AND category=? AND key=? AND value='true'",
            (stage_id, category, index),
        ).fetchone():
            # Older saves or the completed campaign profile already own this pickup.
            added = []
            if legacy:
                old = account.db.execute(
                    "SELECT inventory_id FROM campaign_item_receipts WHERE stage_id=? AND item_key=?",
                    (stage_id, receipt_key),
                ).fetchone()
                if old:
                    added = [
                        r for r in user[inventory] if r["Id"] == old[0] and r["ItemId"] == item_id
                    ]
        else:
            if legacy:
                item = allocate_reward_item(user, item_id)
                user[inventory].append(item)
                added = [item]
                account.db.execute(
                    "INSERT INTO campaign_item_receipts VALUES(?,?,?)",
                    (stage_id, receipt_key, item["Id"]),
                )
            else:
                field_name = "Boxes" if chest else "Items"
                spec = metadata(account.references, stage_id).get(field_name, {}).get(key)
                events = map_events(account.references, stage_id, required=spec is None)
                placed = events.get("boxes" if chest else "items", {}).get(key)
                if spec is None:
                    spec = placed
                # Script-only map objects can publish an event without an inventory grant.
                rewards = spec if chest else [spec] if spec else []
                added = []
                for reward in rewards or []:
                    if not chest and placed and placed.get("NotForInventory"):
                        continue
                    added.extend(
                        grant_item(
                            account,
                            user,
                            reward["ItemSpecId"],
                            reward.get("Amount", 1),
                            reward.get("Level", 0),
                        )
                    )
            account.db.execute(
                "INSERT INTO campaign_progress VALUES(?,?,?,?) ON CONFLICT(stage_id,category,key) DO UPDATE SET value=excluded.value",
                (stage_id, category, index, "true"),
            )
            account.db.execute(
                "INSERT INTO campaign_loot VALUES(?,?,?,?)",
                (stage_id, category, index, json.dumps(added)),
            )
            if added:
                user["Cas"] += 1
                changed = True
        if apply_custom(account, profile, stage_id, request.get("StageCustom")) or changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    if chest:
        return {"User": user, "AddedItems": added}
    return {"User": user, "AddedItem": added[0] if added else None}
