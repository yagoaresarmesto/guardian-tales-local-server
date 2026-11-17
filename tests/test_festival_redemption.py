# SPDX-License-Identifier: Apache-2.0
"""Festival point spending, deliveries and receipts commit atomically."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.items import inventory_item
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet

FIXTURE = Path(__file__).parent / "fixtures/festival_shop_catalog.json"
ROUTE = "/festival-pass/redeem-point-rewards"


class FestivalRedemptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "festival_shop_catalog.json"
        self.catalog_file.write_bytes(FIXTURE.read_bytes())
        self.db_file = self.references / "test-account.sqlite3"
        self.db = sqlite3.connect(self.db_file)
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
        p = self.account.profile()
        p["UserFestivalPass"].update(SeasonId=91, Point=4)
        self.save(p)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def save(self, p):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
        self.db.commit()

    def redeem(self, item=12, amount=1, operation="redeem-1"):
        return self.account.redeem_festival_points(
            {"shopItemId": item, "amount": amount}, operation
        )

    def assert_unchanged(self, p, receipts=0):
        self.assertEqual(self.account.profile(), p)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM festival_shop_requests").fetchone(), (receipts,)
        )

    def packet(self, route, body, seq=17):
        return parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps(body).encode(),
                    body_type=1,
                    api=route,
                    sequence_id=seq,
                )
            )
        )

    def test_one_point_delivers_three_tickets_and_preserves_other_profile_state(self):
        expected = self.account.profile()
        user = expected["User"]
        user["ItemIdCounter"] += 1
        ticket = inventory_item(user["ItemIdCounter"], 110009)
        ticket["Amount"] = 3
        user["ItemStackables"].append(ticket)
        user["Cas"] += 1
        expected["UserFestivalPass"].update(Point=3, Purchase={"12": 1})
        expected["UserFestivalPass"]["Cas"] += 1
        response = self.redeem()
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            response,
            {
                "User": user,
                "UserFestivalPass": expected["UserFestivalPass"],
                "AddedItems": [{"Id": ticket["Id"], "ItemId": 110009, "Amount": 3}],
            },
        )
        audit = json.loads(
            self.db.execute("SELECT purchase FROM festival_shop_requests").fetchone()[0]
        )
        self.assertEqual(audit, {"SeasonId": 91, "ShopItemId": 12, "Amount": 1, "SpentPoint": 1})

    def test_batch_quantity_merges_stack_and_asset_delivery_preserves_spent(self):
        p = self.account.profile()
        p["User"]["ItemStackables"] = [{"Id": 8, "ItemId": 110009, "Amount": 2}]
        p["User"]["ItemIdCounter"] = 8
        self.save(p)
        self.redeem(amount=2)
        saved = self.account.profile()
        self.assertEqual(
            saved["User"]["ItemStackables"], [{"Id": 8, "ItemId": 110009, "Amount": 8}]
        )
        self.assertEqual(saved["UserFestivalPass"]["Point"], 2)
        self.assertEqual(
            self.account.read("/festival-pass/check-not-redeemable"), {"NotRedeemable": [12]}
        )
        self.redeem(13, 2, "asset-purchase")
        after = self.account.profile()
        self.assertEqual(after["UserFestivalPass"]["Point"], 0)
        self.assertEqual(next(a["Amount"] for a in after["User"]["Assets"] if a["Id"] == 70004), 14)
        self.assertEqual(
            [a["Spent"] for a in after["User"]["Assets"]], [a["Spent"] for a in p["User"]["Assets"]]
        )

    def test_persisted_retry_returns_current_state_after_spending_and_catalog_removal(self):
        first = self.redeem()
        p = self.account.profile()
        p["User"]["ItemStackables"][0]["Amount"] = 1
        p["UserFestivalPass"]["Point"] = 2
        self.save(p)
        self.db.close()
        self.db = sqlite3.connect(self.db_file)
        self.account = GuestStore(self.db, self.references).account
        self.catalog_file.unlink()
        response = self.redeem()
        self.assertEqual(response["AddedItems"], first["AddedItems"])
        self.assertEqual(response["User"], p["User"])
        self.assertEqual(response["UserFestivalPass"], p["UserFestivalPass"])
        self.assert_unchanged(p, 1)
        with self.assertRaises(ValueError):
            self.redeem(amount=2)
        self.assert_unchanged(p, 1)

    def test_insufficient_points_unknown_items_and_malformed_requests_cannot_grant(self):
        p = self.account.profile()
        for body in (
            None,
            {},
            {"shopItemId": True, "amount": 1},
            {"shopItemId": 12, "amount": False},
            {"shopItemId": 12, "amount": 0},
            {"shopItemId": 13, "amount": 5},
            {"shopItemId": 999, "amount": 1},
            {"shopItemId": 12, "amount": 1, "Extra": 0},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.account.redeem_festival_points(body, "invalid")
            self.assert_unchanged(p)
        with self.assertRaises(ValueError):
            self.redeem(operation=None)
        self.assert_unchanged(p)

    def test_ownership_purchase_limits_and_unsupported_rewards_do_not_charge(self):
        original = self.account.profile()
        for kind in ("owned", "limit", "unsupported"):
            p = copy.deepcopy(original)
            item, amount = 11, 1
            if kind == "owned":
                p["User"]["ItemMiscs"].append({"Id": 4, "ItemId": 12001, "Amount": 1})
            elif kind == "limit":
                item, amount = 12, 2
                p["UserFestivalPass"]["Purchase"] = {"12": 1}
            else:
                item = 14
            self.save(p)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.redeem(item, amount)
            self.assert_unchanged(p)

    def test_reward_and_inventory_counter_overflow_cannot_spend_points(self):
        original = self.account.profile()
        for kind in ("stack", "counter", "asset"):
            p = copy.deepcopy(original)
            item = 12
            if kind == "stack":
                p["User"]["ItemStackables"] = [{"Id": 4, "ItemId": 110009, "Amount": 0x7FFFFFFF}]
            elif kind == "counter":
                p["User"]["ItemIdCounter"] = 0x7FFFFFFF
            else:
                item = 13
                next(a for a in p["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 0x7FFFFFFF
            self.save(p)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.redeem(item)
            self.assert_unchanged(p)

    def test_profile_or_receipt_failure_rolls_back_points_inventory_and_purchase_count(self):
        p = self.account.profile()
        for table, action in (("local_account", "UPDATE"), ("festival_shop_requests", "INSERT")):
            self.db.execute(
                f"CREATE TRIGGER reject_festival BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.redeem()
            self.assert_unchanged(p)
            self.db.execute("DROP TRIGGER reject_festival")
            self.db.commit()

    def test_packet_auth_reconnect_and_fresh_login_only_charge_intended_purchases(self):
        session = BootstrapSession(self.store)
        request = self.packet(ROUTE, {"shopItemId": 12, "amount": 1})
        with self.assertRaises(PacketError):
            session.handle(request)
        signin = {"AuthKind": 0, "AccessToken": "synthetic-local", "Reconnect": False}
        session.handle(self.packet("/auth/sign-in", signin, 1))
        first = read_json_body(parse_packet(encode_packet(session.handle(request))))
        saved = self.account.profile()
        reconnect = BootstrapSession(self.store)
        reconnect.handle(self.packet("/auth/sign-in", {**signin, "Reconnect": True}, 18))
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(reconnect.handle(request)))), first
        )
        self.assert_unchanged(saved, 1)
        reconnect.handle(self.packet("/auth/sign-in", signin, 1))
        reconnect.handle(request)
        p = self.account.profile()
        self.assertEqual(p["UserFestivalPass"]["Point"], 2)
        self.assertEqual(p["UserFestivalPass"]["Purchase"], {"12": 2})
        self.assertEqual(p["User"]["ItemStackables"][0]["Amount"], 6)
        self.assert_unchanged(p, 2)
