# SPDX-License-Identifier: Apache-2.0
"""Administrative grants are persistent, audited, idempotent and exclusive."""

import asyncio
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from guardian_tales.administration.admin import MAX_GEMS, gem_history, grant_gems
from guardian_tales.runtime.bootstrap import GuestStore
from guardian_tales.runtime.server import LocalServer
from guardian_tales.runtime.state_lock import StateLock


class GemAdministrationTests(unittest.TestCase):
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
            profile = account.profile()
            next(a for a in profile["User"]["Assets"] if a["Id"] == 70003)["Amount"] = 400
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self):
        with self.connect() as db:
            return json.loads(
                db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
            )

    def grant(self, amount=1000000, operation_id="million-001", reason="Local testing"):
        return grant_gems(self.directory, amount, operation_id, reason)

    def test_million_grant_changes_only_free_gems_and_user_revision_and_survives_reopening(self):
        expected = self.profile()
        receipt = self.grant()
        next(a for a in expected["User"]["Assets"] if a["Id"] == 70003)["Amount"] += 1000000
        expected["User"]["Cas"] += 1
        self.assertEqual(self.profile(), expected)
        with self.connect() as db:
            self.assertEqual(GuestStore(db).account.read("/auth/fetch-account"), expected)
        self.assertEqual(receipt["result"], "applied")
        self.assertEqual((receipt["balance_before"], receipt["balance_after"]), (400, 1000400))
        self.assertEqual(receipt["current_balance"], 1000400)
        history = gem_history(self.directory)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["operation_id"], "million-001")
        self.assertEqual(history[0]["created_at"], receipt["created_at"])
        self.assertEqual(history[0]["reason"], "Local testing")

    def test_retry_does_not_duplicate_or_restore_gems_spent_since_the_original_grant(self):
        original = self.grant()
        before = self.profile()
        retry = self.grant()
        self.assertEqual(retry["result"], "already_applied")
        self.assertEqual(self.profile(), before)
        next(a for a in before["User"]["Assets"] if a["Id"] == 70003)["Amount"] -= 10
        with self.connect() as db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(before),))
        retry = self.grant()
        self.assertEqual(retry["balance_after"], original["balance_after"])
        self.assertEqual(retry["current_balance"], 1000390)
        self.assertEqual(self.profile(), before)
        for patch in ({"amount": 1}, {"reason": "Different operation"}):
            with self.assertRaises(ValueError):
                self.grant(**patch)
        self.assertEqual(self.profile(), before)
        self.assertEqual(len(gem_history(self.directory)), 1)

    def test_invalid_input_and_overflow_cannot_change_balances_or_create_receipts(self):
        before = self.profile()
        for patch in (
            {"amount": 0},
            {"amount": -1},
            {"amount": True},
            {"amount": 1.5},
            {"amount": MAX_GEMS + 1},
            {"amount": MAX_GEMS},
            {"operation_id": ""},
            {"operation_id": "bad\nidentifier"},
            {"reason": " "},
            {"reason": "bad\nreason"},
        ):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.grant(**patch)
        self.assertEqual(self.profile(), before)
        self.assertEqual(gem_history(self.directory), [])

    def test_missing_account_unfinished_prologue_and_unsupported_schema_are_rejected(self):
        missing = self.directory / "missing"
        with self.assertRaises(ValueError):
            grant_gems(missing, 1, "test", "Local testing")
        self.assertFalse(missing.exists())
        before = self.profile()
        with self.connect() as db:
            db.execute("DELETE FROM prologue_selection")
        with self.assertRaises(ValueError):
            self.grant()
        with self.connect() as db:
            db.execute("UPDATE local_account SET schema_version=999")
        with self.assertRaises(ValueError):
            self.grant()
        self.assertEqual(self.profile(), before)
        self.assertEqual(gem_history(self.directory), [])

    def test_running_backend_blocks_grants_and_duplicate_backend_until_closed(self):
        server = LocalServer(self.directory, 0, 0, 0)
        before = self.profile()
        try:
            with self.assertRaisesRegex(RuntimeError, "in use"):
                self.grant()
            with self.assertRaisesRegex(RuntimeError, "in use"):
                LocalServer(self.directory, 0, 0, 0)
            self.assertEqual(gem_history(self.directory), [])
            self.assertEqual(self.profile(), before)
        finally:
            asyncio.run(server.close())
        self.assertEqual(self.grant()["result"], "applied")

    def test_legacy_completed_account_does_not_require_an_import_marker_table(self):
        with self.connect() as db:
            db.execute("DROP TABLE imported_account")
        self.assertEqual(self.grant()["result"], "applied")

    def test_audit_failure_rolls_back_the_balance_update(self):
        self.grant(1, "seed")
        before = self.profile()
        with self.connect() as db:
            db.execute(
                "CREATE TRIGGER reject_grant BEFORE INSERT ON admin_gem_grants "
                "BEGIN SELECT RAISE(ABORT, 'test'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.grant()
        self.assertEqual(self.profile(), before)
        self.assertEqual([r["operation_id"] for r in gem_history(self.directory)], ["seed"])

    def test_cli_grant_history_and_cross_process_lock(self):
        command = [sys.executable, "-m", "guardian_tales", "admin"]
        grant = command + [
            "grant-gems",
            "1000000",
            "--data-dir",
            str(self.directory),
            "--operation-id",
            "million-cli",
            "--reason",
            "Local testing",
        ]
        with StateLock(self.directory):
            rejected = subprocess.run(grant, capture_output=True, text=True, timeout=10)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("in use", rejected.stderr)
        applied = subprocess.run(grant, capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(json.loads(applied.stdout)["current_balance"], 1000400)
        history = subprocess.run(
            command + ["gem-history", "--data-dir", str(self.directory)],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        self.assertEqual(json.loads(history.stdout)[0]["operation_id"], "million-cli")

    def test_constructor_and_startup_failures_release_the_state_lock(self):
        with self.connect() as db:
            db.execute("UPDATE local_account SET schema_version=999")
        with self.assertRaises(ValueError):
            LocalServer(self.directory, 0, 0, 0)
        with StateLock(self.directory):
            pass
        with self.connect() as db:
            db.execute("UPDATE local_account SET schema_version=3")
        server = LocalServer(self.directory, 0, 0, 0, cert_dir=self.directory / "missing-tls")
        with self.assertRaises(FileNotFoundError):
            asyncio.run(server.start())
        with StateLock(self.directory):
            pass
