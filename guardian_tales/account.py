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
        db.execute(
            "CREATE TABLE IF NOT EXISTS local_account (id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER NOT NULL, profile TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS prologue_selection (id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, info TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS attendance_claims (day TEXT PRIMARY KEY, attendance_count INTEGER NOT NULL)"
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
                weapons.append(
                    dict(
                        Id=len(weapons) + 1,
                        ItemId=spec,
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
                )
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

    def read(self, route):
        if route == "/auth/fetch-account":
            return self.profile()
        if route == "/mission/get-user-mission":
            return {"UserMission": self.profile()["UserMission"]}
        if route == "/stage/get-stage-progresses":
            return {"StageProgresses": {}}
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
