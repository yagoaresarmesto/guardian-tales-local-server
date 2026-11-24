# SPDX-License-Identifier: Apache-2.0
"""Offline edits to the local player's identity and wallet."""

import re

from guardian_tales.account_name import owned_member, sync_member, valid_name
from guardian_tales.admin_test_items import save_profile
from guardian_tales.campaign import FREE_GEMS, RESERVE_STAMINA
from guardian_tales.stamina_purchase import load_purchase_catalog
from guardian_tales.summon_payment import PAID_GEMS
from guardian_tales.village import GOLD, MAX_REVISION, integer

from .game_save import GameSaveEditor

WALLET_CAP = 100_000_000
WALLET = {
    "freeGems": (FREE_GEMS, "Free gems"),
    "paidGems": (PAID_GEMS, "Paid gems"),
    "gold": (GOLD, "Gold"),
    "coffee": (RESERVE_STAMINA, "Reserve coffee"),
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


def wallet_rows(user):
    rows = {}
    if not isinstance(user.get("Assets"), list):
        raise ValueError("The saved wallet is unavailable.")
    ids = {asset_id for asset_id, _ in WALLET.values()}
    for row in user["Assets"]:
        if isinstance(row, dict) and row.get("Id") in ids:
            if row["Id"] in rows or not integer(row.get("Amount")):
                raise ValueError("Invalid or duplicate saved wallet balance.")
            rows[row["Id"]] = row
    return rows


class AccountEditor(GameSaveEditor):
    def __init__(self, database, references):
        super().__init__(database)
        self.references = references

    def snapshot(self, user, rows):
        # Older installations can still edit identity and currencies without the coffee catalog.
        coffee_cap = None
        if (self.references.directory / "stamina_purchase_catalog.json").is_file():
            coffee_cap = load_purchase_catalog(self.references)["max_storage"]
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
        }

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
            return {
                **self.snapshot(user, wallet_rows(user)),
                "ready": account_ready(db),
                **self.status(),
            }

    def apply_locked(self, db, body):
        if not isinstance(body, dict) or set(body) != {"version", "name", "tag", "add"}:
            raise ValueError("Reload the account and submit its identity and wallet changes.")
        if not account_ready(db):
            raise ValueError("Complete the prologue or import an account before editing.")
        profile = self.profile(db)
        user = profile["User"]
        rows = wallet_rows(user)
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
            asset_id = item["id"]
            if asset_id not in rows:
                rows[asset_id] = dict(Id=asset_id, Amount=0, Spent=0, MaxAdj=0, NextCharge=None)
                user["Assets"].append(rows[asset_id])
            rows[asset_id]["Amount"] += amount
            changed = True
        if changed:
            if user["Cas"] == MAX_REVISION:
                raise ValueError("The save revision has reached its limit.")
            if identity:
                sync_member(owned_member(profile), identity)
                user.update(identity)
            save_profile(db, profile)
        return 200, self.snapshot(user, rows)
