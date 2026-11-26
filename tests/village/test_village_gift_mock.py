# SPDX-License-Identifier: Apache-2.0
"""An empty princess gift advances only its timer and survives replay/interleaving."""

import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from guardian_tales.accounts.snapshots import CLIENT, preserved_read
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.settlement.village import MAX_REVISION, current_village
from guardian_tales.settlement.village import ROUTE as HARVEST
from guardian_tales.settlement.village_gift import ROUTE
from tests.village.test_village_harvest import NOW, VillageFixture

TODAY = datetime.fromtimestamp(NOW, timezone.utc)


class VillageGiftMockTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.gift_path = self.references / "village_gift_mock_catalog.json"
        self.gift_catalog = {"client": CLIENT, "cooldown_seconds": 60}
        self.write_gift_catalog()
        self.initial["NextGiftTime"] = (TODAY - timedelta(seconds=1)).isoformat()
        self.save_village(self.initial)

    def write_gift_catalog(self):
        self.gift_path.write_text(json.dumps(self.gift_catalog))

    def call(self, body=None, route=ROUTE, sequence=111, now=NOW):
        return super().call(body, route, sequence, now)

    def test_only_village_gift_timer_and_revision_change_without_any_reward_fields(self):
        profile = self.store.account.profile()
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        expected = copy.deepcopy(self.initial)
        expected["NextGiftTime"] = (TODAY + timedelta(seconds=60)).isoformat(
            timespec="microseconds"
        )
        expected["Cas"] += 1
        self.assertEqual(self.call(), {"UserLobbyVillage": expected})
        self.assertEqual(current_village(self.db), expected)
        self.assertEqual(
            preserved_read(self.db, "/lobby-village/enter")["UserLobbyVillage"], expected
        )
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )

    def test_null_and_future_timers_are_not_initialized_or_postponed(self):
        profile = self.store.account.profile()
        for index, stamp in enumerate((None, (TODAY + timedelta(seconds=1)).isoformat())):
            village = copy.deepcopy(self.initial)
            village["NextGiftTime"] = stamp
            self.save_village(village)
            self.assertEqual(self.call(sequence=111 + index), {"UserLobbyVillage": village})
            self.assertEqual(current_village(self.db), village)
            self.assertEqual(self.store.account.profile(), profile)

    def test_due_equality_and_seventh_fraction_digit_do_not_open_a_gift_early(self):
        village = copy.deepcopy(self.initial)
        village["NextGiftTime"] = TODAY.strftime("%Y-%m-%dT%H:%M:%S") + ".0000001Z"
        self.save_village(village)
        self.call()
        self.assertEqual(current_village(self.db), village)
        self.call(sequence=112, now=NOW + 1)
        self.assertEqual(current_village(self.db)["Cas"], village["Cas"] + 1)
        village["NextGiftTime"] = TODAY.isoformat()
        self.save_village(village)
        self.call(sequence=113)
        self.assertEqual(current_village(self.db)["Cas"], village["Cas"] + 1)

    def test_old_retry_preserves_new_gift_timer_and_other_village_collections_without_catalog(self):
        self.call()
        self.call(route=HARVEST, sequence=112)
        self.call(sequence=113, now=NOW + 60)
        profile = self.store.account.profile()
        village = current_village(self.db)
        self.gift_path.unlink()
        before = list(self.db.iterdump())
        self.assertEqual(self.call({}, now=NOW + 120), {"UserLobbyVillage": village})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.store.account.profile(), profile)

    def test_reopening_reconnect_and_new_login_keep_the_timer_and_receipt(self):
        first = self.call()
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.assertEqual(self.call(), first)
        self.call(sequence=112, now=NOW + 60)
        self.assertEqual(current_village(self.db)["Cas"], self.initial["Cas"] + 2)

    def test_invalid_owner_missing_and_malformed_timers_reject_without_writes(self):
        for field, value in (
            ("UserId", 1),
            ("NextGiftTime", "bad"),
            ("NextGiftTime", True),
            ("NextGiftTime", "2026-11-18T00:00:00"),
            ("NextGiftTime", "2026-13-18T00:00:00Z"),
        ):
            village = copy.deepcopy(self.initial)
            village[field] = value
            self.save_village(village)
            self.reject_without_writes()
        village = copy.deepcopy(self.initial)
        village.pop("NextGiftTime")
        self.save_village(village)
        self.reject_without_writes()

    def test_revision_ceiling_and_clock_overflow_preserve_gift_and_profile(self):
        village = copy.deepcopy(self.initial)
        village["Cas"] = MAX_REVISION
        self.save_village(village)
        self.reject_without_writes()
        self.save_village(self.initial)
        before = list(self.db.iterdump())
        for clock in (datetime(2026, 11, 18), datetime.max.replace(tzinfo=timezone.utc)):
            with self.assertRaises(ValueError):
                self.store.account.receive_village_gift(None, "clock-check", clock)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_explicit_catalog_parameterless_schema_identity_and_authentication(self):
        original = copy.deepcopy(self.gift_catalog)
        for key, value in (("client", {}), ("cooldown_seconds", 0), ("cooldown_seconds", True)):
            self.gift_catalog = dict(original, **{key: value})
            self.write_gift_catalog()
            self.reject_without_writes()
        self.gift_path.write_text(" " * 4097)
        self.reject_without_writes()
        self.gift_path.unlink()
        self.reject_without_writes()
        self.gift_catalog = original
        self.write_gift_catalog()
        for body in ([], False, {"GiftId": 1}, {"Amount": 1}):
            self.reject_without_writes(body)
        for op in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.receive_village_gift(None, op, TODAY)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes()

    def test_receipt_failure_rolls_back_timer_revision_and_overlay(self):
        self.db.execute(
            "CREATE TRIGGER reject_gift BEFORE INSERT ON village_gift_mock_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call()
        self.assertEqual(list(self.db.iterdump()), before)
