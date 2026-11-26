# SPDX-License-Identifier: Apache-2.0
"""Imported accounts can purchase stored stamina without changing captured state."""

import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.settlement.village import MAX_REVISION, current_village
from tests.village.test_village_harvest import NOW, VillageFixture

ROUTE = "/user/charge-stamina-by-gem"
TODAY = datetime.fromtimestamp(NOW, timezone.utc)
TOMORROW = (
    TODAY.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
).isoformat()


class PurchaseClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(NOW, tz)


class ImportedStaminaPurchaseTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.purchase_path = self.references / "stamina_purchase_catalog.json"
        self.purchase_path.write_text(
            json.dumps(
                {
                    "amount_per_charge": 50,
                    "gem_prices": [100, 100, 200, 200, 300, 300, 400, 400, 500],
                    "max_storage": 3000,
                    "daily_limit": 20,
                }
            )
        )
        profile = self.store.account.profile()
        self.asset(profile, 70003).update(Amount=1000, Spent=25)
        self.asset(profile, 70032).update(Amount=2881, Spent=197411)
        profile["User"]["StaminaGemChargeTicket"].update(
            PlayCount=2,
            RefillCount=0,
            NextCharge=None,
            NextDailyReset=TODAY.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            PlayLimitUpgradeExpireTime=None,
        )
        self.save_profile(profile)

    def call(self, body=None, route=ROUTE, sequence=101, now=NOW):
        with patch("guardian_tales.rewards.stamina_purchase.datetime", PurchaseClock):
            return super().call(body, route, sequence, now)

    def test_imported_native_purchase_changes_only_free_gems_reserve_counter_and_revision(self):
        profile = self.store.account.profile()
        expected = copy.deepcopy(profile)
        self.asset(expected, 70003).update(Amount=900, Spent=125)
        self.asset(expected, 70032)["Amount"] += 50
        expected["User"]["Cas"] += 1
        expected["User"]["StaminaGemChargeTicket"].update(
            PlayCount=1, RefillCount=0, NextDailyReset=TOMORROW
        )
        village = current_village(self.db)
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        source = self.source.read_bytes()
        self.assertEqual(self.call({"Count": 1}), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM prologue_selection").fetchone()[0], 0
        )

    def test_imported_saved_price_tiers_batch_and_expired_daily_counter(self):
        profile = self.store.account.profile()
        profile["User"]["StaminaGemChargeTicket"].update(PlayCount=1, NextDailyReset=TOMORROW)
        self.save_profile(profile)
        self.call({"Count": 2})
        saved = self.store.account.profile()
        self.assertEqual(self.asset(saved, 70003)["Amount"], 700)
        self.assertEqual(self.asset(saved, 70032)["Amount"], 2981)
        self.assertEqual(saved["User"]["StaminaGemChargeTicket"]["PlayCount"], 3)
        # Reset the saved counter to a previous UTC day; the next batch starts at tier zero.
        self.save_profile(profile)
        profile["User"]["StaminaGemChargeTicket"]["NextDailyReset"] = (
            TODAY - timedelta(days=1)
        ).isoformat()
        self.save_profile(profile)
        self.call({"Count": 2}, sequence=102)
        self.assertEqual(self.asset(self.store.account.profile(), 70003)["Amount"], 800)

    def test_delayed_retry_preserves_later_purchase_and_consumption_without_catalog(self):
        self.call({"Count": 1})
        self.call({"Count": 1}, sequence=102)
        profile = self.store.account.profile()
        self.asset(profile, 70032)["Amount"] -= 10
        self.asset(profile, 70032)["Spent"] += 10
        self.save_profile(profile)
        self.purchase_path.unlink()
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"Count": 1}), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes({"Count": 2})

    def test_reopening_reconnect_and_new_login_preserve_receipt_and_allow_a_new_purchase(self):
        first = self.call({"Count": 1})
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"Count": 1}), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.call({"Count": 1})
        self.assertEqual(self.asset(self.store.account.profile(), 70003)["Amount"], 800)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM stamina_gem_purchase_requests").fetchone()[0], 2
        )

    def test_storage_free_gem_daily_limit_schema_and_authentication_guards_remain_atomic(self):
        original = self.store.account.profile()
        self.reject_without_writes({"Count": 3})
        for kind in ("gems", "quota"):
            profile = copy.deepcopy(original)
            if kind == "gems":
                self.asset(profile, 70003)["Amount"] = 99
                self.asset(profile, 70002)["Amount"] = 9999
            else:
                profile["User"]["StaminaGemChargeTicket"].update(
                    PlayCount=20, NextDailyReset=TOMORROW
                )
            self.save_profile(profile)
            self.reject_without_writes({"Count": 1})
        self.save_profile(original)
        for body in (None, {}, [], {"Count": True}, {"Count": 0}, {"Count": 1, "Extra": 0}):
            self.reject_without_writes(body)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes({"Count": 1})

    def test_signed_64_bit_revision_supported_and_ceiling_blocks_only_new_purchases(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = 2**40
        self.save_profile(profile)
        self.call({"Count": 1})
        profile = self.store.account.profile()
        self.assertEqual(profile["User"]["Cas"], 2**40 + 1)
        profile["User"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"Count": 1}), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        with self.assertRaises(ValueError):
            self.store.account.purchase_stamina({"Count": 1}, "ceiling-new-purchase", TODAY)
        self.assertEqual(list(self.db.iterdump()), before)
