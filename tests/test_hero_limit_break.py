# SPDX-License-Identifier: Apache-2.0
"""Limit breaks charge the selected hero's rarity and its next available steps."""

import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.characters import new_character
from guardian_tales.hero_catalog import growth_tables, warm_growth_tables
from guardian_tales.hero_limit_break import ROUTE, rules
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest
from guardian_tales.village import MAX_REVISION
from tests.test_village_harvest import VillageFixture


class HeroLimitBreakTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        forms = ((11, 4, "Unique"), (22, 5, "Story"), (33, 4, "Normal"), (44, 3, "Unique"))
        tables = {
            "items": [{"Id": 80, "Type": "goods", "Name": "herocrystal"}],
            "heroes": [
                dict(Id=ident, Rank=rank, Playable=True, SummonCategory=rarity)
                for ident, rank, rarity in forms
            ],
            "exps2": {
                "Constants": {"MaxLimitBreak": 3},
                "LimitBreaks": [
                    dict(
                        LimitBreak=i,
                        HeroCrystalReqNormal=2 + i,
                        HeroCrystalReqStory=5 + i,
                        HeroCrystalReqUnique=10 + i,
                    )
                    for i in (2, 0, 1)
                ],
            },
        }
        text = ""
        for name, table in tables.items():
            value = json.dumps(table)
            text += f"{name}\n{value}\n1\n{digest(value.encode())}\n"
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(compress(text.encode()))
        self.profile = self.store.account.profile()
        user = self.profile["User"]
        user["Characters"] = [new_character(i, form[0]) for i, form in enumerate(forms, start=1)]
        user["Characters"][0].update(Experience=1, Weapon1=91, BlessLevel=1)
        user["Assets"] = [
            {"Id": 80, "Amount": 50, "Spent": 8},
            {"Id": 81, "Amount": 200, "Spent": 4},
        ]
        user["TrainingSlots"] = {}
        self.profile["UserRecord"]["LimitBreakCharacterCount"] = 19
        self.save_profile(self.profile)

    def run_break(self, who=1, count=1, seq=51):
        return self.call({"CharacterId": who, "LimitBreakCount": count}, ROUTE, sequence=seq)

    def test_warmed_tables_follow_pack_content_and_still_reject_invalid_records(self):
        growth_tables.cache_clear()
        rules.cache_clear()
        with patch("guardian_tales.hero_catalog.decode", wraps=decode) as unpack:
            warm_growth_tables(self.store.references)
            self.assertEqual(self.run_break()["User"]["Assets"][0]["Amount"], 40)
            self.assertEqual(unpack.call_count, 1)
            # Replace the pack under the same filename; even unused tables need valid checksums.
            raw = decode(self.static.read_bytes()) + b"unrelated\n[]\n1\ninvalid\n"
            self.static.write_bytes(compress(raw))
            warm_growth_tables(self.store.references)
            with self.assertRaises(PacketError):
                self.run_break(seq=52)
            self.assertEqual(self.store.account.profile()["User"]["Assets"][0]["Amount"], 40)

    def test_single_then_bulk_only_charge_new_steps_and_retry_after_reconnect(self):
        expected = copy.deepcopy(self.profile)
        user, record = expected["User"], expected["UserRecord"]
        for count, seq, cost in ((1, 51, 10), (2, 52, 23)):
            result = self.run_break(count=count, seq=seq)
            user["Characters"][0]["LimitBreaks"] += count
            user["Assets"][0]["Amount"] -= cost
            user["Assets"][0]["Spent"] += cost
            record["LimitBreakCharacterCount"] += count
            user["Cas"] += 1
            record["Cas"] += 1
            roster_update = {k: user[k] for k in ("Id", "Cas", "Characters", "Assets")}
            self.assertEqual(result, {"User": roster_update, "UserRecord": record})
            self.assertEqual(self.store.account.profile(), expected)
        with self.assertRaises(PacketError):
            self.run_break(seq=53)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(reconnect=True)
        self.static.unlink()
        self.assertEqual(self.run_break(), result)
        self.assertEqual(self.run_break(count=2, seq=52), result)
        for who, count in ((2, 1), (1, 2)):
            with self.assertRaises(PacketError):
                self.run_break(who, count)
        self.assertEqual(self.store.account.profile(), expected)

    def test_other_rarities_use_their_own_prices(self):
        for who, cost in ((2, 18), (3, 9)):
            before = self.store.account.profile()
            after = self.run_break(who, 3, seq=who)["User"]
            self.assertEqual(after["Characters"][who - 1]["LimitBreaks"], 3)
            self.assertEqual(
                before["User"]["Assets"][0]["Amount"] - after["Assets"][0]["Amount"], cost
            )

    def test_rejected_requests_never_partially_apply(self):
        for who, count in ((4, 1), (11, 1), (1, 0), (1, 4), (1, True)):
            with self.assertRaises(PacketError):
                self.run_break(who, count)
        self.assertEqual(self.store.account.profile(), self.profile)
        for change in (
            lambda p: p["User"]["Assets"][0].update(Amount=25),
            lambda p: p["User"]["Assets"][0].update(Spent=MAX_REVISION - 1),
            lambda p: p["User"].update(
                TrainingSlots={"1": {"CharacterId": 1, "IsLimitBreak": True}}
            ),
        ):
            profile = copy.deepcopy(self.profile)
            change(profile)
            self.save_profile(profile)
            with self.assertRaises(PacketError):
                self.run_break(count=3)
            self.assertEqual(self.store.account.profile(), profile)

    def test_receipt_failure_leaves_original_profile(self):
        self.db.execute(
            "CREATE TRIGGER reject_break BEFORE INSERT ON hero_limit_break_requests BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_break(count=2)
        self.assertEqual(self.store.account.profile(), self.profile)
