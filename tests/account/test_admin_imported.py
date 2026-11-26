# SPDX-License-Identifier: Apache-2.0
"""The console grant supports imported accounts without replaying their prologue."""

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from guardian_tales.accounts.snapshots import import_snapshot
from guardian_tales.administration.admin import MAX_USER_REVISION, gem_history, grant_gems
from guardian_tales.runtime.bootstrap import GuestStore
from tests.account.test_snapshots import synthetic_snapshot


class ImportedGemAdministrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.source = self.root / "synthetic.json"
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["Cas"] = 0x80000008
        self.source.write_text(json.dumps(snapshot))
        self.state = self.root / "state"
        import_snapshot(self.source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def profile(self):
        return json.loads(
            self.db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
        )

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def grant(self, operation="million-imported"):
        return grant_gems(self.state, 1000000, operation, "Local testing")

    def test_cli_grants_one_million_without_changing_imported_seed_or_unrelated_state(self):
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM prologue_selection").fetchone()[0], 0
        )
        source = self.source.read_bytes()
        imported = self.db.execute("SELECT * FROM imported_account").fetchall()
        before = self.profile()
        tables = [
            row[0]
            for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] != "local_account"
        ]
        other_rows = {
            name: self.db.execute('SELECT * FROM "' + name + '"').fetchall() for name in tables
        }
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "guardian_tales",
                "admin",
                "grant-gems",
                "1000000",
                "--data-dir",
                str(self.state),
                "--operation-id",
                "million-imported",
                "--reason",
                "Local testing",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        receipt = json.loads(process.stdout)
        expected = copy.deepcopy(before)
        asset = next(a for a in expected["User"]["Assets"] if a["Id"] == 70003)
        asset["Amount"] += 1000000
        expected["User"]["Cas"] += 1
        self.assertEqual(receipt["result"], "applied")
        self.assertEqual(receipt["current_balance"], asset["Amount"])
        self.assertEqual(self.profile(), expected)
        self.assertEqual(self.db.execute("SELECT * FROM imported_account").fetchall(), imported)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            {name: self.db.execute('SELECT * FROM "' + name + '"').fetchall() for name in tables},
            other_rows,
        )
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.assertEqual(GuestStore(self.db).account.read("/auth/fetch-account"), expected)
        self.assertEqual(len(gem_history(self.state)), 1)

    def test_imported_retry_preserves_later_spending_and_does_not_create_prologue_selection(self):
        self.grant()
        profile = self.profile()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70003)["Amount"] -= 123
        self.save(profile)
        before = list(self.db.iterdump())
        receipt = self.grant()
        self.assertEqual(receipt["result"], "already_applied")
        self.assertEqual(self.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        with self.assertRaises(ValueError):
            grant_gems(self.state, 1, "million-imported", "Local testing")
        self.assertEqual(list(self.db.iterdump()), before)

    def test_revision_ceiling_allows_saved_replay_but_rejects_any_new_increment(self):
        profile = self.profile()
        profile["User"]["Cas"] = MAX_USER_REVISION - 1
        self.save(profile)
        self.grant()
        self.assertEqual(self.profile()["User"]["Cas"], MAX_USER_REVISION)
        before = list(self.db.iterdump())
        self.assertEqual(self.grant()["result"], "already_applied")
        with self.assertRaises(ValueError):
            self.grant("another-million")
        self.assertEqual(list(self.db.iterdump()), before)
