# SPDX-License-Identifier: Apache-2.0
"""Persistent new local guest and read-only empty social/collection state.

The account starts empty; the client creates its own temporary prologue party.
Completion creates one knight and the two selected starting weapon slots. No
reference player's inventory, balance, progress or credentials are included.
Campaign battle results and most reward-changing operations remain unimplemented.
"""

import hashlib
import json
from datetime import datetime, timezone

from .attendance import claim as claim_imported_attendance
from .attendance import create_tables as create_attendance_tables
from .basecamp import create_tables as create_basecamp_tables
from .basecamp import harvest as harvest_basecamp
from .beginner import claim_beginner
from .campaign import (
    CHARGED_STAMINA,
    FIRST_CHAPTER_CODE,
    FIRST_CLEAR_GEMS,
    FIRST_STAGE_ID,
    FIRST_STAGE_ITEMS,
    FIRST_STAGE_PICKUPS,
    FIRST_STAGE_STAMINA,
    FREE_GEMS,
    RESERVE_STAMINA,
    STAGE_CLEARED,
    STAGE_OPENED,
    STAGE_UNLOCKED,
    encode_stage_progress,
    initial_stage_progresses,
)
from .challenges import claim_challenges
from .characters import new_character
from .completion import complete_catalog_stage, completion_custom
from .discovery import discover_substage
from .festival_shop import check_not_redeemable, redeem_points
from .guild_menu import GUILD_MENU_ROUTES
from .guild_menu import read as read_guild_menu
from .guild_raid import END_STAGE as RAID_STAGE_EXIT_ROUTE
from .guild_raid import MENU_READ_ROUTES as RAID_MENU_READ_ROUTES
from .guild_raid import RANKING_ROUTES as RAID_RANKING_ROUTES
from .guild_raid import START_STAGE as RAID_STAGE_ENTRY_ROUTE
from .guild_raid import end_stage as exit_raid_stage
from .guild_raid import enter as enter_guild_raid
from .guild_raid import menu_read as read_raid_menu
from .guild_raid import rankings as guild_raid_rankings
from .guild_raid import start_stage as enter_raid_stage
from .hero_knowledge import claim_hero_knowledge
from .items import inventory_item
from .mastery import create_tables as create_mastery_tables
from .mastery import upgrade as upgrade_guardian_mastery
from .mastery_reset import create_tables as create_mastery_reset_tables
from .mastery_reset import reset as reset_guardian_mastery
from .missions import (
    FIRST_HERO_CHALLENGE_GEMS,
    FIRST_HERO_CHALLENGE_GROUP,
    FIRST_HERO_CHALLENGE_STEP,
)
from .monsters import record_defeated_monsters
from .orbital import create_tables as create_orbital_tables
from .passes import (
    FIRST_FESTIVAL_LEVEL,
    FIRST_FESTIVAL_POINTS,
    FIRST_FESTIVAL_SEASON,
    FIRST_PASS_LEVEL,
    FIRST_PASS_SEASON,
    FIRST_PASS_STAMINA,
)
from .presets import create_tables as create_preset_tables
from .presets import delete_existing as delete_existing_preset
from .presets import save_party as save_party_preset
from .presets import set_selected as set_selected_preset
from .profile_card import read as read_profile_card
from .reference import ReferenceData
from .relic_options import change_or_apply as change_or_apply_relic_options
from .relic_options import create_tables as create_relic_option_tables
from .snapshots import create_tables as create_snapshot_tables
from .snapshots import is_imported
from .stamina_purchase import purchase_stamina
from .stamina_regen import charge_stamina
from .story import enter_story_stage, load_story_catalog, open_eligible_stages
from .summon_draw import draw_characters
from .summon_pickup import check_pickup_exchange
from .summon_selection import select_characters
from .training import train_characters
from .tutorials import PASSIVE_HELP_TUTORIALS, POST_INN_TUTORIALS, catalog_tutorial_ids
from .village import create_tables as create_village_tables
from .village import harvest as harvest_village
from .village_gift import create_tables as create_village_gift_tables
from .village_gift import receive as receive_village_gift
from .village_obstacle import create_tables as create_village_obstacle_tables
from .village_obstacle import remove as remove_village_obstacle
from .weapon_engrave import create_tables as create_weapon_engrave_tables
from .weapon_engrave import engrave as engrave_weapon
from .weapon_enhance import create_tables as create_weapon_enhance_tables
from .weapon_enhance import enhance as enhance_weapon
from .weapon_limit_break import create_tables as create_weapon_limit_break_tables
from .weapon_limit_break import limit_break as limit_break_weapon
from .weapon_option_lock import change_locks as change_weapon_option_locks
from .weapon_option_lock import create_tables as create_weapon_option_lock_tables
from .weapon_options import change_or_apply as change_or_apply_weapon_options
from .weapon_options import create_tables as create_weapon_option_tables

ACCOUNT_ROUTES = (
    "/auth/fetch-account",
    "/user/get-user-profile-card",
    "/guild/list-item-request",
    "/guild/get-my-guild",
    "/guild/red-dot",
    "/guild-raid2/reset",
    "/guild-raid2/enter",
    RAID_STAGE_ENTRY_ROUTE,
    RAID_STAGE_EXIT_ROUTE,
    *RAID_MENU_READ_ROUTES,
    *RAID_RANKING_ROUTES,
    "/chat/guild-history/v2",
    "/chat/listen-channel",
    "/collection/list-all",
    "/collection/list-new",
    "/collection/claim-hero-knowledge-all",
    "/heavenholdfarm/collection-all",
    "/pasture/collection-all",
    "/friend2/enter",
    "/friend2/recommend",
    "/friend2/has-changes",
    "/mission/get-user-mission",
    "/mission/claim-beginner-all",
    "/mission/claim-challenge-all",
    "/mission/claim-challenge-all-step",
    "/ad/init-inbox",
    "/guardian-pass/enter",
    "/guardian-pass/claim-all",
    "/festival-pass/enter",
    "/festival-pass/claim-all",
    "/festival-pass/check-not-redeemable",
    "/festival-pass/redeem-point-rewards",
    "/user/exchange-summon-pickup-ticket",
    "/user/charge-stamina-by-gem",
    "/user/charge-stamina",
    "/summon/set-select-character",
    "/summon/select-character",
    "/preset/set-selected-preset",
    "/preset/set-presets",
    "/preset/delete-preset",
    "/lobby-village/harvest-all",
    "/lobby-village/harvest-basecamp",
    "/lobby-village/receive-gift",
    "/lobby-village/remove-obstacle",
    "/item/enhance-weapon",
    "/item/limitbreak-weapon/v2",
    "/item/change-options",
    "/item/apply-options",
    "/item/engrave-weapon",
    "/item/change-lock-options",
    "/item/change-relic-options/v2",
    "/item/apply-relic-options",
    "/user/guardian-mastery-level-up",
    "/user/reset-guardian-mastery-level",
    "/stage/get-stage-progresses",
    "/stage/start-stage",
    "/stage/start-quest",
    "/stage/progress-quest",
    "/stage/pick-stage-coins",
    "/stage/beat-monsters",
    "/stage/pick-stage-item",
    "/stage/open-treasure",
    "/stage/interact-substage-item",
    "/stage/end-stage",
    "/user/mark-tutorial",
    "/user/add-character-experience",
    "/auth/check-name",
    "/auth/sign-name",
    "/auth/sign-up/v2",
    "/user/claim-daily-attendance",
)


def valid_name(name):
    if not isinstance(name, str) or any(ord(c) < 32 or ord(c) == 127 for c in name):
        return False
    try:
        return 2 <= len(name.encode("utf-16le")) // 2 <= 10
    except UnicodeError:
        return False


def valid_prologue_info(info):
    fields = {"IsMale", "VoiceType", "Weapon1ItemId", "Weapon2ItemId", "BobLindaQuestGrade"}
    return (
        isinstance(info, dict)
        and set(info) == fields
        and type(info["IsMale"]) is bool
        and type(info["VoiceType"]) is int
        and 0 <= info["VoiceType"] <= 2
        and all(
            type(info[k]) is int and 0 <= info[k] <= 0x7FFFFFFF
            for k in ("Weapon1ItemId", "Weapon2ItemId")
        )
        and type(info["BobLindaQuestGrade"]) is int
        and 0 <= info["BobLindaQuestGrade"] <= 255
    )


class AccountStore:
    def __init__(self, db, reference_dir=None):
        self.db = db
        self.references = ReferenceData(reference_dir)
        create_snapshot_tables(db)
        create_preset_tables(db)
        create_village_tables(db)
        create_basecamp_tables(db)
        create_mastery_tables(db)
        create_mastery_reset_tables(db)
        create_attendance_tables(db)
        create_village_gift_tables(db)
        create_village_obstacle_tables(db)
        create_weapon_enhance_tables(db)
        create_weapon_limit_break_tables(db)
        create_weapon_option_tables(db)
        create_weapon_engrave_tables(db)
        create_weapon_option_lock_tables(db)
        create_relic_option_tables(db)
        create_orbital_tables(db)
        db.execute(
            "CREATE TABLE IF NOT EXISTS local_account (id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER NOT NULL, profile TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS prologue_selection (id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, info TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS attendance_claims (day TEXT PRIMARY KEY, attendance_count INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS campaign_session (id INTEGER PRIMARY KEY CHECK(id=1), stage_id INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS campaign_progress (stage_id INTEGER NOT NULL, category INTEGER NOT NULL, key INTEGER NOT NULL, value TEXT NOT NULL, PRIMARY KEY(stage_id,category,key))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS campaign_item_receipts (stage_id INTEGER NOT NULL, item_key TEXT NOT NULL, inventory_id INTEGER NOT NULL, PRIMARY KEY(stage_id,item_key))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS campaign_completions (stage_id INTEGER PRIMARY KEY, exit_name TEXT NOT NULL, hit_count INTEGER, no_damage INTEGER)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS campaign_grade_claims (stage_id INTEGER PRIMARY KEY, gems INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS first_knight_training (character_id INTEGER PRIMARY KEY, experience INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS character_training_requests (operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, targets TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS character_summon_requests (operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, results TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS stamina_gem_purchase_requests (operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, purchase TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS beginner_mission_claims (mission_id INTEGER PRIMARY KEY, rewards TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS challenge_mission_claims (group_id INTEGER NOT NULL, step INTEGER NOT NULL, rewards TEXT NOT NULL, PRIMARY KEY(group_id,step))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS challenge_mission_requests (operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, rewards TEXT NOT NULL, targets TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS hero_knowledge_claims (character_id INTEGER PRIMARY KEY, knowledge_id INTEGER NOT NULL UNIQUE, rewards TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS hero_knowledge_requests (operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, rewards TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS guardian_pass_claims (season_id INTEGER NOT NULL, level INTEGER NOT NULL, rewards TEXT NOT NULL, PRIMARY KEY(season_id,level))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS festival_pass_claims (season_id INTEGER NOT NULL, level INTEGER NOT NULL, points INTEGER NOT NULL, PRIMARY KEY(season_id,level))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS festival_shop_requests (operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, rewards TEXT NOT NULL, purchase TEXT NOT NULL)"
        )
        existing = db.execute(
            "SELECT schema_version,profile FROM local_account WHERE id=1"
        ).fetchone()
        if existing and existing[0] == 1:
            # Upgrade only the exact earlier zero-progress laboratory template.
            # Refuse to overwrite any manually edited or progressed profile.
            canonical = json.dumps(
                json.loads(existing[1]), sort_keys=True, separators=(",", ":")
            ).encode()
            if (
                hashlib.sha256(canonical).hexdigest()
                != "bd9f1667b12e736da70f455a2e8953bca4deaba38ec8e122ea584262f5b5ec94"
            ):
                raise ValueError(
                    "Legacy account differs from the known empty template; automatic migration refused"
                )
        if not existing or existing[0] == 1:
            profile = self.references.json("new_guest_profile.json")
            db.execute(
                "INSERT INTO local_account VALUES(1,3,?) ON CONFLICT(id) DO UPDATE SET schema_version=3,profile=excluded.profile",
                (json.dumps(profile, separators=(",", ":")),),
            )
        elif existing[0] == 2:
            profile = json.loads(existing[1])
            # Repair only public counter catalog identifiers. Preserve the
            # player's name, chosen knight, equipment and completion record.
            for spec in self.references.json("counter_types.json"):
                value = profile
                for key in spec["path"]:
                    value = value[key]
                if value["Type"] == 0:
                    value["Type"] = spec["type"]
            db.execute(
                "UPDATE local_account SET schema_version=3,profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        elif existing[0] != 3:
            raise ValueError("Unsupported account schema version")
        db.commit()
        catalog = load_story_catalog(self.references)
        if catalog and not self.needs_prologue() and not is_imported(db):
            profile = self.profile()
            if open_eligible_stages(profile, catalog):
                with db:
                    db.execute(
                        "UPDATE local_account SET profile=? WHERE id=1",
                        (json.dumps(profile, separators=(",", ":")),),
                    )

    def profile(self):
        return json.loads(
            self.db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
        )

    def needs_prologue(self):
        return not is_imported(self.db) and not bool(
            self.db.execute("SELECT 1 FROM prologue_selection WHERE id=1").fetchone()
        )

    def complete_prologue(self, name, info):
        if is_imported(self.db):
            raise ValueError("An imported account cannot repeat the prologue")
        if not valid_name(name) or not valid_prologue_info(info):
            raise ValueError("Invalid prologue selection")
        previous = self.db.execute("SELECT name,info FROM prologue_selection WHERE id=1").fetchone()
        encoded = json.dumps(info, sort_keys=True, separators=(",", ":"))
        if previous:
            if previous != (name, encoded):
                raise ValueError("Prologue already completed with a different selection")
            return self.profile()
        profile = self.profile()
        user = profile["User"]
        weapons = []
        slots = []
        for spec in (info["Weapon1ItemId"], info["Weapon2ItemId"]):
            slots.append(len(weapons) + 1 if spec else None)
            if spec:
                weapons.append(inventory_item(len(weapons) + 1, spec))
        # CharacterSpecId.KnightFemale=1, KnightMale=2 in this client. These
        # public catalog IDs were verified from its initialized static fields.
        knight = new_character(1, 2 if info["IsMale"] else 1, slots[0], slots[1])
        user.update(
            Name=name,
            VoiceType=info["VoiceType"],
            Characters=[knight],
            CharacterIdCounter=1,
            ItemWeapons=weapons,
            ItemIdCounter=len(weapons),
            RepresentativeCharacterId=1,
            Party={"Id": 0, "Characters": [1]},
        )
        with self.db:
            self.db.execute("INSERT INTO prologue_selection VALUES(1,?,?)", (name, encoded))
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        return profile

    def claim_attendance(self, now=None, request=None, operation_id=None):
        """Claim fresh-account assets or explicitly mock the imported account's day."""
        if request not in (None, {}):
            raise ValueError("Daily attendance accepts no parameters")
        if is_imported(self.db):
            return claim_imported_attendance(self, request, operation_id, now)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Attendance clock must have a timezone")
        now = now.astimezone(timezone.utc)
        day = now.date().isoformat()
        if self.db.execute("SELECT 1 FROM attendance_claims WHERE day=?", (day,)).fetchone():
            return {"User": self.profile()["User"], "UserRecord": self.profile()["UserRecord"]}
        profile = self.profile()
        user = profile["User"]
        previous = user["MonthlyLoginCount"]
        catalog = self.references.json("attendance_catalog.json")
        group = (
            (previous // 100 if previous >= 100 else catalog["origin_group"])
            if previous
            else catalog["active_group"]
        )
        ordinal = previous % 100 + 1
        if ordinal > 28:
            group = catalog["active_group"]
            ordinal = 1
        row = next((r for r in catalog["groups"][str(group)] if r["Day"] == ordinal), None)
        if not row:
            raise ValueError("Attendance reward is not in the preserved catalog")
        assets = {a["Id"]: a for a in user["Assets"]}
        if any(r["ItemId"] not in assets for r in row["Rewards"]):
            raise ValueError("Attendance inventory/random-item rewards are not implemented yet")
        # Validate the entire reward before mutating or recording the claim.
        for reward in row["Rewards"]:
            amount = reward["Amount"]
            if type(amount) is not int or not 0 < amount <= 0x7FFFFFFF:
                raise ValueError("Invalid catalog reward")
            if assets[reward["ItemId"]]["Amount"] + amount > 0x7FFFFFFF:
                raise ValueError("Asset balance overflow")
        for reward in row["Rewards"]:
            assets[reward["ItemId"]]["Amount"] += reward["Amount"]
        user["MonthlyLoginCount"] = group * 100 + ordinal
        user["LastAttendanceDate"] = now.isoformat(timespec="microseconds")
        user["Cas"] += 1
        profile["UserRecord"]["LoginDayCount"] += 1
        with self.db:
            self.db.execute(
                "INSERT INTO attendance_claims VALUES(?,?)", (day, user["MonthlyLoginCount"])
            )
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        return {"User": user, "UserRecord": profile["UserRecord"]}

    def start_stage(self, request):
        """Enter a configured story stage, retaining the original first-phase fallback."""
        catalog = load_story_catalog(self.references)
        if catalog is not None:
            return enter_story_stage(self, request, catalog)
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
        ):
            raise ValueError("Stage entry is implemented only for the first story phase")
        if self.needs_prologue():
            raise ValueError("Complete the local prologue before entering a story phase")
        profile = self.profile()
        user, progress = profile["User"], profile["UserProgress"]
        state = progress["StageStates"].get(str(FIRST_STAGE_ID), 0)
        if not state & STAGE_UNLOCKED:
            assets = {asset["Id"]: asset for asset in user["Assets"]}
            charged, reserve = assets[CHARGED_STAMINA], assets[RESERVE_STAMINA]
            if charged["Amount"] + reserve["Amount"] < FIRST_STAGE_STAMINA:
                raise ValueError("Not enough stamina to unlock the first story phase")
            from_charge = min(charged["Amount"], FIRST_STAGE_STAMINA)
            from_reserve = FIRST_STAGE_STAMINA - from_charge
            for asset, amount in ((charged, from_charge), (reserve, from_reserve)):
                asset["Amount"] -= amount
                asset["Spent"] += amount
            progress["StageStates"][str(FIRST_STAGE_ID)] = state | STAGE_OPENED | STAGE_UNLOCKED
            progress["LastPlayedStageId"] = FIRST_STAGE_ID
            progress["Cas"] += 1
            user["Cas"] += 1
        with self.db:
            self.db.execute(
                "INSERT INTO campaign_session VALUES(1,?) ON CONFLICT(id) DO UPDATE SET stage_id=excluded.stage_id",
                (FIRST_STAGE_ID,),
            )
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        return {
            "User": user,
            "UserProgress": progress,
            "StageProgress": self.stage_progress(FIRST_STAGE_ID),
        }

    def stage_progress(self, stage_id):
        stores = {}
        for category, key, value in self.db.execute(
            "SELECT category,key,value FROM campaign_progress WHERE stage_id=?", (stage_id,)
        ):
            stores.setdefault(category, {})[key] = json.loads(value)
        return encode_stage_progress(stores)

    def pick_stage_coins(self, request):
        """Collect known stage currencies atomically, once per kind and tilemap key."""
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or request.get("StageCustom") is not None
            or not isinstance(request.get("Items"), list)
            or not 1
            <= len(request["Items"])
            <= sum(len(keys) for _, keys in FIRST_STAGE_PICKUPS.values())
        ):
            raise ValueError("Malformed first-phase coin request")
        pickups = set()
        for item in request["Items"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"Id", "ItemId"}
                or type(item["Id"]) is not int
                or type(item["ItemId"]) is not int
            ):
                raise ValueError("Malformed first-phase collectible")
            spec = FIRST_STAGE_PICKUPS.get(item["ItemId"])
            if spec is None or item["Id"] not in spec[1]:
                raise ValueError("Unknown first-phase collectible")
            pickups.add((spec[0], item["Id"], item["ItemId"]))
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            FIRST_STAGE_ID,
        ):
            raise ValueError("Start the phase before collecting its coins")
        profile = self.profile()
        user = profile["User"]
        with self.db:
            added = {}
            for category, key, item_id in sorted(pickups):
                inserted = self.db.execute(
                    "INSERT OR IGNORE INTO campaign_progress VALUES(?,?,?,?)",
                    (FIRST_STAGE_ID, category, key, "true"),
                ).rowcount
                if inserted:
                    added[item_id] = added.get(item_id, 0) + 1
            if added:
                assets = {asset["Id"]: asset for asset in user["Assets"]}
                for item_id, amount in added.items():
                    if item_id not in assets:
                        raise ValueError("The saved account is missing a collectible asset")
                    assets[item_id]["Amount"] += amount
                user["Cas"] += 1
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {"User": user}

    def pick_stage_item(self, request):
        """Grant each named first-phase item once and return its stable inventory ID."""
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or not isinstance(request.get("StageItemKey"), str)
            or request["StageItemKey"] not in FIRST_STAGE_ITEMS
            or request.get("StageCustom") is not None
        ):
            raise ValueError("Unknown first-phase item")
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            FIRST_STAGE_ID,
        ):
            raise ValueError("Start the phase before collecting its items")
        key = request["StageItemKey"]
        index, item_id, collection = FIRST_STAGE_ITEMS[key]
        return self._grant_campaign_item(key, 4, index, item_id, collection)

    def open_treasure(self, request):
        """Open the first phase's glove chest once; preserve its inventory receipt."""
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or request.get("TreasureBoxKey") != "mole_glove_box"
            or request.get("StageCustom") is not None
        ):
            raise ValueError("Unknown first-phase treasure box")
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            FIRST_STAGE_ID,
        ):
            raise ValueError("Start the phase before opening its treasure")
        # The loaded TreasureBehaviour contains one ItemPlaceholder: 30017 x1.
        value = self._grant_campaign_item("treasure:mole_glove_box", 5, 1, 30017, "ItemMiscs")
        return {"User": value["User"], "AddedItems": [value["AddedItem"]]}

    def _grant_campaign_item(self, key, category, index, item_id, collection):
        profile = self.profile()
        user = profile["User"]
        previous = self.db.execute(
            "SELECT inventory_id FROM campaign_item_receipts WHERE stage_id=? AND item_key=?",
            (FIRST_STAGE_ID, key),
        ).fetchone()
        if previous:
            item = next((item for item in user[collection] if item["Id"] == previous[0]), None)
            if item is None or item["ItemId"] != item_id:
                raise ValueError("Saved stage item receipt does not match the inventory")
        else:
            user["ItemIdCounter"] += 1
            item = inventory_item(user["ItemIdCounter"], item_id)
            user[collection].append(item)
            user["Cas"] += 1
            with self.db:
                self.db.execute(
                    "INSERT INTO campaign_item_receipts VALUES(?,?,?)",
                    (FIRST_STAGE_ID, key, item["Id"]),
                )
                self.db.execute(
                    "INSERT INTO campaign_progress VALUES(?,?,?,?)",
                    (FIRST_STAGE_ID, category, index, "true"),
                )
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {"User": user, "AddedItem": item}

    def end_stage(self, request):
        """Commit the first phase's clear exit and its first-grade gem reward once."""
        if isinstance(request, dict) and request.get("StageId") != FIRST_STAGE_ID:
            return complete_catalog_stage(self, request)
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or request.get("ExitName") != "exit_forest_1_2"
            or request.get("IsClearExit") is not True
        ):
            raise ValueError("Only the first phase's clear exit is implemented")
        hit_count, no_damage = completion_custom(request.get("StageCustom"))
        profile = self.profile()
        progress, user = profile["UserProgress"], profile["User"]
        completed = self.db.execute(
            "SELECT 1 FROM campaign_completions WHERE stage_id=?", (FIRST_STAGE_ID,)
        ).fetchone()
        if not completed:
            if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
                FIRST_STAGE_ID,
            ):
                raise ValueError("Start the phase before completing it")
            quest = next((q for q in progress["QuestProgresses"] if q["Id"] == 27), None)
            glove = self.db.execute(
                "SELECT 1 FROM campaign_item_receipts WHERE stage_id=? AND item_key=?",
                (FIRST_STAGE_ID, "treasure:mole_glove_box"),
            ).fetchone()
            if quest is None or quest["InnerProgress"] < 4 or not glove:
                raise ValueError("Complete the first phase's initial quest steps and glove chest")
            progress["StageStates"][str(FIRST_STAGE_ID)] |= STAGE_CLEARED
            progress["Cas"] += 1
        grade_claimed = self.db.execute(
            "SELECT 1 FROM campaign_grade_claims WHERE stage_id=?", (FIRST_STAGE_ID,)
        ).fetchone()
        if not progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED:
            raise ValueError("Completion receipt does not match the saved phase state")
        if not grade_claimed:
            next(asset for asset in user["Assets"] if asset["Id"] == FREE_GEMS)[
                "Amount"
            ] += FIRST_CLEAR_GEMS
            user["Cas"] += 1
        opened_next = open_eligible_stages(profile, load_story_catalog(self.references))
        with self.db:
            if not completed:
                self.db.execute(
                    "INSERT INTO campaign_completions VALUES(?,?,?,?)",
                    (FIRST_STAGE_ID, request["ExitName"], hit_count, no_damage),
                )
                self.db.execute("DELETE FROM campaign_session WHERE id=1")
            if not grade_claimed:
                self.db.execute(
                    "INSERT INTO campaign_grade_claims VALUES(?,?)",
                    (FIRST_STAGE_ID, FIRST_CLEAR_GEMS),
                )
            if not completed or not grade_claimed or opened_next:
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        # StageSpec.Rewards and FailRewards are null for this preserved phase.
        # The separate grade reward is the 50 free gems shown on first clear.
        return {
            "User": user,
            "UserProgress": progress,
            "StageState": progress["StageStates"][str(FIRST_STAGE_ID)],
            "StageProgress": self.stage_progress(FIRST_STAGE_ID),
            "AddedItems": [],
        }

    def claim_beginner_missions(self, request):
        return claim_beginner(self, request)

    def claim_challenge_missions(self, request, operation_id=None, all_steps=False):
        """Claim configured steps, retaining the legacy first-knight fallback."""
        if (
            all_steps
            or (self.references.directory / "challenge_mission_catalog.json").is_file()
            or isinstance(operation_id, str)
            and self.db.execute(
                "SELECT 1 FROM challenge_mission_requests WHERE operation_id=?", (operation_id,)
            ).fetchone()
        ):
            return claim_challenges(self, request, operation_id, all_steps)
        if (
            not isinstance(request, dict)
            or set(request) != {"missionIds"}
            or not isinstance(request["missionIds"], list)
            or not 1 <= len(request["missionIds"]) <= 32
            or any(
                type(value) is not int or value != FIRST_HERO_CHALLENGE_GROUP
                for value in request["missionIds"]
            )
        ):
            raise ValueError("Only collect-hero challenge group 200's first step is implemented")
        profile = self.profile()
        user, mission = profile["User"], profile["UserMission"]
        if (
            self.needs_prologue()
            or len(user["Characters"]) != 1
            or user["Characters"][0]["CharacterId"] not in (1, 2)
        ):
            raise ValueError("This challenge supports only the saved starting knight")
        key = str(FIRST_HERO_CHALLENGE_GROUP)
        step = mission["ChallengeClaimed"].get(key, 0)
        if type(step) is not int or step not in (0, FIRST_HERO_CHALLENGE_STEP):
            raise ValueError("Later collect-hero challenge steps are not implemented")
        claimed = self.db.execute(
            "SELECT rewards FROM challenge_mission_claims WHERE group_id=? AND step=?",
            (FIRST_HERO_CHALLENGE_GROUP, FIRST_HERO_CHALLENGE_STEP),
        ).fetchone()
        if bool(claimed) != (step == FIRST_HERO_CHALLENGE_STEP):
            raise ValueError("Challenge receipt does not match saved claim progress")
        if claimed:
            return {"User": user, "UserMission": mission, "AddedItems": json.loads(claimed[0])}
        next(a for a in user["Assets"] if a["Id"] == FREE_GEMS)[
            "Amount"
        ] += FIRST_HERO_CHALLENGE_GEMS
        mission["ChallengeClaimed"][key] = FIRST_HERO_CHALLENGE_STEP
        mission["Cas"] += 1
        user["Cas"] += 1
        rewards = [{"Id": 0, "ItemId": FREE_GEMS, "Amount": FIRST_HERO_CHALLENGE_GEMS}]
        with self.db:
            self.db.execute(
                "INSERT INTO challenge_mission_claims VALUES(?,?,?)",
                (FIRST_HERO_CHALLENGE_GROUP, FIRST_HERO_CHALLENGE_STEP, json.dumps(rewards)),
            )
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        return {"User": user, "UserMission": mission, "AddedItems": rewards}

    def claim_guardian_pass(self, request):
        """Grant only season 58's free level-1 reward, with atomic retry receipts."""
        if request is not None and request != {}:
            raise ValueError("Guardian Pass reward claim accepts no parameters")
        profile = self.profile()
        user, guardian_pass = profile["User"], profile["UserGuardianPass"]
        season = guardian_pass["SeasonId"]
        claimed = guardian_pass["Claimed"]
        if (
            self.needs_prologue()
            or type(season) is not int
            or season not in (0, FIRST_PASS_SEASON)
            or type(guardian_pass["Experience"]) is not int
            or guardian_pass["Experience"] != 0
            or type(guardian_pass["PassType"]) is not int
            or guardian_pass["PassType"] != 0
            or guardian_pass.get("PurchasedGoldPass", False) is not False
            or guardian_pass.get("FreeRewardClaimedList", [])
            or guardian_pass.get("GoldRewardClaimedList", [])
            or guardian_pass["Missions"]
            or set(claimed) != {"Free", "Gold", "Platinum", "ExtraExp"}
            or any(type(value) is not int for value in claimed.values())
            or claimed["Free"] not in (0, FIRST_PASS_LEVEL)
            or any(claimed[key] != 0 for key in ("Gold", "Platinum", "ExtraExp"))
        ):
            raise ValueError(
                "Only the initial free level-1 reward of local season 58 is implemented"
            )
        rewards = [{"Id": 0, "ItemId": RESERVE_STAMINA, "Amount": FIRST_PASS_STAMINA}]
        receipt = self.db.execute(
            "SELECT rewards FROM guardian_pass_claims WHERE season_id=? AND level=?",
            (FIRST_PASS_SEASON, FIRST_PASS_LEVEL),
        ).fetchone()
        if bool(receipt) != (claimed["Free"] == FIRST_PASS_LEVEL) or (
            receipt and (season != FIRST_PASS_SEASON or json.loads(receipt[0]) != rewards)
        ):
            raise ValueError("Guardian Pass receipt does not match saved claim progress")
        if not receipt:
            next(a for a in user["Assets"] if a["Id"] == RESERVE_STAMINA)[
                "Amount"
            ] += FIRST_PASS_STAMINA
            guardian_pass["SeasonId"] = FIRST_PASS_SEASON
            claimed["Free"] = FIRST_PASS_LEVEL
            guardian_pass["Cas"] += 1
            user["Cas"] += 1
            with self.db:
                self.db.execute(
                    "INSERT INTO guardian_pass_claims VALUES(?,?,?)",
                    (FIRST_PASS_SEASON, FIRST_PASS_LEVEL, json.dumps(rewards)),
                )
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {"User": user, "UserGuardianPass": guardian_pass, "AddedItems": rewards}

    def claim_festival_pass(self, request):
        """Grant only local season 41's free level-1 festival points once."""
        if request is not None and request != {}:
            raise ValueError("Festival Pass reward claim accepts no parameters")
        profile = self.profile()
        festival_pass = profile["UserFestivalPass"]
        season, claimed = festival_pass["SeasonId"], festival_pass["Claimed"]
        if (
            self.needs_prologue()
            or type(season) is not int
            or season not in (0, FIRST_FESTIVAL_SEASON)
            or type(festival_pass["Experience"]) is not int
            or festival_pass["Experience"] != 0
            or type(festival_pass["PassType"]) is not int
            or festival_pass["PassType"] != 0
            or type(festival_pass["Point"]) is not int
            or not 0 <= festival_pass["Point"] <= 0x7FFFFFFF
            or festival_pass["Missions"]
            or not isinstance(festival_pass["Purchase"], dict)
            or set(claimed) != {"Free", "Gold", "Platinum", "ExtraExp"}
            or any(type(value) is not int for value in claimed.values())
            or claimed["Free"] not in (0, FIRST_FESTIVAL_LEVEL)
            or any(claimed[key] != 0 for key in ("Gold", "Platinum", "ExtraExp"))
        ):
            raise ValueError(
                "Only the initial free level-1 reward of local festival season 41 is implemented"
            )
        receipt = self.db.execute(
            "SELECT points FROM festival_pass_claims WHERE season_id=? AND level=?",
            (FIRST_FESTIVAL_SEASON, FIRST_FESTIVAL_LEVEL),
        ).fetchone()
        if (
            bool(receipt) != (claimed["Free"] == FIRST_FESTIVAL_LEVEL)
            or not receipt
            and (festival_pass["Point"] != 0 or festival_pass["Purchase"])
            or (
                receipt and (season != FIRST_FESTIVAL_SEASON or receipt != (FIRST_FESTIVAL_POINTS,))
            )
        ):
            raise ValueError("Festival Pass receipt does not match saved claim progress")
        if not receipt:
            festival_pass["SeasonId"] = FIRST_FESTIVAL_SEASON
            festival_pass["Point"] = FIRST_FESTIVAL_POINTS
            claimed["Free"] = FIRST_FESTIVAL_LEVEL
            festival_pass["Cas"] += 1
            with self.db:
                self.db.execute(
                    "INSERT INTO festival_pass_claims VALUES(?,?,?)",
                    (FIRST_FESTIVAL_SEASON, FIRST_FESTIVAL_LEVEL, FIRST_FESTIVAL_POINTS),
                )
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {
            "UserFestivalPass": festival_pass,
            "AddedItems": [],
            "AddedPoint": FIRST_FESTIVAL_POINTS,
        }

    def add_character_experience(self, request, operation_id=None):
        if (self.references.directory / "training_catalog.json").is_file():
            return train_characters(self, request, operation_id)
        return self._initial_knight_training(request)

    def _initial_knight_training(self, request):
        """Apply the observed post-Inn knight level 1-to-2 tutorial once.

        Experiences contains deltas, not target totals. This narrow operation
        deliberately rejects other amounts until general training contracts and
        retry semantics have been implemented.
        """
        if (
            not isinstance(request, dict)
            or set(request) != {"Experiences"}
            or not isinstance(request["Experiences"], dict)
            or set(request["Experiences"]) != {"1"}
            or type(request["Experiences"]["1"]) is not int
            or request["Experiences"]["1"] != 37
        ):
            raise ValueError(
                "Only the initial knight tutorial's 37-experience upgrade is implemented"
            )
        profile = self.profile()
        user, progress, record = profile["User"], profile["UserProgress"], profile["UserRecord"]
        if (
            self.needs_prologue()
            or not progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED
        ):
            raise ValueError("Complete Inn before its knight training tutorial")
        knight = next((c for c in user["Characters"] if c["Id"] == 1), None)
        if knight is None or knight["CharacterId"] not in (1, 2):
            raise ValueError("The starting knight is missing")
        trained = self.db.execute(
            "SELECT experience FROM first_knight_training WHERE character_id=1"
        ).fetchone()
        if trained:
            if trained != (37,) or knight["Experience"] < 37:
                raise ValueError("Knight tutorial receipt does not match the saved character")
            return {"User": user, "UserRecord": record}
        experience = next(asset for asset in user["Assets"] if asset["Id"] == 70004)
        if knight["Experience"] != 0 or experience["Amount"] < 37:
            raise ValueError(
                "The initial knight upgrade requires level 1 and 37 available experience"
            )
        # The pinned APK displayed 37 for this tutorial and sent that delta.
        # It derives the displayed level from the character's Experience.
        experience["Amount"] -= 37
        knight["Experience"] = 37
        record["AddCharacterExperienceAmount"] += 37
        record["Cas"] += 1
        user["Cas"] += 1
        with self.db:
            self.db.execute("INSERT INTO first_knight_training VALUES(1,37)")
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        return {"User": user, "UserRecord": record}

    def mark_tutorial(self, request):
        """Persist known UI acknowledgments, keeping gameplay changes separate."""
        allowed = (
            set(PASSIVE_HELP_TUTORIALS)
            | set(POST_INN_TUTORIALS)
            | catalog_tutorial_ids(self.references)
        )
        if (
            not isinstance(request, dict)
            or not isinstance(request.get("tutorialIds"), list)
            or not 1 <= len(request["tutorialIds"]) <= 8
            or any(
                type(value) is not int or value not in allowed for value in request["tutorialIds"]
            )
        ):
            raise ValueError(
                "Only tutorial IDs from the configured catalog or built-in help are supported"
            )
        profile = self.profile()
        progress = profile["UserProgress"]
        if self.needs_prologue():
            raise ValueError("Finish local account creation before recording tutorials")
        if (
            any(value not in PASSIVE_HELP_TUTORIALS for value in request["tutorialIds"])
            and not progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED
        ):
            raise ValueError("Complete Inn before acknowledging its completion tutorial")
        changed = False
        for tutorial in request["tutorialIds"]:
            if tutorial not in progress["Tutorials"]:
                progress["Tutorials"].append(tutorial)
                changed = True
        if changed:
            progress["Cas"] += 1
            with self.db:
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {"UserProgress": progress}

    def interact_substage_item(self, request):
        return discover_substage(self, request)

    def start_quest(self, request):
        """Register a known quest in the active stage; progression and rewards are separate."""
        stage_id = request.get("StageId") if isinstance(request, dict) else None
        story = load_story_catalog(self.references)
        story_spec = story.get(str(stage_id)) if story else None
        allowed = {27}
        if stage_id != FIRST_STAGE_ID and story_spec:
            allowed = set(story_spec["quest_ids"])
        elif (self.references.directory / "quest_catalog.json").is_file():
            catalog = self.references.json("quest_catalog.json")
            chapters = catalog.get("chapters") if isinstance(catalog, dict) else None
            ids = chapters.get(str(FIRST_CHAPTER_CODE)) if isinstance(chapters, dict) else None
            if (
                not isinstance(ids, list)
                or not 1 <= len(ids) <= 10000
                or any(type(value) is not int or not 0 < value <= 0x7FFFFFFF for value in ids)
                or len(ids) != len(set(ids))
            ):
                raise ValueError("Invalid external chapter quest catalog")
            allowed.update(ids)
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or (request["StageId"] != FIRST_STAGE_ID and not story_spec)
            or type(request.get("QuestId")) is not int
            or request["QuestId"] not in allowed
            or request.get("StageCustom") is not None
        ):
            raise ValueError("Only known stage quests without custom start state can be registered")
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            stage_id,
        ):
            raise ValueError("Start the phase before starting its quest")
        profile = self.profile()
        progress = profile["UserProgress"]
        quest_id = request["QuestId"]
        if not any(quest["Id"] == quest_id for quest in progress["QuestProgresses"]):
            progress["QuestProgresses"].append(
                {"Id": quest_id, "Grade": -1, "InnerProgress": 0, "CustomStates": {}}
            )
            progress["Cas"] += 1
            with self.db:
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        # The native success callback adds its own QuestProgress instance.
        # Returning UserProgress here would add the same quest twice in memory.
        return {"OpenedStages": []}

    def beat_monsters(self, request):
        return record_defeated_monsters(self, request)

    def progress_quest(self, request):
        """Persist sequential main-quest checkpoints in the active configured stage."""
        stage_id = request.get("StageId") if isinstance(request, dict) else None
        story = load_story_catalog(self.references)
        story_spec = story.get(str(stage_id)) if story else None
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or (request["StageId"] != FIRST_STAGE_ID and not story_spec)
            or type(request.get("QuestId")) is not int
            or request["QuestId"] != 27
            or type(request.get("InnerProgress")) is not int
            or not 1 <= request["InnerProgress"] <= 12
            or request.get("StageCustom") is not None
        ):
            raise ValueError("Only initial quest checkpoints without stage unlocks are implemented")
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            stage_id,
        ):
            raise ValueError("Start the phase before progressing its quest")
        profile = self.profile()
        progress = profile["UserProgress"]
        quest = next((quest for quest in progress["QuestProgresses"] if quest["Id"] == 27), None)
        if quest is None:
            raise ValueError("Start the quest before progressing it")
        checkpoint = request["InnerProgress"]
        if checkpoint > quest["InnerProgress"] + 1:
            raise ValueError("Quest checkpoints must advance sequentially")
        if checkpoint > quest["InnerProgress"]:
            quest["InnerProgress"] = checkpoint
            progress["Cas"] += 1
            with self.db:
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {"OpenedStages": []}

    def draw_summon_characters(self, request, operation_id):
        return draw_characters(self, request, operation_id)

    def select_party_preset(self, request, operation_id):
        return set_selected_preset(self, request, operation_id)

    def save_party_preset(self, request, operation_id):
        return save_party_preset(self, request, operation_id)

    def delete_party_preset(self, request, operation_id):
        return delete_existing_preset(self, request, operation_id)

    def harvest_village(self, request, operation_id, now=None):
        return harvest_village(self, request, operation_id, now)

    def harvest_basecamp(self, request, operation_id, now=None):
        return harvest_basecamp(self, request, operation_id, now)

    def receive_village_gift(self, request, operation_id, now=None):
        return receive_village_gift(self, request, operation_id, now)

    def remove_village_obstacle(self, request, operation_id, now=None):
        return remove_village_obstacle(self, request, operation_id, now)

    def enhance_weapon(self, request, operation_id):
        return enhance_weapon(self, request, operation_id)

    def limit_break_weapon(self, request, operation_id):
        return limit_break_weapon(self, request, operation_id)

    def change_or_apply_weapon_options(self, request, operation_id, route):
        return change_or_apply_weapon_options(self, request, operation_id, route)

    def engrave_weapon(self, request, operation_id):
        return engrave_weapon(self, request, operation_id)

    def change_weapon_option_locks(self, request, operation_id):
        return change_weapon_option_locks(self, request, operation_id)

    def change_or_apply_relic_options(self, request, operation_id, route):
        return change_or_apply_relic_options(self, request, operation_id, route)

    def upgrade_guardian_mastery(self, request, operation_id):
        return upgrade_guardian_mastery(self, request, operation_id)

    def reset_guardian_mastery(self, request, operation_id, now=None):
        return reset_guardian_mastery(self, request, operation_id, now)

    def purchase_stamina(self, request, operation_id, now=None):
        return purchase_stamina(self, request, operation_id, now)

    def charge_stamina(self, request, now=None):
        return charge_stamina(self, request, now)

    def claim_hero_knowledge(self, request, operation_id):
        return claim_hero_knowledge(self, request, operation_id)

    def redeem_festival_points(self, request, operation_id):
        return redeem_points(self, request, operation_id)

    def read(self, route, request=None):
        if route == RAID_STAGE_EXIT_ROUTE:
            return exit_raid_stage(self, request)
        if route == RAID_STAGE_ENTRY_ROUTE:
            return enter_raid_stage(self, request)
        if route in RAID_MENU_READ_ROUTES:
            return read_raid_menu(self, route, request)
        if route in RAID_RANKING_ROUTES:
            return guild_raid_rankings(self, route, request)
        if route == "/guild-raid2/enter":
            return enter_guild_raid(self, request)
        if route in GUILD_MENU_ROUTES:
            return read_guild_menu(self, route, request)
        if route == "/user/get-user-profile-card":
            return read_profile_card(self, request)
        if route == "/festival-pass/check-not-redeemable":
            return check_not_redeemable(self, request)
        if route == "/summon/set-select-character":
            return select_characters(self, request)
        if route == "/auth/fetch-account":
            return self.profile()
        if route == "/mission/get-user-mission":
            return {"UserMission": self.profile()["UserMission"]}
        if route == "/guardian-pass/enter":
            if request is not None and request != {}:
                raise ValueError("Guardian Pass entry accepts no parameters")
            # The scene callbacks refresh from the global saved pass record.
            # Entry alone does not initialize a season or grant pass rewards.
            return {"UserGuardianPass": self.profile()["UserGuardianPass"]}
        if route == "/festival-pass/enter":
            if request is not None and request != {}:
                raise ValueError("Festival Pass entry accepts no parameters")
            # Native scene callbacks refresh from the global saved pass record.
            return {"UserFestivalPass": self.profile()["UserFestivalPass"]}
        if route == "/ad/init-inbox":
            if request is not None and request != {}:
                raise ValueError("Ad inbox initialization accepts no parameters")
            # Native callbacks open the inbox; global resource handling consumes
            # UserRecord. Preserve the local ad state without creating rewards.
            return {"UserRecord": self.profile()["UserRecord"]}
        if route == "/user/exchange-summon-pickup-ticket":
            return check_pickup_exchange(self, request)
        if route == "/stage/get-stage-progresses":
            result = initial_stage_progresses(request)
            progress = self.profile()["UserProgress"]
            for key in progress["StageStates"]:
                result["StageProgresses"].setdefault(key, "")
            catalog = load_story_catalog(self.references)
            if catalog is not None:
                for key in catalog:
                    result["StageProgresses"].setdefault(key, "")
            for key in result["StageProgresses"]:
                result["StageProgresses"][key] = self.stage_progress(int(key))
            if catalog is not None:
                result["UserProgress"] = progress
            return result
        if route == "/guild/list-item-request":
            return {"Requests": []}
        if route == "/chat/guild-history/v2":
            return {"History": []}
        if route == "/chat/listen-channel":
            if (
                not isinstance(request, dict)
                or set(request) != {"Listen", "Since"}
                or type(request["Listen"]) is not bool
                or request["Since"] is not None
            ):
                raise ValueError("Local empty-channel listening requires a null history cursor")
            return {"History": []}
        if route == "/collection/list-all":
            return {
                "ItemCollections": {},
                "CustomCollections": [],
                "ItemMastery": {},
                "NewItems": [],
                "NewCustomCollections": [],
                "NewItemMastery": [],
            }
        if route == "/collection/list-new":
            return {"NewItems": [], "NewCustomCollections": [], "NewItemMastery": []}
        if route == "/heavenholdfarm/collection-all":
            return {"FishCollections": {}, "NewFishes": [], "MaxFishes": []}
        if route == "/pasture/collection-all":
            return {
                "PastureMonsterCollections": {},
                "NewPastureMonsters": [],
                "MaxPastureMonsters": [],
            }
        if route == "/friend2/enter":
            if request is not None and (not isinstance(request, dict) or request):
                raise ValueError("Local empty friend entry accepts no parameters")
            # The profile popup refreshes this dictionary before rendering.
            # Peer records were not captured; do not reset saved UserFriend
            # counters, grant gifts or report an executed social migration.
            return {"FriendInfos": {}, "IsMigrated": False}
        if route == "/friend2/recommend":
            if request is not None and (not isinstance(request, dict) or request):
                raise ValueError("Local empty friend recommendations accept no parameters")
            return {"RecommendInfos": []}
        if route == "/friend2/has-changes":
            return {"Changed": False, "Gift": False}
        raise KeyError("Unsupported account route")
