# SPDX-License-Identifier: Apache-2.0
"""Single and maximum hero blessings debit exactly the missing catalog levels."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.heroes.characters import new_character
from guardian_tales.heroes.hero_blessing import ALL, ONE
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import MAX_REVISION
from tests.village.test_village_harvest import VillageFixture


class HeroBlessingTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        ticket = 801
        tiers = [[{"OptionId": 5, "Level": n}] for n in (10, 20, 30)]
        data = {
            "items": [{"Id": ticket, "Type": "ticket", "Name": "hero_blessing_ticket"}],
            "heroes": [
                {"Id": 71, "Playable": True, "BlessingLevelOptions": tiers},
                {"Id": 72, "Playable": True, "BlessingLevelOptions": tiers[:2]},
                {"Id": 73, "Playable": True},
            ],
            "exps2": {
                "HeroBlessing": [
                    {"BlessingLevel": str(n), "BlessingCosts": cost}
                    for n, cost in enumerate((4, 7, 12))
                ]
            },
            "unlockfeature": [
                {"Id": 114, "Type": "QuestClear", "Value": {"Default": 9, "KakaoGlobal": 39}}
            ],
        }
        text = ""
        for key, table in data.items():
            value = json.dumps(table)
            text += f"{key}\n{value}\n1\n{digest(value.encode())}\n"
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(compress(text.encode()))
        self.profile = self.store.account.profile()
        user = self.profile["User"]
        user["Characters"] = [new_character(i, spec) for i, spec in ((1, 71), (2, 72), (3, 73))]
        user["ItemStackables"] = [
            {"Id": 4, "ItemId": ticket, "Amount": 4},
            {"Id": 7, "ItemId": ticket, "Amount": 22},
            {"Id": 9, "ItemId": 800, "Amount": 7},
        ]
        user["TrainingSlots"] = {}
        self.profile["UserRecord"].update(Misc={"Other": 15, "BlessCharacterCount": 21})
        self.profile["UserProgress"]["QuestProgresses"] = [{"Id": 39, "Grade": 0}]
        self.save_profile(self.profile)
        self.body = {"CharacterId": 1}

    def test_single_then_max_spends_only_remaining_books_and_survives_reconnect(self):
        expected = copy.deepcopy(self.profile)
        user, record = expected["User"], expected["UserRecord"]
        user["Characters"][0]["BlessLevel"] = 1
        user["ItemStackables"].pop(0)
        user["Cas"] += 1
        record["Misc"]["BlessCharacterCount"] += 1
        record["Cas"] += 1
        roster_update = {k: user[k] for k in ("Id", "Cas", "Characters", "ItemStackables")}
        self.assertEqual(self.call(self.body, ONE), {"User": roster_update, "UserRecord": record})
        self.assertEqual(self.store.account.profile(), expected)
        user["Characters"][0]["BlessLevel"] = 3
        user["ItemStackables"][0]["Amount"] -= 19
        user["Cas"] += 1
        record["Misc"]["BlessCharacterCount"] += 2
        record["Cas"] += 1
        result = self.call(self.body, ALL, sequence=52)
        roster_update = {k: user[k] for k in ("Id", "Cas", "Characters", "ItemStackables")}
        self.assertEqual(result, {"User": roster_update, "UserRecord": record})
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(reconnect=True)
        self.static.unlink()
        self.assertEqual(self.call(self.body, ONE), result)
        self.assertEqual(self.call(self.body, ALL, sequence=52), result)
        self.assertEqual(self.store.account.profile(), expected)

    def test_other_hero_uses_its_own_cap_and_both_buttons_stop_at_max(self):
        body = {"CharacterId": 2}
        self.call(body, ALL)
        before = self.store.account.profile()
        self.assertEqual(before["User"]["Characters"][1]["BlessLevel"], 2)
        self.assertEqual(before["User"]["ItemStackables"][0]["Amount"], 15)
        for route in (ONE, ALL):
            with self.assertRaises(PacketError):
                self.call(body, route, sequence=60)
        self.assertEqual(self.store.account.profile(), before)

    def test_insufficient_books_never_partially_applies_max(self):
        self.profile["User"]["ItemStackables"][1]["Amount"] = 5
        self.save_profile(self.profile)
        with self.assertRaises(PacketError):
            self.call(self.body, ALL)
        self.assertEqual(self.store.account.profile(), self.profile)
        self.assertEqual(self.call(self.body, ONE)["User"]["Characters"][0]["BlessLevel"], 1)

    def test_authentication_ownership_eligibility_training_unlock_and_revision_guards(self):
        for body in (
            {"CharacterId": 3},
            {"CharacterId": 999},
            {"CharacterId": True},
            {"CharacterId": 1, "Level": 3},
        ):
            with self.assertRaises(PacketError):
                self.call(body, ALL)
        for change in (
            lambda p: p["User"].update(TrainingSlots={"1": {"CharacterId": 1, "IsBlessing": True}}),
            lambda p: p["UserRecord"].update(Cas=MAX_REVISION),
            lambda p: p["UserProgress"].update(QuestProgresses=[{"Id": 39, "Grade": -1}]),
        ):
            profile = copy.deepcopy(self.profile)
            change(profile)
            self.save_profile(profile)
            with self.assertRaises(PacketError):
                self.call(self.body, ONE)
            self.assertEqual(self.store.account.profile(), profile)
        self.session = BootstrapSession(self.store)
        with self.assertRaises(PacketError):
            self.call(self.body, ONE)

    def test_mismatched_retry_and_receipt_failure_cannot_charge_again(self):
        self.call(self.body, ONE)
        before = self.store.account.profile()
        for route, body in ((ALL, self.body), (ONE, {"CharacterId": 2})):
            with self.assertRaises(PacketError):
                self.call(body, route)
        self.db.execute(
            "CREATE TRIGGER reject_bless BEFORE INSERT ON hero_blessing_requests BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.body, ALL, sequence=60)
        self.assertEqual(self.store.account.profile(), before)
