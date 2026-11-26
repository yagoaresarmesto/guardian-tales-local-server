# SPDX-License-Identifier: Apache-2.0
"""Season-bound point grants preserve the account and share the exclusive backend lock."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from guardian_tales.administration.admin_festival import (
    MAX_POINTS,
    festival_point_history,
    grant_festival_points,
)
from guardian_tales.runtime.bootstrap import GuestStore
from guardian_tales.runtime.state_lock import StateLock


class FestivalPointAdministrationTests(unittest.TestCase):
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database)
        try:
            with db:
                yield db
        finally:
            db.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.database = self.directory / "server.sqlite3"
        with self.connect() as db:
            account = GuestStore(db).account
            account.complete_prologue(
                "lab",
                {
                    "IsMale": True,
                    "VoiceType": 1,
                    "Weapon1ItemId": 9010010,
                    "Weapon2ItemId": 9080010,
                    "BobLindaQuestGrade": 0,
                },
            )
            account.claim_festival_pass(None)
            profile = account.profile()
            profile["UserFestivalPass"].update(Point=3, Purchase={"304": 1})
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self):
        with self.connect() as db:
            return json.loads(
                db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
            )

    def grant(
        self,
        amount=1000000,
        season_id=41,
        operation_id="festival-million-001",
        reason="Local testing",
    ):
        return grant_festival_points(self.directory, amount, season_id, operation_id, reason)

    def test_million_points_changes_only_pass_balance_revision_and_survives_claim_retry(self):
        expected = self.profile()
        receipt = self.grant()
        expected["UserFestivalPass"]["Point"] += 1000000
        expected["UserFestivalPass"]["Cas"] += 1
        self.assertEqual(self.profile(), expected)
        self.assertEqual((receipt["balance_before"], receipt["balance_after"]), (3, 1000003))
        self.assertEqual(receipt["season_id"], 41)
        with self.connect() as db:
            account = GuestStore(db).account
            self.assertEqual(
                account.read("/festival-pass/enter")["UserFestivalPass"],
                expected["UserFestivalPass"],
            )
            account.claim_festival_pass(None)
        self.assertEqual(self.profile(), expected)
        self.assertEqual(festival_point_history(self.directory)[0]["amount"], 1000000)

    def test_retries_preserve_spending_and_conflicting_arguments_are_rejected(self):
        original = self.grant()
        p = self.profile()
        p["UserFestivalPass"]["Point"] -= 2
        with self.connect() as db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
        retry = self.grant()
        self.assertEqual(retry["result"], "already_applied")
        self.assertEqual(retry["current_balance"], 1000001)
        self.assertEqual(retry["balance_after"], original["balance_after"])
        for patch in ({"amount": 1}, {"reason": "Different grant"}, {"season_id": 42}):
            with self.assertRaises(ValueError):
                self.grant(**patch)
        self.assertEqual(self.profile(), p)
        self.assertEqual(len(festival_point_history(self.directory)), 1)

    def test_invalid_parameters_and_overflow_do_not_create_receipts(self):
        p = self.profile()
        for patch in (
            {"amount": 0},
            {"amount": True},
            {"amount": 1.5},
            {"amount": MAX_POINTS},
            {"season_id": 0},
            {"season_id": True},
            {"operation_id": "bad\nID"},
            {"reason": " "},
            {"reason": "bad\nreason"},
        ):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.grant(**patch)
        self.assertEqual(self.profile(), p)
        self.assertEqual(festival_point_history(self.directory), [])

    def test_inactive_or_wrong_season_and_invalid_saved_balance_are_rejected(self):
        original = self.profile()
        for key, value in (
            ("SeasonId", 0),
            ("SeasonId", 42),
            ("Point", -1),
            ("Point", True),
            ("Cas", MAX_POINTS),
        ):
            p = json.loads(json.dumps(original))
            p["UserFestivalPass"][key] = value
            with self.connect() as db:
                db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.grant()
            self.assertEqual(self.profile(), p)
        self.assertEqual(festival_point_history(self.directory), [])

    def test_missing_account_unfinished_prologue_and_wrong_schema_are_not_migrated(self):
        missing = self.directory / "missing"
        with self.assertRaises(ValueError):
            grant_festival_points(missing, 1, 41, "missing", "Local testing")
        self.assertFalse(missing.exists())
        p = self.profile()
        with self.connect() as db:
            db.execute("DELETE FROM prologue_selection")
        with self.assertRaises(ValueError):
            self.grant()
        with self.connect() as db:
            db.execute("UPDATE local_account SET schema_version=999")
        with self.assertRaises(ValueError):
            self.grant()
        self.assertEqual(self.profile(), p)
        self.assertEqual(festival_point_history(self.directory), [])

    def test_receipt_or_profile_write_failure_rolls_back_the_full_grant(self):
        self.grant(1, operation_id="seed")
        p = self.profile()
        for table, action in (
            ("local_account", "UPDATE"),
            ("admin_festival_point_grants", "INSERT"),
        ):
            with self.connect() as db:
                db.execute(
                    f"CREATE TRIGGER reject_points BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT,'test'); END"
                )
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.grant()
            self.assertEqual(self.profile(), p)
            self.assertEqual(len(festival_point_history(self.directory)), 1)
            with self.connect() as db:
                db.execute("DROP TRIGGER reject_points")

    def test_backend_lock_blocks_grants_but_history_remains_read_only(self):
        p = self.profile()
        with StateLock(self.directory):
            with self.assertRaisesRegex(RuntimeError, "in use"):
                self.grant()
            self.assertEqual(festival_point_history(self.directory), [])
        self.assertEqual(self.profile(), p)
        self.assertEqual(self.grant()["result"], "applied")

    def test_cli_grant_history_and_cross_process_lock(self):
        command = [sys.executable, "-m", "guardian_tales", "admin"]
        grant = command + [
            "grant-festival-points",
            "1000000",
            "--season-id",
            "41",
            "--data-dir",
            str(self.directory),
            "--operation-id",
            "festival-cli",
            "--reason",
            "Local testing",
        ]
        with StateLock(self.directory):
            denied = subprocess.run(grant, capture_output=True, text=True, timeout=10)
        self.assertEqual(denied.returncode, 2)
        self.assertIn("in use", denied.stderr)
        applied = subprocess.run(grant, capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(json.loads(applied.stdout)["current_balance"], 1000003)
        history = subprocess.run(
            command + ["festival-point-history", "--data-dir", str(self.directory)],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        self.assertEqual(json.loads(history.stdout)[0]["operation_id"], "festival-cli")
