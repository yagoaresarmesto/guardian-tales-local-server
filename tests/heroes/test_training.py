# SPDX-License-Identifier: Apache-2.0
"""The first knight tutorial must spend experience once and preserve the account."""

import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet


def request(body):
    return parse_packet(
        encode_packet(
            Packet(
                0,
                json.dumps(body).encode(),
                body_type=1,
                sequence_id=1,
                api="/user/add-character-experience",
            )
        )
    )


class FirstKnightTrainingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db)
        self.store.account.complete_prologue(
            "lab",
            {
                "IsMale": True,
                "VoiceType": 1,
                "Weapon1ItemId": 9010010,
                "Weapon2ItemId": 9080010,
                "BobLindaQuestGrade": 0,
            },
        )
        self.profile = self.store.account.profile()
        self.profile["UserProgress"]["StageStates"]["100010001"] = 7
        next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 790
        self.save_profile()
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True

    def tearDown(self):
        self.db.close()

    def save_profile(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def test_upgrade_spends_once_and_survives_restart(self):
        body = {"Experiences": {"1": 37}}
        response = read_json_body(parse_packet(encode_packet(self.session.handle(request(body)))))
        expected = json.loads(json.dumps(self.profile))
        next(a for a in expected["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 753
        expected["User"]["Characters"][0]["Experience"] = 37
        expected["User"]["Cas"] += 1
        expected["UserRecord"]["AddCharacterExperienceAmount"] += 37
        expected["UserRecord"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(response, {"User": expected["User"], "UserRecord": expected["UserRecord"]})
        restarted = GuestStore(self.db).account
        self.assertEqual(restarted.add_character_experience(body), response)
        self.assertEqual(restarted.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT * FROM first_knight_training").fetchall(), [(1, 37)]
        )

    def test_invalid_or_unaffordable_training_is_atomic(self):
        for body in (
            None,
            {},
            {"Experiences": {}},
            {"Experiences": {"1": True}},
            {"Experiences": {"1": 38}},
            {"Experiences": {"2": 37}},
            {"Experiences": {"1": 37, "2": 37}},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.session.handle(request(body))
        self.assertEqual(self.store.account.profile(), self.profile)
        next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 36
        self.save_profile()
        with self.assertRaises(PacketError):
            self.session.handle(request({"Experiences": {"1": 37}}))
        self.assertEqual(self.store.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM first_knight_training").fetchone(), (0,)
        )

    def test_clear_and_original_character_are_required(self):
        self.profile["UserProgress"]["StageStates"] = {}
        self.save_profile()
        with self.assertRaises(PacketError):
            self.session.handle(request({"Experiences": {"1": 37}}))
        self.profile["UserProgress"]["StageStates"]["100010001"] = 7
        self.profile["User"]["Characters"][0]["Experience"] = 1
        self.save_profile()
        with self.assertRaises(PacketError):
            self.session.handle(request({"Experiences": {"1": 37}}))
        self.assertEqual(self.store.account.profile(), self.profile)

    def test_database_failure_rolls_back_receipt_and_balance(self):
        self.db.execute(
            "CREATE TRIGGER reject_training BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.account.add_character_experience({"Experiences": {"1": 37}})
        self.assertEqual(self.store.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM first_knight_training").fetchone(), (0,)
        )

    def test_help_tutorials_do_not_unlock_content_and_batches_are_atomic(self):
        account = self.store.account
        self.profile["UserProgress"]["StageStates"] = {}
        self.save_profile()
        with self.assertRaises(ValueError):
            account.mark_tutorial({"tutorialIds": [1003, 200]})
        self.assertEqual(account.profile(), self.profile)
        for ids in ([1003, 1012], [1003, True], [9999]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                account.mark_tutorial({"tutorialIds": ids})
        self.assertEqual(account.profile(), self.profile)
        response = account.mark_tutorial({"tutorialIds": [1003, 1007, 1003]})
        self.assertEqual(response["UserProgress"]["Tutorials"], [1003, 1007])
        expected = json.loads(json.dumps(self.profile))
        expected["UserProgress"]["Tutorials"] = [1003, 1007]
        expected["UserProgress"]["Cas"] += 1
        self.assertEqual(account.profile(), expected)
        saved = account.profile()
        restarted = GuestStore(self.db).account
        self.assertEqual(restarted.mark_tutorial({"tutorialIds": [1007]}), response)
        self.assertEqual(restarted.profile(), saved)
