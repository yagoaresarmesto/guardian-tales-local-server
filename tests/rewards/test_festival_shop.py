# SPDX-License-Identifier: Apache-2.0
"""Shop availability computes local exclusions and never spends or rewrites account data."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet
from tests import FIXTURES

FIXTURE = FIXTURES / "festival_shop_catalog.json"
ROUTE = "/festival-pass/check-not-redeemable"


class FestivalShopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "festival_shop_catalog.json"
        self.catalog_file.write_bytes(FIXTURE.read_bytes())
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db, self.references)
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
        self.profile["UserFestivalPass"].update(SeasonId=91, Point=4)
        self.save(self.profile)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def save(self, p):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
        self.db.commit()

    def check(self, body=None):
        return self.account.read(ROUTE, body)

    def test_empty_purchase_history_is_read_only_and_preserves_points_across_repeats(self):
        changes = self.db.total_changes
        for body in (None, {}, None):
            self.assertEqual(self.check(body), {"NotRedeemable": []})
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(self.db.total_changes, changes)

    def test_exhausted_limits_and_owned_persistent_rewards_are_excluded(self):
        p = self.account.profile()
        p["UserFestivalPass"]["Purchase"] = {"12": 2, "13": 100}
        p["User"]["ItemMiscs"].extend(
            [
                {"Id": 20, "ItemId": 12001, "Amount": 1},
                {"Id": 21, "ItemId": 12003, "Amount": 0},
            ]
        )
        self.save(p)
        self.assertEqual(self.check(), {"NotRedeemable": [11, 12]})
        self.assertEqual(self.account.profile(), p)
        p["User"]["ItemMiscs"][-1]["Amount"] = 1
        self.save(p)
        self.assertEqual(self.check(), {"NotRedeemable": [11, 12, 14]})
        self.assertEqual(self.account.profile(), p)

    def test_uninitialized_empty_season_uses_catalog_without_initializing_or_writing(self):
        p = self.account.profile()
        p["UserFestivalPass"].update(SeasonId=0, Point=0)
        self.save(p)
        changes = self.db.total_changes
        self.assertEqual(self.check(), {"NotRedeemable": []})
        self.assertEqual(self.account.profile(), p)
        self.assertEqual(self.db.total_changes, changes)
        p["UserFestivalPass"]["Point"] = 1
        self.save(p)
        with self.assertRaises(ValueError):
            self.check()
        self.assertEqual(self.account.profile(), p)

    def test_malformed_requests_unknown_season_and_history_fail_without_writes(self):
        original = self.account.profile()
        for body in ([], False, 0, "", {"Count": 1}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.check(body)
        for patch in (
            {"SeasonId": True},
            {"SeasonId": 92},
            {"Point": -1},
            {"Purchase": {"999": 1}},
            {"Purchase": {"11": True}},
            {"Purchase": {"11": -1}},
        ):
            p = copy.deepcopy(original)
            p["UserFestivalPass"].update(patch)
            self.save(p)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.check()
            self.assertEqual(self.account.profile(), p)

    def test_missing_and_invalid_catalog_do_not_fall_back_to_unrestricted_availability(self):
        original = json.loads(FIXTURE.read_text())
        invalid = [[], {}, {**original, "season_id": True}, {**original, "items": {}}]
        for patch in (
            {"limit": True},
            {"limit": -1},
            {"owned_misc_ids": [True]},
            {"owned_misc_ids": [12001, 12001]},
            {"price": 0},
            {"price": True},
            {"rewards": [{"item_id": 70003, "amount": 1, "storage": "unknown"}]},
        ):
            bad = copy.deepcopy(original)
            bad["items"]["11"].update(patch)
            invalid.append(bad)
        self.catalog_file.unlink()
        with self.assertRaises(ValueError):
            self.check()
        for bad in invalid:
            self.catalog_file.write_text(json.dumps(bad))
            with self.subTest(catalog=bad), self.assertRaises(ValueError):
                self.check()
        self.assertEqual(self.account.profile(), self.profile)

    def test_packet_requires_signin_and_completed_local_prologue(self):
        packet = parse_packet(encode_packet(Packet(0, body_type=0, api=ROUTE, sequence_id=9)))
        session = BootstrapSession(self.store)
        with self.assertRaises(PacketError):
            session.handle(packet)
        session.signed_in = True
        changes = self.db.total_changes
        response = read_json_body(parse_packet(encode_packet(session.handle(packet))))
        self.assertEqual(response, {"NotRedeemable": []})
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(self.account.profile(), self.profile)
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.references).account
            with self.assertRaises(ValueError):
                account.read(ROUTE)
