# SPDX-License-Identifier: Apache-2.0
"""Supported beginner missions grant complete rewards once, including shared stacks."""

import base64
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet


class InnMissionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db)
        self.account = self.store.account
        self.account.complete_prologue(
            "lab",
            {
                "IsMale": True,
                "VoiceType": 1,
                "Weapon1ItemId": 9010010,
                "Weapon2ItemId": 9080010,
                "BobLindaQuestGrade": 0,
            },
        )
        self.profile = self.account.profile()
        self.profile["UserProgress"]["StageStates"]["100010001"] = 7
        self.save()
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True

    def tearDown(self):
        self.db.close()

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def claim(self, ids):
        request = parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps({"missionIds": ids}).encode(),
                    body_type=1,
                    sequence_id=1,
                    api="/mission/claim-beginner-all",
                )
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(request))))

    def test_complete_reward_and_retry_preserve_other_progress(self):
        response = self.claim([0, 0])
        expected = json.loads(json.dumps(self.profile))
        user = expected["User"]
        for item_id, amount in ((70003, 300), (70032, 50)):
            next(a for a in user["Assets"] if a["Id"] == item_id)["Amount"] += amount
        user["ItemIdCounter"] += 1
        user["Cas"] += 1
        actual = self.account.profile()
        ticket = actual["User"]["ItemStackables"][0]
        self.assertEqual((ticket["Id"], ticket["ItemId"], ticket["Amount"]), (3, 110015, 3))
        user["ItemStackables"] = [ticket]
        expected["UserMission"]["GuideClaimed"] = "AQ=="
        expected["UserMission"]["Cas"] += 1
        self.assertEqual(actual, expected)
        self.assertEqual(
            [(i["ItemId"], i["Amount"]) for i in response["AddedItems"]],
            [(70003, 300), (70032, 50), (110015, 3)],
        )
        restarted = GuestStore(self.db).account
        self.assertEqual(restarted.claim_beginner_missions({"missionIds": [0]}), response)
        self.assertEqual(restarted.profile(), expected)

    def test_invalid_mixed_batch_and_uncleared_stage_cannot_grant(self):
        for ids in ([], [True], [1], [0, 1], [0, False], None):
            with self.subTest(ids=ids), self.assertRaises(PacketError):
                self.claim(ids)
        self.assertEqual(self.account.profile(), self.profile)
        self.profile["UserProgress"]["StageStates"] = {}
        self.save()
        with self.assertRaises(PacketError):
            self.claim([0])
        self.assertEqual(self.account.profile(), self.profile)

    def test_existing_ticket_stack_and_unrelated_claim_flags_are_preserved(self):
        self.profile["User"]["ItemStackables"] = [{"Id": 42, "ItemId": 110015, "Amount": 2}]
        self.profile["UserMission"]["GuideClaimed"] = base64.b64encode(b"\x80\x04").decode()
        self.save()
        self.claim([0])
        saved = self.account.profile()
        self.assertEqual(
            saved["User"]["ItemStackables"], [{"Id": 42, "ItemId": 110015, "Amount": 5}]
        )
        self.assertEqual(base64.b64decode(saved["UserMission"]["GuideClaimed"]), b"\x81\x04")
        self.assertEqual(saved["User"]["ItemIdCounter"], self.profile["User"]["ItemIdCounter"])

    def test_failed_profile_write_rolls_back_whole_reward_and_receipt(self):
        self.db.execute(
            "CREATE TRIGGER reject_mission BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.claim([0])
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM beginner_mission_claims").fetchone(), (0,)
        )

    def test_level_two_mission_requires_training_and_preserves_inn_receipt(self):
        with self.assertRaises(PacketError):
            self.claim([1])
        next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 37
        self.save()
        self.account.add_character_experience({"Experiences": {"1": 37}})
        self.claim([0])
        response = self.claim([1])
        saved = self.account.profile()
        self.assertEqual(base64.b64decode(saved["UserMission"]["GuideClaimed"]), b"\x03")
        self.assertEqual(next(a for a in saved["User"]["Assets"] if a["Id"] == 70032)["Amount"], 70)
        self.assertEqual(
            {i["ItemId"]: i["Amount"] for i in saved["User"]["ItemStackables"]},
            {110015: 3, 60014: 200},
        )
        self.assertEqual(
            GuestStore(self.db).account.claim_beginner_missions({"missionIds": [1]}), response
        )
        self.assertEqual(self.account.profile(), saved)

    def test_stamina_reward_uses_spent_counters_and_survives_restart(self):
        self.profile["UserProgress"]["StageStates"] = {}
        self.profile["User"]["ItemStackables"] = [{"Id": 42, "ItemId": 110015, "Amount": 3}]
        self.profile["User"]["ItemIdCounter"] = 42
        self.profile["UserMission"]["GuideClaimed"] = base64.b64encode(b"\x80\x04").decode()
        for asset in self.profile["User"]["Assets"]:
            if asset["Id"] in (70006, 70032):
                asset["Amount"] = 5 if asset["Id"] == 70006 else 10
        self.save()
        with self.assertRaises(PacketError):
            self.claim([9])
        self.assertEqual(self.account.profile(), self.profile)
        self.account.start_stage({"StageId": 100010001})
        before = self.account.profile()
        response = self.claim([9, 9])
        saved = self.account.profile()
        self.assertEqual(base64.b64decode(saved["UserMission"]["GuideClaimed"]), b"\x80\x06")
        self.assertEqual(
            [(i["ItemId"], i["Amount"]) for i in response["AddedItems"]],
            [(110007, 20), (110015, 1)],
        )
        self.assertEqual(
            {i["ItemId"]: (i["Id"], i["Amount"]) for i in saved["User"]["ItemStackables"]},
            {110015: (42, 4), 110007: (43, 20)},
        )
        self.assertEqual(saved["User"]["Assets"], before["User"]["Assets"])
        self.assertEqual(saved["UserProgress"], before["UserProgress"])
        self.assertEqual(
            GuestStore(self.db).account.claim_beginner_missions({"missionIds": [9]}), response
        )
        self.assertEqual(self.account.profile(), saved)

    def test_stamina_threshold_and_unsupported_batches_do_not_change_profile(self):
        charged = next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70006)
        charged["Spent"] = 9
        self.save()
        with self.assertRaises(PacketError):
            self.claim([9])
        self.assertEqual(self.account.profile(), self.profile)
        charged["Spent"] = 10
        self.save()
        for ids in ([9, 0], [9, True], [10], [[9]]):
            with self.subTest(ids=ids), self.assertRaises(PacketError):
                self.claim(ids)
        self.assertEqual(self.account.profile(), self.profile)
        self.claim([9])
        self.assertEqual(
            self.db.execute("SELECT mission_id FROM beginner_mission_claims").fetchall(), [(9,)]
        )

    def test_stamina_reward_write_failure_rolls_back_both_stacks_and_claim(self):
        next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70032)["Spent"] = 10
        self.save()
        self.db.execute(
            "CREATE TRIGGER reject_stamina BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.claim([9])
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM beginner_mission_claims").fetchone(), (0,)
        )
