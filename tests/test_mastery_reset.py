# SPDX-License-Identifier: Apache-2.0
"""Mastery reset refunds the current investment once and preserves later work."""

import copy
import json
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from guardian_tales.basecamp import ROUTE as HARVEST
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.mastery import ROUTE as UPGRADE
from guardian_tales.mastery_reset import MASTERY_POINTS, ROUTE
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import INT_MAX, MAX_REVISION, MAX_TIME, current_village
from tests.test_guardian_mastery import GuardianMasteryFixture
from tests.test_village_harvest import NOW


class MasteryResetTests(GuardianMasteryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.reset_catalog = {
            "client": CLIENT,
            "resource_id": 70003,
            "cost": 30,
            "cooldown_seconds": 60,
        }
        self.reset_path = self.references / "guardian_mastery_reset_catalog.json"
        self.write_reset_catalog()
        self.set_levels({"101": 2, "201": 1})
        profile = self.store.account.profile()
        self.asset(profile, MASTERY_POINTS)["Spent"] = 300
        self.asset(profile, 70003).update(Amount=1000, Spent=7)
        self.asset(profile, 70004).update(Amount=10000, Spent=9)
        self.save_profile(profile)

    def write_reset_catalog(self):
        self.reset_path.write_text(json.dumps(self.reset_catalog))

    def call(self, body=None, route=ROUTE, sequence=81, now=NOW):
        with patch("guardian_tales.mastery_reset.time.time", return_value=now):
            return super().call(body, route, sequence, now)

    def mastery(self, profile):
        return profile["User"]["Options"]["GuardianMastery"]

    def test_reset_refunds_current_map_and_changes_only_payment_skills_timer_total_revision(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.asset(expected, MASTERY_POINTS).update(Amount=10244, Spent=56)
        self.asset(expected, 70003).update(Amount=970, Spent=37)
        self.mastery(expected).update(
            GuardianMasterySkill={},
            SkillNextResetTime=datetime.fromtimestamp(NOW + 60, timezone.utc).isoformat(),
        )
        expected["User"]["GuardianMasteryLevel"] = 0
        expected["User"]["Cas"] += 1
        village = current_village(self.db)
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        source = self.source.read_bytes()
        self.assertEqual(self.call(), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(
            self.db.execute("SELECT refund,gem_cost FROM mastery_reset_requests").fetchone(),
            (244, 30),
        )

    def test_new_skill_can_be_bought_during_reset_cooldown_and_old_reset_replay_keeps_it(self):
        self.call()
        self.call({"SkillId": 301}, UPGRADE, 82)
        profile = self.store.account.profile()
        self.assertEqual(self.levels(profile), {"301": 1})
        self.assertEqual(self.asset(profile, MASTERY_POINTS)["Amount"], 10164)
        self.reset_path.unlink()
        self.mastery_path.unlink()
        before = list(self.db.iterdump())
        self.assertEqual(self.call({}), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_old_upgrade_retry_after_reset_does_not_restore_removed_skill(self):
        self.call({"SkillId": 101}, UPGRADE, 80)
        self.call()
        before = list(self.db.iterdump())
        response = self.call({"SkillId": 101}, UPGRADE, 80)
        self.assertEqual(self.levels({"User": response["User"]}), {})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_reopening_reconnect_and_fresh_login_retain_receipt_timer_and_single_payment(self):
        response = self.call()
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(), response)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.call({"SkillId": 101}, UPGRADE, 82)
        self.reject_without_writes()
        self.call(now=NOW + 60)
        profile = self.store.account.profile()
        self.assertEqual(self.asset(profile, MASTERY_POINTS)["Amount"], 10244)
        self.assertEqual(self.asset(profile, MASTERY_POINTS)["Spent"], 56)
        self.assertEqual(self.asset(profile, 70003)["Amount"], 940)

    def test_timestamp_boundary_uses_native_whole_seconds_and_null_is_due(self):
        original = self.store.account.profile()
        stamp = datetime.fromtimestamp(NOW + 1, timezone.utc).isoformat()
        profile = copy.deepcopy(original)
        self.mastery(profile)["SkillNextResetTime"] = stamp
        self.save_profile(profile)
        self.reject_without_writes()
        self.call(now=NOW + 1)
        for index, value in enumerate(
            (
                None,
                "0001-01-01T00:00:00+00:00",
                datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                + ".9999999+00:00",
            )
        ):
            profile = copy.deepcopy(original)
            self.mastery(profile)["SkillNextResetTime"] = value
            self.save_profile(profile)
            self.call(sequence=83 + index)

    def test_authentication_and_parameterless_schema(self):
        for body in ([], False, 0, {"SkillId": 101}, {"Cost": 0}, {"Refund": 999}):
            self.reject_without_writes(body)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes()

    def test_empty_and_fully_maximized_skills_cannot_be_reset(self):
        self.set_levels({})
        self.reject_without_writes()
        self.set_levels({k: 12 for k in self.mastery_catalog["skills"]})
        self.reject_without_writes()

    def test_invalid_missing_and_naive_reset_timestamps_reject(self):
        original = self.store.account.profile()
        for value in (
            True,
            "bad",
            "2026-11-18T00:00:00",
            "2026-13-01T00:00:00Z",
            "2026-11-18T00:00:00+99:00",
        ):
            profile = copy.deepcopy(original)
            self.mastery(profile)["SkillNextResetTime"] = value
            self.save_profile(profile)
            self.reject_without_writes()
        self.mastery(original).pop("SkillNextResetTime")
        self.save_profile(original)
        self.reject_without_writes()

    def test_free_gem_policy_does_not_silently_spend_paid_gems_or_overflow_spending(self):
        original = self.store.account.profile()
        for field, value in (("Amount", 29), ("Spent", INT_MAX - 29), ("Amount", True)):
            profile = copy.deepcopy(original)
            self.asset(profile, 70003)[field] = value
            self.save_profile(profile)
            self.reject_without_writes()

    def test_refund_and_revision_limits_reject_atomically(self):
        original = self.store.account.profile()
        for field, value in (
            ("Amount", INT_MAX - 243),
            ("Spent", -INT_MAX - 1 + 243),
            ("Spent", "bad"),
        ):
            profile = copy.deepcopy(original)
            self.asset(profile, MASTERY_POINTS)[field] = value
            self.save_profile(profile)
            self.reject_without_writes()
        original["User"]["Cas"] = MAX_REVISION
        self.save_profile(original)
        self.reject_without_writes()
        for now in (0, True, MAX_TIME - 59):
            with self.assertRaises(ValueError):
                self.store.account.reset_guardian_mastery(None, "clock-boundary", now)

    def test_missing_and_duplicate_currency_rows_reject(self):
        original = self.store.account.profile()
        for item in (MASTERY_POINTS, 70003):
            for duplicate in (True, False):
                profile = copy.deepcopy(original)
                row = self.asset(profile, item)
                if duplicate:
                    profile["User"]["Assets"].append(dict(row))
                else:
                    profile["User"]["Assets"].remove(row)
                self.save_profile(profile)
                self.reject_without_writes()

    def test_reset_catalog_is_explicit_bounded_matching_and_supports_only_free_gems(self):
        original = copy.deepcopy(self.reset_catalog)
        for key, value in (
            ("client", {}),
            ("resource_id", 70004),
            ("cost", 0),
            ("cost", True),
            ("cooldown_seconds", 0),
            ("cooldown_seconds", True),
        ):
            self.reset_catalog = dict(original, **{key: value})
            self.write_reset_catalog()
            self.reject_without_writes()
        self.reset_path.write_text(" " * 4097)
        self.reject_without_writes()
        self.reset_path.unlink()
        self.reject_without_writes()

    def test_receipt_failure_rolls_back_refund_payment_skills_and_cooldown(self):
        self.db.execute(
            "CREATE TRIGGER reject_reset BEFORE INSERT ON mastery_reset_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_upgraded_camp_collection_remains_available_with_zero_skills_after_reset(self):
        self.call()
        (self.references / "basecamp_harvest_catalog.json").write_text(
            json.dumps(
                {
                    "client": CLIENT,
                    "portal_specs": [9001],
                    "min_seconds": 60,
                    "debug_mastery_points": 100,
                }
            )
        )
        response = self.call(route=HARVEST, sequence=82, now=NOW + 60)
        self.assertEqual(response["AddedItems"], [])
        profile = self.store.account.profile()
        self.assertEqual(profile["User"]["GuardianMasteryLevel"], 0)
        self.assertEqual(self.asset(profile, MASTERY_POINTS)["Amount"], 10244)
