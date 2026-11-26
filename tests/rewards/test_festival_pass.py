# SPDX-License-Identifier: Apache-2.0
"""Festival points are separate from inventory and other pass reward receipts."""

import json
import sqlite3
import unittest

from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.rewards.festival_missions import ROUTE as MISSION_ROUTE
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import PacketError, parse_packet
from guardian_tales.runtime.protocol import Packet, encode_packet
from tests.village.test_village_harvest import VillageFixture


class FirstFestivalPassTests(unittest.TestCase):
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
        self.account.claim_guardian_pass(None)
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
            sequence_id=6,
            api="/festival-pass/claim-all",
        )
        response = self.session.handle(parse_packet(encode_packet(packet)))
        return read_json_body(parse_packet(encode_packet(response)))

    def test_points_persist_once_without_affecting_inventory_or_guardian_pass(self):
        response = self.claim()
        expected = json.loads(json.dumps(self.profile))
        expected["UserFestivalPass"]["SeasonId"] = 41
        expected["UserFestivalPass"]["Point"] = 4
        expected["UserFestivalPass"]["Claimed"]["Free"] = 1
        expected["UserFestivalPass"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            response,
            {"UserFestivalPass": expected["UserFestivalPass"], "AddedItems": [], "AddedPoint": 4},
        )
        self.assertEqual(self.claim({}), response)
        self.assertEqual(GuestStore(self.db).account.claim_festival_pass(None), response)
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT season_id,level,points FROM festival_pass_claims").fetchall(),
            [(41, 1, 4)],
        )
        self.assertEqual(
            self.db.execute("SELECT season_id,level FROM guardian_pass_claims").fetchall(),
            [(58, 1)],
        )

    def test_parameters_sign_in_and_account_creation_are_required(self):
        for body in ([], False, 0, "", {"SeasonId": 41}, {"PassType": 1}):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.claim(body)
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.claim()
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM festival_pass_claims").fetchone(), (0,)
        )
        with sqlite3.connect(":memory:") as empty_db:
            with self.assertRaises(ValueError):
                GuestStore(empty_db).account.claim_festival_pass(None)

    def test_claimed_reward_retry_preserves_spent_or_administratively_granted_points(self):
        self.claim()
        for balance in (3, 1000003):
            self.profile = self.account.profile()
            self.profile["UserFestivalPass"]["Point"] = balance
            self.profile["UserFestivalPass"]["Purchase"] = {"304": 1}
            self.save()
            response = self.claim()
            self.assertEqual(response["UserFestivalPass"]["Point"], balance)
            self.assertEqual(self.account.profile(), self.profile)
            self.assertEqual(
                self.db.execute("SELECT count(*) FROM festival_pass_claims").fetchone(), (1,)
            )

    def test_unsupported_progress_and_paid_passes_are_rejected_unchanged(self):
        original = json.loads(json.dumps(self.profile))
        for patch in (
            {"SeasonId": 42},
            {"SeasonId": False},
            {"Experience": 1},
            {"Experience": False},
            {"PassType": 1},
            {"PassType": False},
            {"Point": 1},
            {"Point": False},
            {"Missions": {"1": 1}},
            {"Purchase": {"1": 1}},
            {"Claimed": {"Free": 0, "Gold": 1, "Platinum": 0, "ExtraExp": 0}},
            {"Claimed": {"Free": False, "Gold": 0, "Platinum": 0, "ExtraExp": 0}},
        ):
            self.profile = json.loads(json.dumps(original))
            self.profile["UserFestivalPass"].update(patch)
            self.save()
            with self.subTest(patch=patch), self.assertRaises(PacketError):
                self.claim()
            self.assertEqual(self.account.profile(), self.profile)

    def test_receipt_mismatch_and_failed_write_cannot_award_points(self):
        self.profile["UserFestivalPass"]["Claimed"]["Free"] = 1
        self.save()
        with self.assertRaises(PacketError):
            self.claim()
        self.assertEqual(self.account.profile(), self.profile)
        self.profile["UserFestivalPass"]["Claimed"]["Free"] = 0
        self.save()
        self.db.execute(
            "CREATE TRIGGER reject_festival BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.claim()
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM festival_pass_claims").fetchone(), (0,)
        )
        self.db.execute("DROP TRIGGER reject_festival")
        self.db.commit()
        self.claim()
        saved = self.account.profile()
        self.db.execute("UPDATE festival_pass_claims SET points=40")
        self.db.commit()
        with self.assertRaises(PacketError):
            self.claim()
        self.assertEqual(self.account.profile(), saved)


class FestivalMissionClaimTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        catalog = {
            "Seasons": [{"Id": 41, "MissionSet": 7}],
            "Missions": [
                {"SetId": 7, "Id": 2, "GroupId": 2, "Value": 100, "PassExperience": 10},
                {"SetId": 7, "Id": 3, "GroupId": 2, "Value": 300, "PassExperience": 100},
                {"SetId": 7, "Id": 4, "GroupId": 2, "Value": 600, "PassExperience": 100},
                {"SetId": 7, "Id": 8, "GroupId": 8, "Value": 1, "PassExperience": 600},
                {"SetId": 6, "Id": 9, "GroupId": 2, "Value": 1, "PassExperience": 50},
            ],
        }
        content = json.dumps(catalog)
        table = f"festivalpass\n{content}\n1\n{digest(content.encode())}\n"
        (self.references / "static_data_get.bin").write_bytes(compress(table.encode()))
        profile = self.store.account.profile()
        profile["UserFestivalPass"].update(
            SeasonId=41,
            Point=49,
            Experience=9900,
            Missions={
                "2": {"Id": 2, "Value": 310, "RewardedIds": [2], "Rewarded": False},
                "8": {"Id": 8, "Value": 1, "RewardedIds": None, "Rewarded": False},
            },
        )
        self.save_profile(profile)

    def test_claim_all_records_only_new_tiers_and_reconnect_cannot_repeat_them(self):
        expected = self.store.account.profile()
        festival = expected["UserFestivalPass"]
        festival["Experience"] += 700
        festival["Cas"] += 1
        festival["Missions"]["2"]["RewardedIds"].append(3)
        festival["Missions"]["8"]["RewardedIds"] = [8]
        body = {"missionIds": [2, 3, 3, 8]}
        self.assertEqual(self.call(body, MISSION_ROUTE), {"UserFestivalPass": festival})
        self.assertEqual(self.store.account.profile(), expected)
        self.open_session(reconnect=True)
        changes = self.db.total_changes
        self.assertEqual(self.call(body, MISSION_ROUTE), {"UserFestivalPass": festival})
        self.assertEqual(self.db.total_changes, changes)

    def test_invalid_batches_cannot_partially_grant_xp(self):
        original = self.store.account.profile()
        for ids in ([3, 4], [3, 9], [3, True], 3):
            with self.subTest(ids=ids), self.assertRaises(PacketError):
                self.call({"missionIds": ids}, MISSION_ROUTE)
            self.assertEqual(self.store.account.profile(), original)

    def test_legacy_group_rewarded_flag_is_honored(self):
        original = self.store.account.profile()
        original["UserFestivalPass"]["Missions"]["8"]["Rewarded"] = True
        self.save_profile(original)
        changes = self.db.total_changes
        self.call({"missionIds": [8]}, MISSION_ROUTE)
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(self.store.account.profile(), original)
