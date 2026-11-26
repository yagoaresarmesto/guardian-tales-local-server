# SPDX-License-Identifier: Apache-2.0
"""Quantity edits for owned stacks, restricted to the active section's catalog types."""

from guardian_tales.administration.admin_test_items import save_profile
from guardian_tales.settlement.village import INT_MAX, MAX_REVISION, integer

from .game_save import GameSaveEditor

CONSUMABLES = {
    "ticket": "Tickets & stones",
    "evolve_stone": "Evolution stones",
    "material": "Awakening materials",
}


HAMMERS = {"enhancehammer": "Strengthening Hammer", "limitbreakhammer": "Limit Breaking Hammer"}
RARITIES = ("Normal", "Rare", "Unique", "Legend", "Epic", "Myth")


class StackQuantityEditor(GameSaveEditor):
    def __init__(self, database, catalog, categories):
        super().__init__(database)
        self.catalog = catalog
        self.categories = categories

    def info(self):
        with self.reader() as db:
            user = self.profile(db)["User"]
        return dict(rows=self.rows(user), hasIcons=self.catalog.has_icons, **self.status())

    def rows(self, user):
        rows = []
        for item in user["ItemStackables"]:
            key = item["ItemId"]
            spec = self.catalog.specs.get(key, {})
            kind = spec.get("Type")
            group = self.categories.get(kind)
            if not group or not integer(item["Amount"], minimum=1):
                continue
            row = {
                "id": item["Id"],
                "spec": key,
                "category": group,
                "amount": item["Amount"],
                "maximum": spec.get("MaxCount", INT_MAX),
                "version": self.option_version(user, item, "Amount"),
            }
            fallback = (spec.get("Name") or f"Item {key}").replace("_", " ").title()
            if kind in HAMMERS:
                rarity, level = spec.get("Rarity"), spec.get("Level")
                rarity_name = RARITIES[rarity] if integer(rarity, len(RARITIES) - 1) else ""
                fallback = f"{rarity_name} {group}".strip() if kind == "limitbreakhammer" else group
                row.update(
                    kind="enhance",
                    grade=rarity,
                    rarityName=rarity_name,
                    stars=rarity + 1 if rarity_name else None,
                    level=level + 1 if integer(level) else None,
                    locked=item.get("Locked") is True,
                    enhanceExp=self.catalog.equipment.hammer_exp.get(str(key)),
                )
            row["name"] = self.catalog.names.get(key) or fallback
            rows.append(row)
        # Keep the save's order within each section, including hero-specific stones.
        order = {name: i for i, name in enumerate(self.categories.values())}
        rows.sort(key=lambda r: order[r["category"]])
        return rows

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
        if spec.get("Type") not in self.categories or not integer(item["Amount"], minimum=1):
            raise ValueError("Select an owned stack from this inventory section.")
        if not integer(body["amount"], spec.get("MaxCount", INT_MAX), 1):
            raise ValueError("The quantity exceeds the limit for this stack.")
        if item["Amount"] != body["amount"]:
            if not integer(user["Cas"], MAX_REVISION - 1):
                raise ValueError("The game save revision has reached its limit.")
            item["Amount"] = body["amount"]
            save_profile(db, profile)
        return 200, {"amount": item["Amount"], "version": self.option_version(user, item, "Amount")}
