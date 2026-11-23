# SPDX-License-Identifier: Apache-2.0
"""Owned consumable stacks, classified by their game catalog entry."""

from guardian_tales.admin_test_items import save_profile
from guardian_tales.village import INT_MAX, MAX_REVISION, integer

from .game_save import GameSaveEditor

CATEGORIES = {
    "ticket": "Tickets & stones",
    "evolve_stone": "Evolution stones",
    "material": "Awakening materials",
}


def category(spec):
    return CATEGORIES.get(spec.get("Type"))


class ConsumableEditor(GameSaveEditor):
    def __init__(self, database, catalog):
        super().__init__(database)
        self.catalog = catalog

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
        rows = []
        for item in user["ItemStackables"]:
            key = item["ItemId"]
            spec = self.catalog.specs.get(key, {})
            group = category(spec)
            if not group or not integer(item["Amount"], minimum=1):
                continue
            rows.append(
                {
                    "id": item["Id"],
                    "spec": key,
                    "name": self.catalog.names.get(key) or spec["Name"].replace("_", " ").title(),
                    "category": group,
                    "amount": item["Amount"],
                    "maximum": spec.get("MaxCount", INT_MAX),
                    "version": self.option_version(user, item, "Amount"),
                }
            )
        # Keep the save's order within each section, including hero-specific stones.
        order = {name: i for i, name in enumerate(CATEGORIES.values())}
        rows.sort(key=lambda r: order[r["category"]])
        return dict(rows=rows, hasIcons=self.catalog.has_icons, **self.status())

    def apply_locked(self, db, body):
        if (
            not isinstance(body, dict)
            or set(body) != {"id", "version", "amount"}
            or not integer(body["id"], minimum=1)
            or not isinstance(body["version"], str)
            or not integer(body["amount"], minimum=1)
        ):
            raise ValueError("Choose an owned stack and enter a positive whole quantity.")
        profile = self.profile(db)
        user = profile["User"]
        matches = [r for r in user["ItemStackables"] if r["Id"] == body["id"]]
        if len(matches) != 1 or self.option_version(user, matches[0], "Amount") != body["version"]:
            return 409, {"error": "This stack changed. Review its current quantity."}
        item = matches[0]
        spec = self.catalog.specs.get(item["ItemId"], {})
        if not category(spec) or not integer(item["Amount"], minimum=1):
            raise ValueError("Select an owned consumable stack.")
        if not integer(body["amount"], spec.get("MaxCount", INT_MAX), 1):
            raise ValueError("The quantity exceeds the limit for this consumable.")
        if item["Amount"] != body["amount"]:
            if not integer(user["Cas"], MAX_REVISION - 1):
                raise ValueError("The game save revision has reached its limit.")
            item["Amount"] = body["amount"]
            save_profile(db, profile)
        return 200, {"amount": item["Amount"], "version": self.option_version(user, item, "Amount")}
