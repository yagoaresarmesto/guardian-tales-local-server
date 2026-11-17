# SPDX-License-Identifier: Apache-2.0
"""Catalog Festival shop exclusions and atomic asset/stackable point redemptions."""

import json

from .items import inventory_item


def load_shop_catalog(references):
    value = references.json("festival_shop_catalog.json")
    if (
        not isinstance(value, dict)
        or set(value) != {"season_id", "items"}
        or type(value["season_id"]) is not int
        or not 1 <= value["season_id"] <= 0x7FFFFFFF
        or not isinstance(value["items"], dict)
        or not 1 <= len(value["items"]) <= 1000
    ):
        raise ValueError("Invalid Festival shop catalog")
    for key, item in value["items"].items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or key.startswith("0")
            or len(key) > 10
            or int(key) > 0x7FFFFFFF
            or not isinstance(item, dict)
            or set(item) != {"limit", "owned_misc_ids", "price", "rewards"}
            or type(item["price"]) is not int
            or not 1 <= item["price"] <= 0x7FFFFFFF
            or type(item["limit"]) is not int
            or not 0 <= item["limit"] <= 0x7FFFFFFF
            or not isinstance(item["owned_misc_ids"], list)
            or len(item["owned_misc_ids"]) > 32
            or any(type(i) is not int or not 1 <= i <= 0x7FFFFFFF for i in item["owned_misc_ids"])
            or len(set(item["owned_misc_ids"])) != len(item["owned_misc_ids"])
            or not isinstance(item["rewards"], list)
            or not 1 <= len(item["rewards"]) <= 32
        ):
            raise ValueError("Invalid Festival shop exclusion rule")
        for reward in item["rewards"]:
            if (
                not isinstance(reward, dict)
                or set(reward) != {"item_id", "amount", "storage"}
                or type(reward["item_id"]) is not int
                or not 1 <= reward["item_id"] <= 0x7FFFFFFF
                or type(reward["amount"]) is not int
                or not 1 <= reward["amount"] <= 0x7FFFFFFF
                or reward["storage"] not in ("asset", "stackable", "unsupported")
            ):
                raise ValueError("Invalid Festival shop reward")
    return value


def shop_profile(account, catalog):
    profile = account.profile()
    festival = profile["UserFestivalPass"]
    if (
        type(festival["SeasonId"]) is not int
        or festival["SeasonId"] not in (0, catalog["season_id"])
        or type(festival["Point"]) is not int
        or not 0 <= festival["Point"] <= 0x7FFFFFFF
        or type(festival["Experience"]) is not int
        or not 0 <= festival["Experience"] <= 0x7FFFFFFF
        or type(festival["PassType"]) is not int
        or festival["PassType"] not in (0, 1)
        or not isinstance(festival["Purchase"], dict)
    ):
        raise ValueError("Unsupported saved Festival Pass season/state")
    if festival["SeasonId"] == 0 and (
        festival["Point"]
        or festival["Experience"]
        or festival["PassType"]
        or festival["Purchase"]
        or festival["Missions"]
        or any(type(v) is not int or v != 0 for v in festival["Claimed"].values())
    ):
        raise ValueError("An uninitialized Festival season cannot contain progress")
    purchases = festival["Purchase"]
    if any(
        key not in catalog["items"] or type(count) is not int or not 0 <= count <= 0x7FFFFFFF
        for key, count in purchases.items()
    ):
        raise ValueError("Invalid or unconfigured Festival purchase history")
    inventory = profile["User"]["ItemMiscs"]
    if not isinstance(inventory, list) or any(
        not isinstance(item, dict)
        or type(item.get("ItemId")) is not int
        or not 1 <= item["ItemId"] <= 0x7FFFFFFF
        or type(item.get("Amount")) is not int
        or not 0 <= item["Amount"] <= 0x7FFFFFFF
        for item in inventory
    ):
        raise ValueError("Invalid saved persistent-item inventory")
    return profile


def excluded_items(profile, catalog):
    inventory = profile["User"]["ItemMiscs"]
    purchases = profile["UserFestivalPass"]["Purchase"]
    owned = {i["ItemId"] for i in inventory if i["Amount"] > 0}
    excluded = []
    for key, item in catalog["items"].items():
        if (
            item["limit"]
            and purchases.get(key, 0) >= item["limit"]
            or any(i in owned for i in item["owned_misc_ids"])
        ):
            excluded.append(int(key))
    return sorted(excluded)


def check_not_redeemable(account, request):
    if request is not None and request != {} or account.needs_prologue():
        raise ValueError("Festival shop availability accepts no parameters after the prologue")
    catalog = load_shop_catalog(account.references)
    return {"NotRedeemable": excluded_items(shop_profile(account, catalog), catalog)}


def redemption_response(profile, rewards):
    return {
        "User": profile["User"],
        "UserFestivalPass": profile["UserFestivalPass"],
        "AddedItems": rewards,
    }


def redeem_points(account, request, operation_id):
    if (
        not isinstance(request, dict)
        or set(request) != {"shopItemId", "amount"}
        or type(request["shopItemId"]) is not int
        or not 1 <= request["shopItemId"] <= 0x7FFFFFFF
        or type(request["amount"]) is not int
        or not 1 <= request["amount"] <= 1000
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid Festival redemption or request identity")
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
    saved = account.db.execute(
        "SELECT request,rewards FROM festival_shop_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if saved:
        if saved[0] != encoded:
            raise ValueError("Festival request identity was already used for another redemption")
        return redemption_response(account.profile(), json.loads(saved[1]))
    catalog = load_shop_catalog(account.references)
    profile = shop_profile(account, catalog)
    user, festival = profile["User"], profile["UserFestivalPass"]
    key = str(request["shopItemId"])
    if festival["SeasonId"] != catalog["season_id"] or key not in catalog["items"]:
        raise ValueError("Festival redemption requires a configured active-season item")
    item = catalog["items"][key]
    count = request["amount"]
    purchased = festival["Purchase"].get(key, 0)
    if request["shopItemId"] in excluded_items(profile, catalog) or (
        item["limit"] and purchased + count > item["limit"]
    ):
        raise ValueError("Festival redemption is owned or exceeds its purchase limit")
    cost = item["price"] * count
    if cost > festival["Point"] or purchased + count > 0x7FFFFFFF:
        raise ValueError("Not enough Festival points or purchase counter overflow")
    if any(r["storage"] == "unsupported" for r in item["rewards"]):
        raise ValueError("This Festival reward's inventory/progression type is not implemented")
    assets = {a["Id"]: a for a in user["Assets"]}
    rewards = []
    for reward in item["rewards"]:
        item_id, amount = reward["item_id"], reward["amount"] * count
        if reward["storage"] == "asset":
            if item_id not in assets:
                raise ValueError("The saved account is missing a Festival reward asset")
            target = assets[item_id]
            inventory_id = 0
        else:
            if item_id in assets:
                raise ValueError("Festival asset rewards cannot be stored as inventory items")
            target = next((i for i in user["ItemStackables"] if i["ItemId"] == item_id), None)
            if target is None:
                if (
                    type(user["ItemIdCounter"]) is not int
                    or not 0 <= user["ItemIdCounter"] < 0x7FFFFFFF
                ):
                    raise ValueError("Festival inventory counter overflow")
                user["ItemIdCounter"] += 1
                target = inventory_item(user["ItemIdCounter"], item_id)
                target["Amount"] = 0
                user["ItemStackables"].append(target)
            inventory_id = target["Id"]
        if type(target["Amount"]) is not int or not 0 <= target["Amount"] <= 0x7FFFFFFF - amount:
            raise ValueError("Festival reward balance overflow")
        target["Amount"] += amount
        rewards.append({"Id": inventory_id, "ItemId": item_id, "Amount": amount})
    festival["Point"] -= cost
    festival["Purchase"][key] = purchased + count
    festival["Cas"] += 1
    user["Cas"] += 1
    audit = {
        "SeasonId": festival["SeasonId"],
        "ShopItemId": request["shopItemId"],
        "Amount": count,
        "SpentPoint": cost,
    }
    with account.db:
        account.db.execute(
            "INSERT INTO festival_shop_requests VALUES(?,?,?,?)",
            (
                operation_id,
                encoded,
                json.dumps(rewards, separators=(",", ":")),
                json.dumps(audit, separators=(",", ":")),
            ),
        )
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
    return redemption_response(profile, rewards)
