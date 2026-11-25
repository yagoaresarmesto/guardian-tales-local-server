# SPDX-License-Identifier: Apache-2.0
"""Ordinary hero evolution uses the selected Dream budget and the current form's stones."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.characters import new_character
from guardian_tales.hero_evolution import ROUTE
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, digest
from tests.test_village_harvest import VillageFixture


class HeroEvolutionTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        data = {
            "items": [{"Id": 90, "Type": "goods", "Name": "dream_spiritstone"}],
            "heroes": [],
            "constants": {
                "DreamSpiritStoneExchangeRate": 1,
                "DreamSpiritStoneStoryExchangeRate": 2,
                "DreamSpiritStoneNormalExchangeRate": 5,
            },
            "exps2": {
                "Evolves": [
                    {"Rank": rank, "Upgrade": i, "UpgradeCost": 40, "IsEvolve": i == size - 1}
                    for rank, size in ((1, 3), (2, 4))
                    for i in range(size)
                ]
            },
        }
        for ident, category in enumerate(("Unique", "Story", "Normal"), start=1):
            stone = 100 + ident
            data["items"].append({"Id": stone, "Type": "evolve_stone"})
            for i in range(3):
                spec = ident * 10 + i
                data["heroes"].append(
                    dict(
                        Id=spec,
                        OriginId=ident * 10,
                        Playable=True,
                        Rank=i + 1,
                        SummonCategory=category,
                        EvolveTo=spec + 1 if i < 2 else 0,
                        EvolvingStoneId=stone if i < 2 else 0,
                    )
                )
        text = ""
        for key, table in data.items():
            value = json.dumps(table)
            text += f"{key}\n{value}\n1\n{digest(value.encode())}\n"
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(compress(text.encode()))
        self.profile = self.store.account.profile()
        user = self.profile["User"]
        user["Characters"] = [new_character(i, i * 10) for i in (1, 2, 3)]
        user["Characters"][0].update(Experience=300, Weapon1=144, BlessLevel=2, SpriteRank=1)
        user["ItemStackables"] = [
            {"Id": 3, "ItemId": 101, "Amount": 114},
            {"Id": 2, "ItemId": 101, "Amount": 6},
            {"Id": 4, "ItemId": 102, "Amount": 80},
        ]
        user["Assets"] = [{"Id": 90, "Amount": 130, "Spent": 7}]
        user["TrainingSlots"] = {}
        self.profile["UserRecord"]["EvolveCharacterCount"] = 8
        self.save_profile(self.profile)

    def evolve(self, who=1, count=1, dream=0, seq=51):
        return self.call(
            {"CharacterId": who, "UpgradeCount": count, "DreamSpiritStoneUsageAmount": dream},
            ROUTE,
            sequence=seq,
        )

    def test_personal_split_stacks_and_rank_change_preserve_other_progress(self):
        self.profile["User"]["Assets"] = []
        self.save_profile(self.profile)
        expected = copy.deepcopy(self.profile)
        user, record = expected["User"], expected["UserRecord"]
        hero = user["Characters"][0]
        self.evolve(count=2)
        user["Cas"] += 1
        hero["RankUpgrade"] = 2
        user["ItemStackables"].pop(1)
        user["ItemStackables"][0]["Amount"] = 40
        self.assertEqual(self.store.account.profile(), expected)
        result = self.evolve(seq=52)
        hero.update(CharacterId=11, RankUpgrade=0)
        user["Cas"] += 1
        user["ItemStackables"].pop(0)
        record["Cas"] += 1
        record["EvolveCharacterCount"] += 1
        self.assertEqual(result, {"User": user, "UserRecord": record})
        self.assertEqual(self.store.account.profile(), expected)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(reconnect=True)
        self.static.unlink()
        self.assertEqual(self.evolve(count=2), result)
        self.assertEqual(self.evolve(seq=52), result)
        for args in ({"who": 2, "count": 2}, {"count": 1}, {"count": 2, "dream": 1}):
            with self.assertRaises(PacketError):
                self.evolve(**args)

    def test_dream_slider_budget_is_capped_to_actual_step_by_rarity(self):
        for who, cost in ((1, 40), (2, 20), (3, 8)):
            before = self.store.account.profile()["User"]
            after = self.evolve(who, dream=120, seq=50 + who)["User"]
            self.assertEqual(after["Assets"][0]["Amount"], before["Assets"][0]["Amount"] - cost)
            self.assertEqual(after["Assets"][0]["Spent"], before["Assets"][0]["Spent"] + cost)
            self.assertEqual(after["ItemStackables"], before["ItemStackables"])
            self.assertEqual(after["Characters"][who - 1]["RankUpgrade"], 1)

    def test_dream_first_then_only_the_selected_heros_stones(self):
        result = self.evolve(2, count=3, dream=25)
        user = result["User"]
        self.assertEqual(user["Characters"][1]["CharacterId"], 21)
        self.assertEqual(user["Assets"], [{"Id": 90, "Amount": 105, "Spent": 32}])
        self.assertEqual(user["ItemStackables"][-1]["Amount"], 10)
        self.assertEqual(user["ItemStackables"][:-1], self.profile["User"]["ItemStackables"][:-1])
        self.evolve(2, count=4, dream=80, seq=52)
        before = self.store.account.profile()
        self.assertEqual(before["User"]["Characters"][1]["CharacterId"], 22)
        with self.assertRaises(PacketError):
            self.evolve(2, dream=1, seq=53)
        self.assertEqual(self.store.account.profile(), before)

    def test_unaffordable_invalid_or_out_of_rank_requests_are_atomic(self):
        for args in (
            {"who": 3},
            {"who": 3, "dream": 7},
            {"who": 999},
            {"count": 4},
            {"count": 0},
            {"count": True},
            {"dream": False},
            {"dream": -1},
        ):
            with self.subTest(args=args), self.assertRaises(PacketError):
                self.evolve(**args)
            self.assertEqual(self.store.account.profile(), self.profile)
        self.profile["User"]["Assets"][0]["Amount"] = 8
        self.save_profile(self.profile)
        with self.assertRaises(PacketError):
            self.evolve(dream=40)
        self.profile["User"]["TrainingSlots"] = {"1": {"CharacterId": 1, "IsEvolveOnly": True}}
        self.save_profile(self.profile)
        with self.assertRaises(PacketError):
            self.evolve()
        self.assertEqual(self.store.account.profile(), self.profile)
        self.evolve(2)

    def test_receipt_failure_rolls_back_rank_and_both_payments(self):
        self.db.execute(
            "CREATE TRIGGER reject_evolve BEFORE INSERT ON hero_evolution_requests BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.evolve(count=3, dream=60)
        self.assertEqual(self.store.account.profile(), self.profile)
