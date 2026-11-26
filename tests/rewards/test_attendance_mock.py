# SPDX-License-Identifier: Apache-2.0
"""A skipped daily reward changes attendance state once without touching inventory."""

import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.rewards.attendance import ROUTE
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.settlement.village import INT_MAX, MAX_REVISION, current_village
from tests.village.test_village_harvest import NOW, VillageFixture

DAY = 86400
TODAY = datetime.fromtimestamp(NOW, timezone.utc)


class AttendanceMockTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.mock_catalog = {"client": CLIENT, "origin_group": 1, "active_group": 3, "days": 28}
        self.mock_path = self.references / "attendance_mock_catalog.json"
        self.write_mock_catalog()
        profile = self.store.account.profile()
        profile["User"].update(
            MonthlyLoginCount=318, LastAttendanceDate=(TODAY - timedelta(days=1)).isoformat()
        )
        self.save_profile(profile)

    def write_mock_catalog(self):
        self.mock_path.write_text(json.dumps(self.mock_catalog))

    def call(self, body=None, route=ROUTE, sequence=91, now=NOW):
        return super().call(body, route, sequence, now)

    def test_mock_advances_only_date_calendar_login_count_and_both_revisions(self):
        profile = self.store.account.profile()
        expected = copy.deepcopy(profile)
        expected["User"].update(
            MonthlyLoginCount=319, LastAttendanceDate=TODAY.isoformat(timespec="microseconds")
        )
        expected["User"]["Cas"] += 1
        expected["UserRecord"]["LoginDayCount"] += 1
        expected["UserRecord"]["Cas"] += 1
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        source = self.source.read_bytes()
        village = current_village(self.db)
        self.assertEqual(
            self.call(),
            {"User": expected["User"], "UserRecord": expected["UserRecord"], "AddedItems": []},
        )
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(
            self.db.execute("SELECT day,attendance_count FROM attendance_claims").fetchone(),
            (TODAY.date().isoformat(), 319),
        )

    def test_mock_never_reads_missing_or_malformed_reward_catalogs(self):
        rewards = self.references / "attendance_catalog.json"
        self.assertFalse(rewards.exists())
        self.call()
        rewards.write_text("invalid JSON with unsupported random inventory rewards")
        before = self.store.account.profile()
        self.call(sequence=92, now=NOW + DAY)
        after = self.store.account.profile()
        for key in ("Assets", "ItemWeapons", "ItemStackables", "ItemMiscs", "ItemIdCounter"):
            self.assertEqual(before["User"][key], after["User"][key])

    def test_reconnect_retry_after_a_later_day_returns_current_state_without_advancing_again(self):
        self.call()
        self.call(sequence=92, now=NOW + DAY)
        self.mock_path.unlink()
        profile = self.store.account.profile()
        before = list(self.db.iterdump())
        self.assertEqual(self.call({}, now=NOW + 2 * DAY)["User"], profile["User"])
        self.assertEqual(list(self.db.iterdump()), before)

    def test_new_request_same_day_records_no_second_claim_or_profile_change(self):
        self.call()
        profile = self.store.account.profile()
        self.mock_path.unlink()
        self.call(sequence=92, now=NOW + 100)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(self.db.execute("SELECT count(*) FROM attendance_claims").fetchone()[0], 1)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM attendance_mock_requests").fetchone()[0], 2
        )

    def test_official_same_day_capture_is_not_reclaimed_and_its_retry_stays_noop_tomorrow(self):
        profile = self.store.account.profile()
        profile["User"]["LastAttendanceDate"] = TODAY.isoformat()
        self.save_profile(profile)
        self.mock_path.unlink()
        self.call()
        self.call(now=NOW + DAY)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(self.db.execute("SELECT count(*) FROM attendance_claims").fetchone()[0], 0)

    def test_existing_daily_receipt_prevents_reclaim_even_if_saved_date_is_older(self):
        self.db.execute(
            "INSERT INTO attendance_claims VALUES(?,?)", (TODAY.date().isoformat(), 319)
        )
        self.db.commit()
        profile = self.store.account.profile()
        self.call()
        self.assertEqual(self.store.account.profile(), profile)

    def test_reopen_reconnect_and_new_login_keep_the_saved_daily_fence(self):
        first = self.call()
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.call()
        self.assertEqual(self.store.account.profile()["User"], first["User"])
        self.call(sequence=92, now=NOW + DAY)
        self.assertEqual(self.store.account.profile()["User"]["MonthlyLoginCount"], 320)

    def test_calendar_group_legacy_count_first_day_and_28_day_rollover(self):
        original = self.store.account.profile()
        for index, (count, expected) in enumerate(
            ((0, 301), (18, 119), (218, 219), (328, 301), (28, 301), (300, 301))
        ):
            profile = copy.deepcopy(original)
            profile["User"]["MonthlyLoginCount"] = count
            self.save_profile(profile)
            self.call(sequence=91 + index, now=NOW + index * DAY)
            self.assertEqual(self.store.account.profile()["User"]["MonthlyLoginCount"], expected)

    def test_date_comparison_uses_utc_for_offset_and_dotnet_fractional_timestamps(self):
        profile = self.store.account.profile()
        offset = TODAY.astimezone(timezone(timedelta(hours=14)))
        profile["User"]["LastAttendanceDate"] = (
            offset.strftime("%Y-%m-%dT%H:%M:%S") + ".1234567+14:00"
        )
        self.save_profile(profile)
        self.call()
        self.assertEqual(self.store.account.profile(), profile)
        self.call(sequence=92, now=NOW + DAY)
        self.assertEqual(self.store.account.profile()["User"]["MonthlyLoginCount"], 319)

    def test_missing_naive_malformed_and_future_saved_dates_reject_without_writes(self):
        original = self.store.account.profile()
        for value in (
            None,
            True,
            "bad",
            "2026-11-18T00:00:00",
            "2026-13-01T00:00:00Z",
            (TODAY + timedelta(days=1)).isoformat(),
        ):
            profile = copy.deepcopy(original)
            profile["User"]["LastAttendanceDate"] = value
            self.save_profile(profile)
            self.reject_without_writes()

    def test_invalid_counters_owners_and_revision_limits_reject_without_writes(self):
        original = self.store.account.profile()
        for section, field, value in (
            ("User", "MonthlyLoginCount", True),
            ("User", "MonthlyLoginCount", 329),
            ("User", "MonthlyLoginCount", -1),
            ("User", "Cas", MAX_REVISION),
            ("UserRecord", "Cas", MAX_REVISION),
            ("UserRecord", "LoginDayCount", INT_MAX),
            ("UserRecord", "UserId", 1),
        ):
            profile = copy.deepcopy(original)
            profile[section][field] = value
            self.save_profile(profile)
            self.reject_without_writes()

    def test_authentication_parameterless_body_and_operation_identity(self):
        for body in ([], False, {"Reward": True}, {"Day": 19}):
            self.reject_without_writes(body)
        for op in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.claim_attendance(TODAY, operation_id=op)
        with self.assertRaises(ValueError):
            self.store.account.claim_attendance(datetime(2026, 11, 18), operation_id="naive-clock")
        self.session = BootstrapSession(self.store)
        self.reject_without_writes()

    def test_explicit_matching_mock_configuration_is_required_before_skipping_a_reward(self):
        original = copy.deepcopy(self.mock_catalog)
        for key, value in (
            ("client", {}),
            ("origin_group", True),
            ("active_group", 0),
            ("days", True),
            ("days", 29),
        ):
            self.mock_catalog = dict(original, **{key: value})
            self.write_mock_catalog()
            self.reject_without_writes()
        self.mock_path.write_text(" " * 4097)
        self.reject_without_writes()
        self.mock_path.unlink()
        self.reject_without_writes()

    def test_mock_receipt_failure_rolls_back_profile_and_daily_claim(self):
        self.db.execute(
            "CREATE TRIGGER reject_mock BEFORE INSERT ON attendance_mock_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call()
        self.assertEqual(list(self.db.iterdump()), before)
