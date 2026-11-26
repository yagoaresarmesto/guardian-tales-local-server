# SPDX-License-Identifier: Apache-2.0
"""The first hero collection challenge grants its gems once without losing progress."""

import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet


class FirstHeroChallengeTests(unittest.TestCase):
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
        self.profile["UserMission"]["ChallengeClaimed"] = {"999": 4}
        self.save()
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True

    def tearDown(self):
        self.db.close()

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def claim(self, body):
        request = parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps(body).encode(),
                    body_type=1,
                    sequence_id=1,
                    api="/mission/claim-challenge-all",
                )
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(request))))

    def test_reward_and_retry_preserve_entire_profile(self):
        response = self.claim({"missionIds": [200, 200]})
        expected = json.loads(json.dumps(self.profile))
        next(a for a in expected["User"]["Assets"] if a["Id"] == 70003)["Amount"] += 50
        expected["User"]["Cas"] += 1
        expected["UserMission"]["Cas"] += 1
        expected["UserMission"]["ChallengeClaimed"]["200"] = 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(response["AddedItems"], [{"Id": 0, "ItemId": 70003, "Amount": 50}])
        self.assertEqual(
            GuestStore(self.db).account.claim_challenge_missions({"missionIds": [200]}), response
        )
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT group_id,step FROM challenge_mission_claims").fetchall(),
            [(200, 1)],
        )

    def test_malformed_and_mixed_requests_are_atomic(self):
        for body in (
            None,
            {},
            {"missionIds": []},
            {"missionIds": [True]},
            {"missionIds": [200, 201]},
            {"missionIds": [[200]]},
            {"missionIds": [200], "Step": 2},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.claim(body)
        self.assertEqual(self.account.profile(), self.profile)

    def test_sign_in_saved_knight_and_first_step_scope_are_required(self):
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.claim({"missionIds": [200]})
        self.session.signed_in = True
        original = json.loads(json.dumps(self.profile))
        for characters in ([], [original["User"]["Characters"][0]] * 2):
            self.profile["User"]["Characters"] = characters
            self.save()
            with self.assertRaises(PacketError):
                self.claim({"missionIds": [200]})
            self.assertEqual(self.account.profile(), self.profile)
        self.profile = original
        self.profile["UserMission"]["ChallengeClaimed"]["200"] = 2
        self.save()
        with self.assertRaises(PacketError):
            self.claim({"missionIds": [200]})
        self.assertEqual(self.account.profile(), self.profile)

    def test_inconsistent_receipt_and_failed_write_cannot_grant(self):
        self.profile["UserMission"]["ChallengeClaimed"]["200"] = 1
        self.save()
        with self.assertRaises(PacketError):
            self.claim({"missionIds": [200]})
        self.assertEqual(self.account.profile(), self.profile)
        del self.profile["UserMission"]["ChallengeClaimed"]["200"]
        self.save()
        self.db.execute(
            "CREATE TRIGGER reject_challenge BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.claim({"missionIds": [200]})
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM challenge_mission_claims").fetchone(), (0,)
        )
