# SPDX-License-Identifier: Apache-2.0
"""Offline edits to the local player's identity and wallet."""

import re

from guardian_tales.account_name import owned_member, sync_member, valid_name
from guardian_tales.admin_test_items import save_profile
from guardian_tales.campaign import FREE_GEMS, RESERVE_STAMINA
from guardian_tales.challenges import allocate_reward_item
from guardian_tales.stamina_purchase import load_purchase_catalog
from guardian_tales.summon_payment import PAID_GEMS, spend_tickets
from guardian_tales.village import GOLD, INT_MAX, MAX_REVISION, integer

from .account_materials import account_materials
from .game_save import GameSaveEditor

WALLET_CAP = 100_000_000
WALLET = {
    "freeGems": (FREE_GEMS, "Free gems"),
    "paidGems": (PAID_GEMS, "Paid gems"),
    "gold": (GOLD, "Gold"),
    "coffee": (RESERVE_STAMINA, "Reserve coffee"),
}
MILEAGE = 70014
SUMMONING = {
    "mileage": (MILEAGE, "Mileage Ticket"),
    "summonControllers": (110007, "Summon Controller"),
    "selectableControllers": (110015, "Selectable Summon Controller"),
}


def normalize_tag(tag):
    if not isinstance(tag, str) or not re.fullmatch(r"#?[a-zA-Z0-9]{5}", tag):
        raise ValueError("Enter a tag of five letters or digits.")
    return tag.removeprefix("#").upper()


def account_ready(db):
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('imported_account','prologue_selection')"
        )
    }
    return any(db.execute(f"SELECT 1 FROM {table} WHERE id=1").fetchone() for table in tables)


def wallet_rows(user, ids):
    rows = {}
    if not isinstance(user.get("Assets"), list):
        raise ValueError("The saved wallet is unavailable.")
    for row in user["Assets"]:
        if isinstance(row, dict) and row.get("Id") in ids:
            if row["Id"] in rows or not integer(row.get("Amount")):
                raise ValueError("Invalid or duplicate saved wallet balance.")
            rows[row["Id"]] = row
    return rows


def set_asset(user, rows, asset_id, amount):
    if asset_id not in rows:
        rows[asset_id] = dict(Id=asset_id, Amount=0, Spent=0, MaxAdj=0, NextCharge=None)
        user["Assets"].append(rows[asset_id])
    rows[asset_id]["Amount"] = amount


def item_stacks(user, item_id):
    stacks = [item for item in user["ItemStackables"] if item["ItemId"] == item_id]
    if any(not integer(s.get("Amount")) or not integer(s.get("Id"), minimum=1) for s in stacks):
        raise ValueError("Invalid saved item stack.")
    if len({s["Id"] for s in stacks}) != len(stacks):
        raise ValueError("Duplicate saved item stack.")
    return stacks


def adjust_stacks(user, item_id, delta):
    if delta < 0:
        spend_tickets(user, item_id, -delta)
        return
    stacks = item_stacks(user, item_id)
    if stacks:
        min(stacks, key=lambda s: s["Id"])["Amount"] += delta
    else:
        item = allocate_reward_item(user, item_id)
        item["Amount"] = delta
        user["ItemStackables"].append(item)


class AccountEditor(GameSaveEditor):
    def __init__(self, database, references, catalog, tables):
        super().__init__(database)
        self.references = references
        specs = catalog.specs
        summoning = [
            dict(
                key=key,
                id=item_id,
                label=label,
                limit=min(specs[item_id].get("MaxCount", INT_MAX), INT_MAX),
            )
            for key, (item_id, label) in SUMMONING.items()
            if item_id in specs
        ]
        self.sections = {
            "summoning": summoning,
            "materials": account_materials(catalog, tables),
        }
        self.asset_ids = {asset_id for asset_id, _ in WALLET.values()} | {
            item["id"]
            for section in self.sections.values()
            for item in section
            if specs[item["id"]].get("Type") == "goods"
        }

    def snapshot(self, user, rows):
        # Older installations can still edit identity and currencies without the coffee catalog.
        coffee_cap = None
        if (self.references.directory / "stamina_purchase_catalog.json").is_file():
            coffee_cap = load_purchase_catalog(self.references)["max_storage"]
        balances = {}
        for section, items in self.sections.items():
            balances[section] = []
            for item in items:
                ident = item["id"]
                if ident in self.asset_ids:
                    amount = rows.get(ident, {}).get("Amount", 0)
                else:
                    amount = sum(stack["Amount"] for stack in item_stacks(user, ident))
                balances[section].append(dict(item, balance=amount))
        return {
            "name": user["Name"],
            "tag": user["HashTag"],
            "version": f"{user['Id']}:{user['Cas']}",
            "wallet": [
                dict(
                    key=key,
                    label=label,
                    id=asset_id,
                    balance=rows.get(asset_id, {}).get("Amount", 0),
                    limit=coffee_cap if key == "coffee" else WALLET_CAP,
                )
                for key, (asset_id, label) in WALLET.items()
            ],
            **balances,
        }

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
            return {
                **self.snapshot(user, wallet_rows(user, self.asset_ids)),
                "ready": account_ready(db),
                **self.status(),
            }

    def apply_locked(self, db, body):
        if not isinstance(body, dict) or body.keys() - {"set"} != {"version", "name", "tag", "add"}:
            raise ValueError("Reload the account and submit its identity and wallet changes.")
        if not account_ready(db):
            raise ValueError("Complete the prologue or import an account before editing.")
        profile = self.profile(db)
        user = profile["User"]
        rows = wallet_rows(user, self.asset_ids)
        current = self.snapshot(user, rows)
        if body["version"] != current["version"]:
            return 409, {"error": "Your save changed. Reload the account before applying."}
        identity = {}
        if body["name"] != user["Name"]:
            if not valid_name(body["name"]):
                raise ValueError(
                    "Enter a nickname of 2–10 UTF-16 units without control characters."
                )
            identity["Name"] = body["name"]
        if body["tag"] != user["HashTag"]:
            tag = normalize_tag(body["tag"])
            if tag != user["HashTag"]:
                identity["HashTag"] = tag
        additions = body["add"]
        if not isinstance(additions, dict) or additions.keys() - WALLET.keys():
            raise ValueError("Choose a supported wallet balance.")
        changed = bool(identity)
        for item in current["wallet"]:
            amount = additions.get(item["key"], 0)
            if not integer(amount):
                raise ValueError("Enter a nonnegative whole amount to add.")
            if amount == 0:
                continue
            if item["limit"] is None or item["balance"] + amount > item["limit"]:
                raise ValueError(f"{item['label']} would exceed the available storage.")
            set_asset(user, rows, item["id"], item["balance"] + amount)
            changed = True
        totals = body.get("set", {})
        available = {item["key"]: item for section in self.sections for item in current[section]}
        if not isinstance(totals, dict) or totals.keys() - available.keys():
            raise ValueError("Choose a supported account balance.")
        for key, total in totals.items():
            item = available[key]
            if not integer(total, item["limit"]):
                raise ValueError(
                    f"Enter a whole {item['label']} balance from 0 to {item['limit']:,}."
                )
            if total == item["balance"]:
                continue
            if item["id"] in self.asset_ids:
                set_asset(user, rows, item["id"], total)
            else:
                adjust_stacks(user, item["id"], total - item["balance"])
            changed = True
        if changed:
            if user["Cas"] == MAX_REVISION:
                raise ValueError("The save revision has reached its limit.")
            if identity:
                sync_member(owned_member(profile), identity)
                user.update(identity)
            save_profile(db, profile)
        return 200, self.snapshot(user, rows)
