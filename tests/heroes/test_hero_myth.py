# SPDX-License-Identifier: Apache-2.0
"""Myth eligibility follows the regional catalog link on the exact owned form."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.characters import new_character
from guardian_tales.hero_myth import ROUTE
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, digest
from tests.village.test_village_harvest import VillageFixture


class HeroMythTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()

        def form(ident, origin, rank, category="Unique", **extra):
            return dict(
                Id=ident,
                OriginId=origin,
                Rank=rank,
                SummonCategory=category,
                Playable=True,
                **extra,
            )

        self.tables = {
            "constants": {"MythCharacterRank": 6, "DreamMythStoneExchangeRate": 1},
            "exps2": {
                "Constants": {"MaxLimitBreak": 5},
                "MythCosts": [
                    {"Rank": 6, "SummonCategory": "Unique", "MythStoneCount": 40},
                    {"Rank": 6, "SummonCategory": "Story", "MythStoneCount": 20},
                ],
            },
            "items": [
                {"Id": 80, "Name": "dream_mythstone", "Type": "goods"},
                {"Id": 81, "Name": "dream_spiritstone", "Type": "goods"},
                *[dict(Id=i, Type="evolve_stone", StoneType="HeroMyth") for i in (93, 94)],
            ],
            "heroes": [
                form(11, 10, 4, MythTo={"Default": 13, "KakaoGlobal": 12}, MythStoneId=93),
                form(12, 10, 6),
                form(13, 10, 6),
                form(21, 20, 4, "Story"),
                form(22, 20, 5, "Story", MythTo={"Default": 23}, MythStoneId=94),
                form(23, 20, 6, "Story"),
                form(31, 30, 4),
                form(32, 30, 6),
                form(41, 40, 4, MythTo={"Kong": 42}, MythStoneId=93),
                form(42, 40, 6),
            ],
        }
        self.static = self.references / "static_data_get.bin"
        self.write_static()
        self.profile = self.store.account.profile()
        user = self.profile["User"]
        user["Characters"] = [
            dict(new_character(i, spec), LimitBreaks=5)
            for i, spec in enumerate((11, 21, 22, 31, 41), start=1)
        ]
        user["Characters"][0].update(
            Experience=1234, BlessLevel=2, Weapon1=33, SpriteRank=4, AwakeningTree="saved tree"
        )
        user["Assets"] = [dict(Id=80, Amount=50, Spent=2), dict(Id=81, Amount=500, Spent=5)]
        user["ItemStackables"] = [
            dict(Id=7, ItemId=93, Amount=6),
            dict(Id=9, ItemId=93, Amount=34),
            dict(Id=6, ItemId=94, Amount=20),
        ]
        user["TrainingSlots"] = {}
        self.profile["UserRecord"]["Misc"] = {"MythCharacterCount": 3, "Other": 8}
        self.save_profile(self.profile)

    def write_static(self):
        text = ""
        for key, table in self.tables.items():
            value = json.dumps(table)
            text += f"{key}\n{value}\n1\n{digest(value.encode())}\n"
        self.static.write_bytes(compress(text.encode()))

    def myth(self, who=1, dream=0, seq=51):
        return self.call(
            {"CharacterId": who, "DreamMythStoneUsageAmount": dream}, ROUTE, sequence=seq
        )

    def test_mixed_payment_regional_form_and_persistence(self):
        expected = copy.deepcopy(self.profile)
        user, record = expected["User"], expected["UserRecord"]
        user["Characters"][0]["CharacterId"] = 12
        user["Cas"] += 1
        user["Assets"][0].update(Amount=40, Spent=12)
        user["ItemStackables"].pop(0)
        user["ItemStackables"][0]["Amount"] = 10
        record["Cas"] += 1
        record["Misc"]["MythCharacterCount"] += 1
        result = self.myth(dream=10)
        roster_update = {
            k: user[k] for k in ("Id", "Cas", "Characters", "Assets", "ItemStackables")
        }
        self.assertEqual(result, {"User": roster_update, "UserRecord": record})
        self.assertEqual(self.store.account.profile(), expected)
        with self.assertRaises(PacketError):
            self.myth(seq=52)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(reconnect=True)
        self.static.unlink()
        self.assertEqual(self.myth(dream=10), result)
        for who, dream in ((1, 9), (3, 10)):
            with self.assertRaises(PacketError):
                self.myth(who, dream)
        self.assertEqual(self.store.account.profile(), expected)

    def test_personal_only_on_ascended_story_form_and_dream_only_on_unique(self):
        user = self.myth(3)["User"]
        self.assertEqual(user["Characters"][2]["CharacterId"], 23)
        self.assertEqual(user["Assets"], self.profile["User"]["Assets"])
        self.assertEqual(user["ItemStackables"], self.profile["User"]["ItemStackables"][:2])
        after = self.myth(dream=40, seq=52)["User"]
        self.assertEqual(after["Assets"][0], dict(Id=80, Amount=10, Spent=42))
        self.assertEqual(after["ItemStackables"], user["ItemStackables"])

    def test_no_myth_without_valid_regional_link_and_permanent_breaks(self):
        for who in (2, 4, 5, 30):
            with self.assertRaises(PacketError):
                self.myth(who)
        for change in (
            lambda p: p["User"]["Characters"][0].update(LimitBreaks=4),
            lambda p: p["User"].update(TrainingSlots={"1": {"CharacterId": 1, "IsMyth": True}}),
            lambda p: p["User"].update(ItemStackables=[dict(Id=6, ItemId=94, Amount=200)]),
            lambda p: p["User"]["Assets"][0].update(Amount=0),
        ):
            profile = copy.deepcopy(self.profile)
            change(profile)
            self.save_profile(profile)
            with self.assertRaises(PacketError):
                self.myth(dream=10)
            self.assertEqual(self.store.account.profile(), profile)

    def test_invalid_target_or_receipt_failure_preserves_all_balances(self):
        for field, value in (("OriginId", 999), ("Rank", 5), ("Playable", False)):
            target = self.tables["heroes"][1]
            original = target[field]
            target[field] = value
            self.write_static()
            with self.assertRaises(PacketError):
                self.myth()
            target[field] = original
        self.write_static()
        self.db.execute(
            "CREATE TRIGGER reject_myth BEFORE INSERT ON hero_myth_requests BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.myth(dream=20)
        self.assertEqual(self.store.account.profile(), self.profile)
