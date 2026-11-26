# SPDX-License-Identifier: Apache-2.0
"""Pass rewards and their claim receipt must survive retries without double grants."""

import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet


class FirstGuardianPassTests(unittest.TestCase):
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
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True

    def tearDown(self):
        self.db.close()

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def claim(self, body=None):
        packet = Packet(
            0,
            json.dumps(body).encode() if body is not None else b"",
            body_type=1 if body is not None else 0,
            sequence_id=5,
            api="/guardian-pass/claim-all",
        )
        response = self.session.handle(parse_packet(encode_packet(packet)))
        return read_json_body(parse_packet(encode_packet(response)))

    def test_reward_initializes_only_free_claim_and_survives_retry_and_reopening(self):
        response = self.claim()
        expected = json.loads(json.dumps(self.profile))
        next(a for a in expected["User"]["Assets"] if a["Id"] == 70032)["Amount"] += 30
        expected["User"]["Cas"] += 1
        expected["UserGuardianPass"]["SeasonId"] = 58
        expected["UserGuardianPass"]["Claimed"]["Free"] = 1
        expected["UserGuardianPass"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(response["AddedItems"], [{"Id": 0, "ItemId": 70032, "Amount": 30}])
        self.assertEqual(response["UserGuardianPass"], expected["UserGuardianPass"])
        self.assertEqual(self.claim({}), response)
        self.assertEqual(GuestStore(self.db).account.claim_guardian_pass(None), response)
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT season_id,level FROM guardian_pass_claims").fetchall(),
            [(58, 1)],
        )

    def test_parameters_sign_in_and_account_creation_are_checked_before_grant(self):
        for body in ([], False, 0, "", {"SeasonId": 58}, {"PassType": 1}):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.claim(body)
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.claim()
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM guardian_pass_claims").fetchone(), (0,)
        )
        with sqlite3.connect(":memory:") as empty_db:
            with self.assertRaises(ValueError):
                GuestStore(empty_db).account.claim_guardian_pass(None)

    def test_other_seasons_paid_passes_and_progress_are_rejected_unchanged(self):
        original = json.loads(json.dumps(self.profile))
        for patch in (
            {"SeasonId": 59},
            {"SeasonId": False},
            {"Experience": 1},
            {"Experience": False},
            {"PassType": 1},
            {"PassType": False},
            {"PurchasedGoldPass": True},
            {"Missions": {"1": 1}},
            {"FreeRewardClaimedList": [1]},
            {"Claimed": {"Free": 0, "Gold": 1, "Platinum": 0, "ExtraExp": 0}},
            {"Claimed": {"Free": False, "Gold": 0, "Platinum": 0, "ExtraExp": 0}},
        ):
            self.profile = json.loads(json.dumps(original))
            self.profile["UserGuardianPass"].update(patch)
            self.save()
            with self.subTest(patch=patch), self.assertRaises(PacketError):
                self.claim()
            self.assertEqual(self.account.profile(), self.profile)

    def test_inconsistent_receipts_and_write_failure_cannot_grant(self):
        self.profile["UserGuardianPass"]["Claimed"]["Free"] = 1
        self.save()
        with self.assertRaises(PacketError):
            self.claim()
        self.assertEqual(self.account.profile(), self.profile)
        self.profile["UserGuardianPass"]["Claimed"]["Free"] = 0
        self.save()
        self.db.execute(
            "CREATE TRIGGER reject_pass BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.claim()
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM guardian_pass_claims").fetchone(), (0,)
        )
        self.db.execute("DROP TRIGGER reject_pass")
        self.db.commit()
        self.claim()
        saved = self.account.profile()
        self.db.execute("UPDATE guardian_pass_claims SET rewards='[]'")
        self.db.commit()
        with self.assertRaises(PacketError):
            self.claim()
        self.assertEqual(self.account.profile(), saved)
