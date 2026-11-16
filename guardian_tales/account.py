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

from .campaign import (
    CHARGED_STAMINA,
    FIRST_MONSTER_EXP,
    FIRST_MONSTER_GOLD,
    FIRST_MONSTERS,
    FIRST_PURPLE_COIN,
    FIRST_PURPLE_COIN_KEYS,
    FIRST_STAGE_ID,
    FIRST_STAGE_ITEMS,
    FIRST_STAGE_STAMINA,
    RESERVE_STAMINA,
    STAGE_OPENED,
    STAGE_UNLOCKED,
    encode_stage_progress,
    initial_stage_progresses,
)
from .reference import ReferenceData

ACCOUNT_ROUTES = (
    "/auth/fetch-account",
    "/guild/list-item-request",
    "/guild/get-my-guild",
    "/chat/guild-history/v2",
    "/collection/list-all",
    "/collection/list-new",
    "/heavenholdfarm/collection-all",
    "/pasture/collection-all",
    "/friend2/has-changes",
    "/mission/get-user-mission",
    "/stage/get-stage-progresses",
    "/stage/start-stage",
    "/stage/start-quest",
    "/stage/progress-quest",
    "/stage/pick-stage-coins",
    "/stage/beat-monsters",
    "/stage/pick-stage-item",
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


def inventory_item(inventory_id, item_id):
    """Construct the common persistent inventory shape with default options."""
    return dict(
        Id=inventory_id,
        ItemId=item_id,
        Amount=1,
        Experience=0,
        EvolveProgress=0,
        Options=None,
        RelicOptions=None,
        LimitBreaks=0,
        Locked=False,
        JewelSlots=None,
        EngraveOptions=None,
        EngraveCeiling=0,
    )


class AccountStore:
    def __init__(self, db, reference_dir=None):
        self.db = db
        self.references = ReferenceData(reference_dir)
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

    def profile(self):
        return json.loads(
            self.db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
        )

    def needs_prologue(self):
        return not bool(self.db.execute("SELECT 1 FROM prologue_selection WHERE id=1").fetchone())

    def complete_prologue(self, name, info):
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
        knight = dict(
            Id=1,
            CharacterId=2 if info["IsMale"] else 1,
            Experience=0,
            LimitBreaks=0,
            Weapon1=slots[0],
            Weapon2=slots[1],
            Accessory1=None,
            Costume=None,
            Orb1=None,
            Orb2=None,
            Merch=None,
            Relic=None,
            EquipCostumes={},
            AwakeningTree="",
            Knowledge=0,
            RankUpgrade=0,
            SpriteRank=None,
            BlessLevel=0,
            AwakeningTreeGold=0,
            Flag=0,
        )
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

    def claim_attendance(self, now=None):
        """Grant catalog ASSET rewards once per UTC day; item rolls are pending."""
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
        """Unlock the first phase once, then allow free retries of that phase."""
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
        """Collect first-phase purple coins once per public tilemap key."""
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or request.get("StageCustom") is not None
            or not isinstance(request.get("Items"), list)
            or not 1 <= len(request["Items"]) <= len(FIRST_PURPLE_COIN_KEYS)
        ):
            raise ValueError("Malformed first-phase coin request")
        keys = set()
        for item in request["Items"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"Id", "ItemId"}
                or type(item["Id"]) is not int
                or item["Id"] not in FIRST_PURPLE_COIN_KEYS
                or type(item["ItemId"]) is not int
                or item["ItemId"] != FIRST_PURPLE_COIN
            ):
                raise ValueError("Unknown first-phase purple coin")
            keys.add(item["Id"])
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            FIRST_STAGE_ID,
        ):
            raise ValueError("Start the phase before collecting its coins")
        profile = self.profile()
        user = profile["User"]
        with self.db:
            added = 0
            for key in keys:
                added += self.db.execute(
                    "INSERT OR IGNORE INTO campaign_progress VALUES(?,?,?,?)",
                    (FIRST_STAGE_ID, 2, key, "true"),
                ).rowcount
            if added:
                next(asset for asset in user["Assets"] if asset["Id"] == FIRST_PURPLE_COIN)[
                    "Amount"
                ] += added
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
                    (FIRST_STAGE_ID, 4, index, "true"),
                )
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {"User": user, "AddedItem": item}

    def start_quest(self, request):
        """Persist the first phase's initial quest without claiming completion."""
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or type(request.get("QuestId")) is not int
            or request["QuestId"] != 27
            or request.get("StageCustom") is not None
        ):
            raise ValueError("Only the first phase's initial quest is implemented")
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            FIRST_STAGE_ID,
        ):
            raise ValueError("Start the phase before starting its quest")
        profile = self.profile()
        progress = profile["UserProgress"]
        if not any(quest["Id"] == 27 for quest in progress["QuestProgresses"]):
            progress["QuestProgresses"].append(
                {"Id": 27, "Grade": -1, "InnerProgress": 0, "CustomStates": {}}
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
        """Record the first encounter once using a provisional local drop rule."""
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or request.get("StageCustom") is not None
            or not isinstance(request.get("MonsterHandleNames"), list)
            or not 1 <= len(request["MonsterHandleNames"]) <= len(FIRST_MONSTERS)
            or any(
                not isinstance(name, str) or name not in FIRST_MONSTERS
                for name in request["MonsterHandleNames"]
            )
        ):
            raise ValueError("Only the first phase's initial monster encounter is implemented")
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            FIRST_STAGE_ID,
        ):
            raise ValueError("Start the phase before reporting defeated monsters")
        profile = self.profile()
        user = profile["User"]
        with self.db:
            added = 0
            for name in set(request["MonsterHandleNames"]):
                added += self.db.execute(
                    "INSERT OR IGNORE INTO campaign_progress VALUES(?,?,?,?)",
                    (FIRST_STAGE_ID, 10, FIRST_MONSTERS[name], "true"),
                ).rowcount
            exp, gold = added * FIRST_MONSTER_EXP, added * FIRST_MONSTER_GOLD
            if added:
                assets = {asset["Id"]: asset for asset in user["Assets"]}
                assets[70004]["Amount"] += exp
                assets[70001]["Amount"] += gold
                user["Cas"] += 1
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
        return {"User": user, "DropExp": exp, "DropGold": gold}

    def progress_quest(self, request):
        """Persist sequential quest checkpoints before its first catalog stage unlock."""
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or type(request.get("QuestId")) is not int
            or request["QuestId"] != 27
            or type(request.get("InnerProgress")) is not int
            or not 1 <= request["InnerProgress"] <= 12
            or request.get("StageCustom") is not None
        ):
            raise ValueError("Only initial quest checkpoints without stage unlocks are implemented")
        if self.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
            FIRST_STAGE_ID,
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

    def read(self, route, request=None):
        if route == "/auth/fetch-account":
            return self.profile()
        if route == "/mission/get-user-mission":
            return {"UserMission": self.profile()["UserMission"]}
        if route == "/stage/get-stage-progresses":
            result = initial_stage_progresses(request)
            result["StageProgresses"][str(FIRST_STAGE_ID)] = self.stage_progress(FIRST_STAGE_ID)
            return result
        if route == "/guild/list-item-request":
            return {"Requests": []}
        if route == "/guild/get-my-guild":
            return {"Hash": 0, "Guild": None, "GuildMember": None, "GuildMembers": []}
        if route == "/chat/guild-history/v2":
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
        if route == "/friend2/has-changes":
            return {"Changed": False, "Gift": False}
        raise KeyError("Unsupported account route")
