# SPDX-License-Identifier: Apache-2.0
"""Hero Reset preserves ownership, equipment, collection progress and balances."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.heroes.characters import new_character
from guardian_tales.heroes.hero_reset import ROUTE
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import MAX_REVISION
from tests.village.test_village_harvest import VillageFixture


class HeroResetTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        specs = [
            (501, 501, 2, "Unique"),
            (505, 501, 4, "Unique"),
            (951, 501, 6, "Unique"),
            (102, 102, 1, "Story"),
            (132, 102, 3, "Story"),
            (142, 102, 4, "Story"),
            (152, 102, 5, "Story"),
            (162, 102, 6, "Story"),
            (205, 205, 0, "Normal"),
            (245, 205, 4, "Normal"),
        ]
        heroes = [
            dict(Id=ident, OriginId=origin, Rank=rank, SummonCategory=category, Playable=True)
            for ident, origin, rank, category in specs
        ]
        text = ""
        for name, data in (("heroes", heroes), ("items", [{"Id": 110003}])):
            content = json.dumps(data)
            text += f"{name}\n{content}\n1\n{digest(content.encode())}\n"
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(compress(text.encode()))
        profile = self.store.account.profile()
        hero = new_character(7, 951, 81)
        hero.update(
            Experience=341,
            LimitBreaks=5,
            RankUpgrade=2,
            SpriteRank=4,
            BlessLevel=3,
            AwakeningTree="abc",
            AwakeningTreeGold=70,
            Costume=90,
            Knowledge=99,
            Flag=15,
        )
        user = profile["User"]
        user.update(
            Characters=[hero, new_character(9, 505)],
            RepresentativeCharacterId=7,
            TrainingSlots={"1": {"Id": 1, "CharacterId": 9}},
        )
        user["ItemStackables"] = [{"Id": 123, "ItemId": 110003, "Amount": 4}]
        self.save_profile(profile)
        self.body = {"CharacterId": 7, "ReceiveCrystal": True}

    def test_myth_unique_reset_changes_only_owned_hero_growth_and_persists(self):
        expected = self.store.account.profile()
        user = expected["User"]
        user["Characters"][0].update(
            CharacterId=501,
            Experience=0,
            LimitBreaks=0,
            RankUpgrade=0,
            BlessLevel=0,
            AwakeningTree="",
            AwakeningTreeGold=0,
            SpriteRank=None,
        )
        user["Cas"] += 1
        reply = self.call(self.body, ROUTE)
        self.assertEqual(
            reply, {"User": {k: user[k] for k in ("Id", "Cas", "Characters")}, "AddedItems": []}
        )
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.call(self.body, ROUTE), reply)

    def test_reset_forms_follow_rarity_and_both_choices_work_without_a_stone(self):
        base = self.store.account.profile()
        for seq, (spec, expected, upgrade, sprite) in enumerate(
            (
                (505, 501, 0, None),
                (132, 132, 2, None),
                (245, 245, 2, 4),
                (152, 142, 0, 4),
                (162, 142, 0, 4),
            )
        ):
            with self.subTest(spec=spec):
                profile = copy.deepcopy(base)
                profile["User"]["ItemStackables"] = []
                profile["User"]["Characters"][0]["CharacterId"] = spec
                self.save_profile(profile)
                reply = self.call(dict(self.body, ReceiveCrystal=False), ROUTE, sequence=100 + seq)
                hero = reply["User"]["Characters"][0]
                self.assertEqual(
                    (hero["CharacterId"], hero["RankUpgrade"], hero["SpriteRank"]),
                    (expected, upgrade, sprite),
                )
                self.assertEqual(hero["Experience"], 0)
                self.assertEqual(reply["AddedItems"], [])
                self.assertEqual(self.store.account.profile()["User"]["ItemStackables"], [])

    def test_old_retry_keeps_later_growth_even_after_catalog_removal(self):
        self.call(self.body, ROUTE)
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["Experience"] = 800
        self.save_profile(profile)
        self.static.unlink()
        writes = self.db.total_changes
        self.assertEqual(
            self.call(self.body, ROUTE)["User"]["Characters"], profile["User"]["Characters"]
        )
        for mismatch in (dict(self.body, CharacterId=9), dict(self.body, ReceiveCrystal=False)):
            with self.assertRaises(PacketError):
                self.call(mismatch, ROUTE)
        self.assertEqual(self.db.total_changes, writes)

    def test_rejects_invalid_unowned_training_and_experimental_selections(self):
        before = self.store.account.profile()
        for body in (
            {},
            dict(self.body, CharacterId=True),
            dict(self.body, ReceiveCrystal=1),
            dict(self.body, CharacterId=951),
            dict(self.body, CharacterId=9),
        ):
            with self.assertRaises(PacketError):
                self.call(body, ROUTE)
        trial = dict(
            version=1,
            active=True,
            generation=1,
            owner_id=before["User"]["Id"],
            inventory_id=7,
            source_sha256="0" * 64,
        )
        (self.references / "andras_myth_trial.json").write_text(json.dumps(trial))
        self.session.andras_trial_selection = trial
        with self.assertRaisesRegex(PacketError, "Disable the experimental Andras trial"):
            self.call(self.body, ROUTE)
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM hero_reset_requests").fetchone(), (0,)
        )

    def test_receipt_failure_and_revision_overflow_leave_all_development_untouched(self):
        before = self.store.account.profile()
        self.db.execute(
            "CREATE TRIGGER reject_reset BEFORE INSERT ON hero_reset_requests BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.body, ROUTE)
        self.assertEqual(self.store.account.profile(), before)
        before["User"]["Cas"] = MAX_REVISION
        self.save_profile(before)
        with self.assertRaises(PacketError):
            self.call(self.body, ROUTE)
        self.assertEqual(self.store.account.profile(), before)
