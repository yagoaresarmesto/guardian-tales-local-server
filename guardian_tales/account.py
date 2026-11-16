# SPDX-License-Identifier: Apache-2.0
"""Persistent new local guest and read-only empty social/collection state.

The account starts empty; the client creates its own temporary prologue party.
Completion creates one knight and the two selected starting weapon slots. No
reference player's inventory, balance, progress or credentials are included.
Campaign battle results and most reward-changing operations remain unimplemented.
"""

import base64
import hashlib
import json
from datetime import datetime, timezone

from .campaign import (
    CHARGED_STAMINA,
    FIRST_CLEAR_GEMS,
    FIRST_MONSTER_EXP,
    FIRST_MONSTER_GOLD,
    FIRST_MONSTERS,
    FIRST_PURPLE_COIN,
    FIRST_PURPLE_COIN_KEYS,
    FIRST_STAGE_ID,
    FIRST_STAGE_ITEMS,
    FIRST_STAGE_STAMINA,
    FREE_GEMS,
    RESERVE_STAMINA,
    STAGE_CLEARED,
    STAGE_OPENED,
    STAGE_UNLOCKED,
    encode_stage_progress,
    initial_stage_progresses,
)
from .missions import (
    BEGINNER_REWARDS,
    FIRST_HERO_CHALLENGE_GEMS,
    FIRST_HERO_CHALLENGE_GROUP,
    FIRST_HERO_CHALLENGE_STEP,
    STAMINA_MISSION_SPEND,
)
from .reference import ReferenceData
from .tutorials import PASSIVE_HELP_TUTORIALS, POST_INN_TUTORIALS

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
    "/mission/claim-beginner-all",
    "/mission/claim-challenge-all",
    "/ad/init-inbox",
    "/guardian-pass/enter",
    "/user/exchange-summon-pickup-ticket",
    "/stage/get-stage-progresses",
    "/stage/start-stage",
    "/stage/start-quest",
    "/stage/progress-quest",
    "/stage/pick-stage-coins",
    "/stage/beat-monsters",
    "/stage/pick-stage-item",
    "/stage/open-treasure",
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
            "CREATE TABLE IF NOT EXISTS beginner_mission_claims (mission_id INTEGER PRIMARY KEY, rewards TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS challenge_mission_claims (group_id INTEGER NOT NULL, step INTEGER NOT NULL, rewards TEXT NOT NULL, PRIMARY KEY(group_id,step))"
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
        if (
            not isinstance(request, dict)
            or type(request.get("StageId")) is not int
            or request["StageId"] != FIRST_STAGE_ID
            or request.get("ExitName") != "exit_forest_1_2"
            or request.get("IsClearExit") is not True
        ):
            raise ValueError("Only the first phase's clear exit is implemented")
        custom = request.get("StageCustom")
        hit_count = no_damage = None
        if custom is not None:
            empty = {
                "StageId",
                "Category",
                "CustomValues",
                "QuestId",
                "QuestCustomState",
                "ClearInTime",
                "Score",
                "ChallengeA",
                "ChallengeB",
            }
            if (
                not isinstance(custom, dict)
                or set(custom) - empty - {"HitCount", "NoDamage"}
                or any(custom.get(key) is not None for key in empty)
                or (
                    custom.get("HitCount") is not None
                    and (
                        type(custom["HitCount"]) is not int
                        or not 0 <= custom["HitCount"] <= 1000000
                    )
                )
                or (custom.get("NoDamage") is not None and type(custom["NoDamage"]) is not bool)
            ):
                raise ValueError("Unsupported first-phase completion custom state")
            hit_count, no_damage = custom.get("HitCount"), custom.get("NoDamage")
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
            if not completed or not grade_claimed:
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
        """Grant one supported beginner mission per batch with a persistent receipt."""
        if (
            not isinstance(request, dict)
            or set(request) != {"missionIds"}
            or not isinstance(request["missionIds"], list)
            or not 1 <= len(request["missionIds"]) <= 32
            or any(
                type(value) is not int or value not in BEGINNER_REWARDS
                for value in request["missionIds"]
            )
            or len(set(request["missionIds"])) != 1
        ):
            raise ValueError("Only beginner missions 0, 1 or 9 in separate batches are implemented")
        mission_id = request["missionIds"][0]
        profile = self.profile()
        user, progress, mission = profile["User"], profile["UserProgress"], profile["UserMission"]
        if self.needs_prologue():
            raise ValueError("Finish local account creation before claiming missions")
        if (
            mission_id == 0
            and not progress["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED
        ):
            raise ValueError("Complete Inn before claiming its beginner mission")
        if mission_id == 1:
            knight = next((c for c in user["Characters"] if c["Id"] == 1), None)
            trained = self.db.execute(
                "SELECT experience FROM first_knight_training WHERE character_id=1"
            ).fetchone()
            if trained != (37,) or knight is None or knight["Experience"] < 37:
                raise ValueError("Reach knight level 2 before claiming its beginner mission")
        if mission_id == 9:
            # The native UsedStamina getter sums these two assets' Spent fields.
            spent = sum(
                a["Spent"] for a in user["Assets"] if a["Id"] in (CHARGED_STAMINA, RESERVE_STAMINA)
            )
            if spent < STAMINA_MISSION_SPEND:
                raise ValueError("Spend 10 stamina before claiming its beginner mission")
        bits = bytearray(base64.b64decode(mission["GuideClaimed"], validate=True))
        byte_index, bit_index = divmod(mission_id, 8)
        mask = 1 << bit_index
        marked = byte_index < len(bits) and bool(bits[byte_index] & mask)
        claimed = self.db.execute(
            "SELECT rewards FROM beginner_mission_claims WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if bool(claimed) != marked:
            raise ValueError("Mission receipt does not match saved claim flags")
        if claimed:
            return {"User": user, "UserMission": mission, "AddedItems": json.loads(claimed[0])}

        rewards = []
        for item_id, amount in BEGINNER_REWARDS[mission_id]:
            if item_id in (FREE_GEMS, RESERVE_STAMINA):
                next(a for a in user["Assets"] if a["Id"] == item_id)["Amount"] += amount
                inventory_id = 0
            else:
                item = next((i for i in user["ItemStackables"] if i["ItemId"] == item_id), None)
                if item is None:
                    user["ItemIdCounter"] += 1
                    item = inventory_item(user["ItemIdCounter"], item_id)
                    item["Amount"] = 0
                    user["ItemStackables"].append(item)
                item["Amount"] += amount
                inventory_id = item["Id"]
            rewards.append({"Id": inventory_id, "ItemId": item_id, "Amount": amount})
        bits.extend(bytes(max(0, byte_index + 1 - len(bits))))
        bits[byte_index] |= mask
        mission["GuideClaimed"] = base64.b64encode(bits).decode("ascii")
        mission["Cas"] += 1
        user["Cas"] += 1
        with self.db:
            self.db.execute(
                "INSERT INTO beginner_mission_claims VALUES(?,?)", (mission_id, json.dumps(rewards))
            )
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        return {"User": user, "UserMission": mission, "AddedItems": rewards}

    def claim_challenge_missions(self, request):
        """Grant only the one-knight account's first collect-hero challenge step."""
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

    def add_character_experience(self, request):
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
        """Persist post-Inn acknowledgments and catalog-verified passive help views."""
        if (
            not isinstance(request, dict)
            or not isinstance(request.get("tutorialIds"), list)
            or not 1 <= len(request["tutorialIds"]) <= 8
            or any(
                type(value) is not int
                or (value not in POST_INN_TUTORIALS and value not in PASSIVE_HELP_TUTORIALS)
                for value in request["tutorialIds"]
            )
        ):
            raise ValueError(
                "Only post-Inn acknowledgments and the pinned passive help tutorials are implemented"
            )
        profile = self.profile()
        progress = profile["UserProgress"]
        if self.needs_prologue():
            raise ValueError("Finish local account creation before recording tutorials")
        if (
            any(value in POST_INN_TUTORIALS for value in request["tutorialIds"])
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
        if route == "/guardian-pass/enter":
            if request is not None and request != {}:
                raise ValueError("Guardian Pass entry accepts no parameters")
            # The scene callbacks refresh from the global saved pass record.
            # Entry alone does not initialize a season or grant pass rewards.
            return {"UserGuardianPass": self.profile()["UserGuardianPass"]}
        if route == "/ad/init-inbox":
            if request is not None and request != {}:
                raise ValueError("Ad inbox initialization accepts no parameters")
            # Native callbacks open the inbox; global resource handling consumes
            # UserRecord. Preserve the local ad state without creating rewards.
            return {"UserRecord": self.profile()["UserRecord"]}
        if route == "/user/exchange-summon-pickup-ticket":
            if request is not None and request != {}:
                raise ValueError("Pickup ticket exchange accepts no parameters")
            shop = self.profile()["UserShop"]
            if shop["SummonPickUpTickets"] or shop["CollaborationPickUpTickets"]:
                raise ValueError("Exchange of existing event pickup tickets is not implemented")
            # These event coupon maps differ from regular/selectable inventory
            # tickets. No exchange is needed when both saved maps are empty.
            return {
                "UserShop": shop,
                "ExchangeSummonPickUpTickets": {},
                "ExchangeCollaborationPickUpTickets": {},
            }
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
