# SPDX-License-Identifier: Apache-2.0
"""Synthetic prices verify atomic stamina purchases, UTC resets and stable retries."""

import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import PacketError, parse_packet
from guardian_tales.runtime.protocol import Packet, encode_packet
from tests import FIXTURES

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
FIXTURE = FIXTURES / "stamina_purchase_catalog.json"


class StaminaPurchaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "stamina_purchase_catalog.json"
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
        self.asset(p, 70003)["Amount"] = 200
        self.asset(p, 70032)["Amount"] = 20
        self.save(p)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def asset(self, p, item_id):
        return next(a for a in p["User"]["Assets"] if a["Id"] == item_id)

    def save(self, p):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
        self.db.commit()

    def buy(self, count=1, operation="purchase-1", now=NOW):
        return self.account.purchase_stamina({"Count": count}, operation, now)

    def assert_unchanged(self, p, receipts=0):
        self.assertEqual(self.account.profile(), p)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM stamina_gem_purchase_requests").fetchone(),
            (receipts,),
        )

    def packet(self, route, body, seq=7):
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

    def test_purchase_changes_only_free_gems_storage_counter_and_user_revision(self):
        expected = self.account.profile()
        self.asset(expected, 70003)["Amount"] -= 5
        self.asset(expected, 70003)["Spent"] += 5
        self.asset(expected, 70032)["Amount"] += 7
        expected["User"]["Cas"] += 1
        expected["User"]["StaminaGemChargeTicket"].update(
            PlayCount=1, RefillCount=0, NextDailyReset="2026-11-18T00:00:00+00:00"
        )
        response = self.buy()
        self.assertEqual(response, {"User": expected["User"]})
        self.assertEqual(self.account.profile(), expected)
        receipt = json.loads(
            self.db.execute("SELECT purchase FROM stamina_gem_purchase_requests").fetchone()[0]
        )
        self.assertEqual(
            (receipt["GemCost"], receipt["StaminaAmount"], receipt["PlayCountAfter"]), (5, 7, 1)
        )

    def test_batch_cost_sums_price_tiers_and_repeats_final_price(self):
        self.buy()
        self.buy(1, "purchase-2")
        self.buy(2, "purchase-3")
        p = self.account.profile()
        self.assertEqual((self.asset(p, 70003)["Amount"], self.asset(p, 70003)["Spent"]), (168, 32))
        self.assertEqual(self.asset(p, 70032)["Amount"], 48)
        self.assertEqual(p["User"]["StaminaGemChargeTicket"]["PlayCount"], 4)
        with self.assertRaises(ValueError):
            self.buy(1, "over-limit")
        self.assert_unchanged(p, 3)

    def test_receipt_survives_reopening_and_returns_current_state_after_spending(self):
        self.buy()
        saved = self.account.profile()
        self.asset(saved, 70032)["Amount"] -= 4
        self.asset(saved, 70032)["Spent"] += 4
        self.asset(saved, 70003)["Amount"] -= 3
        self.save(saved)
        self.db.close()
        self.db = sqlite3.connect(self.db_file)
        self.account = GuestStore(self.db, self.references).account
        self.catalog_file.unlink()
        self.assertEqual(self.buy(now=NOW + timedelta(days=2)), {"User": saved["User"]})
        self.assert_unchanged(saved, 1)
        with self.assertRaises(ValueError):
            self.buy(2)
        self.assert_unchanged(saved, 1)

    def test_utc_day_reset_restarts_price_and_quota_without_regranting_old_receipt(self):
        before_midnight = NOW.replace(hour=23, minute=59)
        self.buy(4, "day-1", before_midnight)
        # This offset-aware time is the next UTC midnight.
        after_midnight = datetime(2026, 11, 18, 1, 0, tzinfo=timezone(timedelta(hours=1)))
        self.buy(1, "day-2", after_midnight)
        p = self.account.profile()
        self.assertEqual(self.asset(p, 70003)["Spent"], 37)
        self.assertEqual(p["User"]["StaminaGemChargeTicket"]["PlayCount"], 1)
        self.assertEqual(
            p["User"]["StaminaGemChargeTicket"]["NextDailyReset"], "2026-11-19T00:00:00+00:00"
        )
        self.buy(4, "day-1", after_midnight)
        self.assert_unchanged(p, 2)

    def test_insufficient_free_gems_do_not_spend_paid_gems_or_partially_charge(self):
        p = self.account.profile()
        self.asset(p, 70003)["Amount"] = 4
        self.asset(p, 70002)["Amount"] = 999
        self.save(p)
        with self.assertRaises(ValueError):
            self.buy()
        self.assert_unchanged(p)

    def test_storage_and_spending_limits_reject_whole_purchase(self):
        original = self.account.profile()
        for kind in ("storage", "spent"):
            p = copy.deepcopy(original)
            if kind == "storage":
                self.asset(p, 70032)["Amount"] = 94
            else:
                self.asset(p, 70003)["Spent"] = 0x7FFFFFFF
            self.save(p)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.buy()
            self.assert_unchanged(p)
        self.asset(p, 70003)["Spent"] = 0
        self.asset(p, 70032)["Amount"] = 93
        self.save(p)
        self.buy()
        self.assertEqual(self.asset(self.account.profile(), 70032)["Amount"], 100)

    def test_malformed_request_clock_and_identity_do_not_change_account(self):
        p = self.account.profile()
        for request in (
            None,
            {},
            {"Count": True},
            {"Count": 0},
            {"Count": -1},
            {"Count": 1.5},
            {"Count": 1001},
            {"Count": 1, "Extra": 0},
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.account.purchase_stamina(request, "bad", NOW)
            self.assert_unchanged(p)
        for identity in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.buy(operation=identity)
        with self.assertRaises(ValueError):
            self.buy(now=NOW.replace(tzinfo=None))
        self.assert_unchanged(p)

    def test_missing_or_invalid_catalog_cannot_grant(self):
        p = self.account.profile()
        catalog = json.loads(FIXTURE.read_text())
        invalid = [
            [],
            {},
            {**catalog, "daily_limit": True},
            {**catalog, "amount_per_charge": 0},
            {**catalog, "max_storage": 1},
            {**catalog, "gem_prices": []},
            {**catalog, "gem_prices": [True]},
            {**catalog, "gem_prices": [-1]},
        ]
        self.catalog_file.unlink()
        with self.assertRaises(ValueError):
            self.buy()
        for value in invalid:
            self.catalog_file.write_text(json.dumps(value))
            with self.subTest(catalog=value), self.assertRaises(ValueError):
                self.buy()
            self.assert_unchanged(p)

    def test_invalid_saved_counter_or_asset_cannot_grant(self):
        original = self.account.profile()
        for key, value in (
            ("Type", True),
            ("Type", 1),
            ("PlayCount", -1),
            ("NextDailyReset", "bad"),
            ("NextDailyReset", "2026-11-18"),
            ("NextCharge", "2026-11-18T00:00:00+00:00"),
            ("PlayLimitUpgradeExpireTime", "2026-11-18T00:00:00+00:00"),
        ):
            p = copy.deepcopy(original)
            p["User"]["StaminaGemChargeTicket"][key] = value
            self.save(p)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.buy()
            self.assert_unchanged(p)
        p = copy.deepcopy(original)
        self.asset(p, 70003)["Amount"] = True
        self.save(p)
        with self.assertRaises(ValueError):
            self.buy()
        self.assert_unchanged(p)

    def test_receipt_or_profile_write_failure_rolls_back_every_change(self):
        original = self.account.profile()
        for table, action in (
            ("local_account", "UPDATE"),
            ("stamina_gem_purchase_requests", "INSERT"),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_purchase BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.buy()
            self.assert_unchanged(original)
            self.db.execute("DROP TRIGGER reject_purchase")
            self.db.commit()

    def test_packet_requires_auth_and_reconnect_reuses_receipt_while_new_login_can_buy_again(self):
        route = "/user/charge-stamina-by-gem"
        request = self.packet(route, {"Count": 1})
        session = BootstrapSession(self.store)
        with self.assertRaises(PacketError):
            session.handle(request)
        signin = {"AuthKind": 0, "AccessToken": "synthetic-local", "Reconnect": False}
        session.handle(self.packet("/auth/sign-in", signin, 1))
        response = read_json_body(parse_packet(encode_packet(session.handle(request))))
        p = self.account.profile()
        self.assertEqual(set(response), {"User"})
        reconnect = BootstrapSession(self.store)
        reconnect.handle(self.packet("/auth/sign-in", {**signin, "Reconnect": True}, 8))
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(reconnect.handle(request)))), response
        )
        self.assert_unchanged(p, 1)
        reconnect.handle(self.packet("/auth/sign-in", signin, 1))
        reconnect.handle(request)
        self.assertEqual(self.asset(self.account.profile(), 70003)["Spent"], 14)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM stamina_gem_purchase_requests").fetchone(), (2,)
        )

    def test_account_without_completed_prologue_cannot_purchase(self):
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.references).account
            before = account.profile()
            with self.assertRaises(ValueError):
                account.purchase_stamina({"Count": 1}, "too-early", NOW)
            self.assertEqual(account.profile(), before)
