# SPDX-License-Identifier: Apache-2.0
"""Browse owned heroes and run the game's progression operations on the selected copy."""

import json
from bisect import bisect_right
from uuid import uuid4

from guardian_tales.accounts.account import AccountStore
from guardian_tales.accounts.snapshots import is_imported
from guardian_tales.campaigns.campaign import FIRST_STAGE_ID, STAGE_CLEARED
from guardian_tales.heroes import (
    awakening_catalog,
    hero_awakening,
    hero_blessing,
    hero_evolution,
    hero_limit_break,
    hero_myth,
    hero_reset,
    imported_training,
)
from guardian_tales.heroes.characters import owned_character
from guardian_tales.settlement.village import MAX_REVISION, integer

from .game_save import GameSaveEditor

ELEMENTS = {"None": "Basic", "Darkness": "Dark", "Ice": "Water"}


def choice(value, label):
    return {"value": value, "label": label}


def star_style(spec, origin):
    rank = spec.get("Rank")
    category = spec.get("SummonCategory", origin.get("SummonCategory"))
    if spec.get("CollaborationId") or origin.get("CollaborationId"):
        return "collab"
    if rank == 5 or (rank == 6 and category == "Story"):
        return "promote_silver"
    if rank == 6:
        return "myth_red"
    return {"Normal": "bronze", "Story": "silver", "Unique": "gold"}.get(category)


class HeroEditor(GameSaveEditor):
    def __init__(self, database, catalog, tables, body):
        super().__init__(database)
        self.catalog = catalog
        self.body = body
        self.specs = (
            {h["Id"]: h for h in json.loads(tables["heroes"][1])} if "heroes" in tables else {}
        )
        growth = json.loads(tables["exps2"][1]) if "exps2" in tables else {}
        constants = json.loads(tables["constants"][1]) if "constants" in tables else {}
        self.ascent_rank = constants.get("AscentCharacterRank")
        self.ascent_categories = {
            row["SummonCategory"]
            for row in growth.get("AscendCosts", [])
            if row["Rank"] == self.ascent_rank
        }
        experience = growth.get("LevelExps", [])
        self.levels = [0, *(row["TotalExps"] for row in experience if "TotalExps" in row)]

    def summary(self, hero):
        spec_id = hero["CharacterId"]
        spec = self.specs.get(spec_id, {})
        rank = spec.get("Rank")
        sprite = spec.get("SpriteName") or spec.get("Name")
        model = (spec.get("SpineAssetName") or {}).get("default", "")
        fallback = model.rsplit(":", 1)[-1].rsplit("#", 1)[-1]
        name = self.catalog.equipment.hero_names.get(spec_id)
        name = (
            name
            or str(spec.get("PortraitAssetName") or spec.get("Class") or f"Hero {spec_id}")
            .replace("_", " ")
            .title()
        )
        return {
            "id": hero["Id"],
            "spec": spec_id,
            "name": name,
            "sprite": f"/heroes/sprites/{sprite}.png" if sprite else None,
            "spriteFallback": (
                f"/heroes/sprites/{fallback}.png" if fallback and fallback != sprite else None
            ),
            "element": ELEMENTS.get(spec.get("ElementalType"), spec.get("ElementalType")),
            "form": {5: "Ascended", 6: "Myth"}.get(rank, ""),
            "starStyle": star_style(spec, self.specs.get(spec.get("OriginId"), {})),
            "stars": (
                min(rank + 1, 5) if rank is not None and rank < 6 else (6 if rank == 6 else None)
            ),
            "level": bisect_right(self.levels, hero.get("Experience", 0)),
        }

    def info(self):
        with self.reader() as db:
            profile = self.profile(db)
            user = profile["User"]
            policy = self.training_policy(db) if user["Characters"] else None
            heroes = []
            for hero in user["Characters"]:
                detail = self.inspect(profile, hero, policy)
                heroes.append({**detail["hero"], "upgradable": bool(detail["actions"])})
            return {"heroes": heroes, "version": self.inventory_version(user), **self.status()}

    def training_policy(self, db):
        refs = self.catalog.refs
        imported = is_imported(db)
        if imported and (refs.directory / "imported_training_catalog.json").is_file():
            return imported, imported_training.load_catalog(refs)
        if not imported and (refs.directory / "training_catalog.json").is_file():
            return imported, refs.json("training_catalog.json")
        return imported, None

    def training(self, policy_info, profile, hero):
        imported, policy = policy_info
        progress = profile["UserProgress"]
        if not progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED:
            return (), 0
        if imported:
            if not policy or hero["CharacterId"] not in policy["character_ids"]:
                return (), 0
            cap = 1 + imported_training.hero_cap(
                policy, imported_training.story_cap(policy, progress), hero
            )
        elif hero["CharacterId"] in (1, 2) and not (
            hero.get("BlessLevel") or hero.get("LimitBreaks")
        ):
            if policy is None:
                return ([0, 37], 2) if hero["Id"] == 1 else ((), 0)
            cap = imported_training.story_cap(policy, progress)
        else:
            return (), 0
        levels = policy["experience_by_level"]
        return levels, min(cap, len(levels))

    def inspect(self, profile, hero, policy):
        user = profile["User"]
        ident = hero["Id"]
        summary = self.summary(hero)
        stats = {"Level": summary["level"]}
        actions = {}
        detail = {
            "hero": summary,
            "stats": stats,
            "actions": actions,
            "version": self.inventory_version(user),
        }
        spec = hero["CharacterId"]
        if not self.specs.get(spec, {}).get("Playable"):
            return detail
        slots = [s for s in user.get("TrainingSlots", {}).values() if s.get("CharacterId") == ident]
        locked = {key for s in slots for key, on in s.items() if on is True}
        if slots:
            detail["trainingRoom"] = True

        levels, cap = self.training(policy, profile, hero)
        if levels:
            level = bisect_right(levels, hero["Experience"])
            summary["level"] = level
            stats["Level"] = f"{level} / {cap}"
            if "IsLevel" not in locked and level < cap:
                actions["level"] = {
                    "label": "Level up",
                    "choices": [choice(i, f"Level {i}") for i in range(level + 1, cap + 1)],
                }

        caps, _, _, quest = hero_blessing.rules(self.body)
        blessing = hero.get("BlessLevel", 0)
        bless_cap = caps.get(spec, 0)
        if bless_cap:
            stats["Blessing"] = f"{blessing} / {bless_cap}"
            if (
                blessing < bless_cap
                and "IsBlessing" not in locked
                and any(
                    q["Id"] == quest and q["Grade"] >= 0
                    for q in profile["UserProgress"]["QuestProgresses"]
                )
            ):
                choices = [choice(1, "One level")]
                if bless_cap - blessing > 1:
                    choices.append(choice(bless_cap - blessing, "Max blessing"))
                actions["bless"] = {"label": "Blessing", "choices": choices}

        forms, steps, _ = hero_evolution.rules(self.body)
        if spec in forms and not locked.intersection({"IsEvolve", "IsEvolveOnly"}):
            rank = forms[spec][0]
            current = hero.get("RankUpgrade", 0)
            choices = []
            for count in range(1, len(steps[rank]) - current + 1):
                _, evolves = hero_evolution.price(steps[rank], current, count)
                entry = choice(
                    count,
                    (
                        f"Evolve to {rank + 2}★"
                        if evolves
                        else f"+{count} evolution step{'s' if count > 1 else ''}"
                    ),
                )
                choices.append(entry)
                if evolves:
                    break
            if choices:
                stats["Evolution steps"] = f"{current} / {current + len(choices)}"
                actions["evolve"] = {"label": "Evolution", "choices": choices}

        prices, _ = hero_limit_break.rules(self.body)
        breaks = hero.get("LimitBreaks", 0)
        max_breaks = len(prices.get(spec, ()))
        if max_breaks:
            stats["Limit breaks"] = f"{breaks} / {max_breaks}"
            if breaks < max_breaks and "IsLimitBreak" not in locked:
                actions["break"] = {
                    "label": "Limit break",
                    "choices": [
                        choice(i, f"{breaks} → {breaks + i} breaks")
                        for i in range(1, max_breaks - breaks + 1)
                    ],
                }

        myth, required, _, _ = hero_myth.rules(self.body)
        source = self.specs[spec]
        link = source.get("AscendTo") or {}
        ascend_to = link.get("KakaoGlobal", link.get("Default"))
        ascended = self.specs.get(ascend_to)
        if (
            ascended
            and ascended.get("Playable") is True
            and source.get("SummonCategory") in self.ascent_categories
            and source["SummonCategory"] == ascended.get("SummonCategory")
            and source["OriginId"] == ascended.get("OriginId")
            and source["Rank"] + 1 == self.ascent_rank == ascended["Rank"]
            and breaks == required
            and not slots
        ):
            actions["ascend"] = {
                "label": "Ascension",
                "choices": [choice(ascend_to, "Ascend hero")],
            }
        if spec in myth and breaks == required and not slots:
            actions["myth"] = {"label": "Myth", "choices": [choice(1, "Promote to Myth")]}

        trees, _ = awakening_catalog.catalog(self.body)
        if spec in trees:
            tree, rank = trees[spec]
            _, mask = hero_awakening.saved_mask(hero, len(tree.nodes))
            opened = {i for i in range(len(tree.nodes)) if mask[i // 8] & (1 << (i % 8))}
            stats["Awakening"] = f"{len(opened)} / {len(tree.nodes)}"
            if "IsAwakening" not in locked:
                pending = sorted(tree.visible(rank, breaks) - opened)
                reachable = sorted(tree.open_connected(pending, opened.copy()) - opened)
                if reachable:
                    choices = [
                        choice(i, f"Node {i}") for i in reachable if tree.can_open(i, opened)
                    ]
                    choices.append(choice(-1, f"Auto Awakening · {len(reachable)} nodes"))
                    actions["awaken"] = {"label": "Awakening", "choices": choices}
                    detail["autoNodes"] = reachable
        return detail

    def details(self, ident):
        with self.reader() as db:
            return self.selected_details(db, ident)

    def selected_details(self, db, ident):
        profile = self.profile(db)
        hero = owned_character(profile["User"], ident)
        detail = self.inspect(profile, hero, self.training_policy(db))
        account = AccountStore(db, self.catalog.refs.directory, initialize=False)
        detail["reset"] = self.reset_preview(account, profile["User"], hero)
        return detail

    def reset_preview(self, account, user, hero):
        if account.needs_prologue():
            return {"reason": "Complete the prologue before resetting a hero."}
        try:
            changes = hero_reset.reset_changes(user, hero, self.specs, account.references)
        except ValueError as exc:
            return {"reason": str(exc)}
        if not changes:
            return {"reason": "This hero has no progress to reset."}
        return {"target": self.summary(hero | changes)}

    def apply_locked(self, db, body):
        if not isinstance(body, dict):
            raise ValueError("Choose a hero and an action")
        max_hero = body.get("action") == "max"
        fields = {"id", "version", "action"}
        if body.get("action") not in ("max", "reset"):
            fields.add("value")
        if set(body) != fields:
            raise ValueError("Choose a hero and an action")
        ident, action = body["id"], body["action"]
        if not integer(ident, minimum=1) or not isinstance(action, str):
            raise ValueError("Invalid hero action")
        profile = self.profile(db)
        if body["version"] != self.inventory_version(profile["User"]):
            return 409, {"error": "The roster has changed. Reload the heroes before applying."}
        hero = owned_character(profile["User"], ident)
        account = AccountStore(db, self.catalog.refs.directory, initialize=False)
        if action == "reset":
            preview = self.reset_preview(account, profile["User"], hero)
            if "reason" in preview:
                raise ValueError(preview["reason"])
            hero_reset.create_tables(db)
            hero_reset.reset(
                account,
                {"CharacterId": ident, "ReceiveCrystal": False},
                "panel-" + uuid4().hex,
                heroes=self.specs,
            )
            return 200, self.selected_details(db, ident)
        policy = self.training_policy(db)
        detail = self.inspect(profile, hero, policy)
        if not max_hero:
            value = body["value"]
            options = detail["actions"].get(action, {}).get("choices", [])
            if type(value) is not int or not any(c["value"] == value for c in options):
                raise ValueError("Choose an available upgrade for this hero")
        # A guest knight can train only in its starting form. On imported saves
        # train after promotion so the final level cap is reached in one step.
        order = ("evolve", "break", "ascend", "myth", "bless", "level", "awaken")
        if not policy[0]:
            order = ("level", "evolve", "break", "ascend", "myth", "bless", "awaken")
        while detail["actions"]:
            if max_hero:
                action = next(key for key in order if key in detail["actions"])
                value = detail["actions"][action]["choices"][-1]["value"]
            before = hero.copy()
            self.apply_upgrade(account, profile, hero, policy, detail, action, value)
            profile = account.profile()
            updated = owned_character(profile["User"], ident)
            if updated == before:
                raise ValueError("The selected hero upgrade did not advance its progress")
            hero = updated
            detail = self.inspect(profile, hero, policy)
            if not max_hero:
                break
        detail["reset"] = self.reset_preview(account, profile["User"], hero)
        return 200, detail

    def apply_upgrade(self, account, profile, hero, policy, detail, action, value):
        db = account.db
        ident = hero["Id"]
        operation = "panel-" + uuid4().hex
        request = {"CharacterId": ident}
        if action == "level":
            levels, _ = self.training(policy, profile, hero)
            imported_training.create_tables(db)
            account.add_character_experience(
                {"Experiences": {str(ident): levels[value - 1] - hero["Experience"]}},
                operation,
                free=True,
            )
        elif action == "awaken":
            hero_awakening.create_tables(db)
            request.update(
                NodeIndices=detail["autoNodes"] if value == -1 else [value], discountBuff=False
            )
            hero_awakening.awaken(account, request, operation, free=True)
        elif action == "evolve":
            hero_evolution.create_tables(db)
            request.update(UpgradeCount=value, DreamSpiritStoneUsageAmount=0)
            hero_evolution.evolve(account, request, operation, free=True)
        elif action == "myth":
            hero_myth.create_tables(db)
            request["DreamMythStoneUsageAmount"] = 0
            hero_myth.promote(account, request, operation, free=True)
        elif action == "ascend":
            if account.needs_prologue() or not integer(profile["User"]["Cas"], MAX_REVISION - 1):
                raise ValueError("Cannot ascend this hero on the current save")
            hero.update(CharacterId=value, RankUpgrade=0)
            profile["User"]["Cas"] += 1
            db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        elif action == "break":
            hero_limit_break.create_tables(db)
            request["LimitBreakCount"] = value
            hero_limit_break.limit_break(account, request, operation, free=True)
        elif action == "bless":
            hero_blessing.create_tables(db)
            hero_blessing.bless(
                account,
                hero_blessing.ONE if value == 1 else hero_blessing.ALL,
                request,
                operation,
                free=True,
            )
