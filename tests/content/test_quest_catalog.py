# SPDX-License-Identifier: Apache-2.0
"""Quest registration preserves existing progression and never grants rewards."""

import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.runtime.bootstrap import GuestStore
from tests import FIXTURES

REFERENCE_DIR = FIXTURES / "reference"


class QuestCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.account = GuestStore(self.db, REFERENCE_DIR).account
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
        self.profile["UserProgress"]["QuestProgresses"] = [
            {"Id": 27, "Grade": -1, "InnerProgress": 4, "CustomStates": {}}
        ]
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.execute("INSERT INTO campaign_session VALUES(1,100010001)")
        self.db.commit()
        self.body = {"StageId": 100010001, "QuestId": 57, "StageCustom": None}

    def tearDown(self):
        self.db.close()

    def test_start_and_retry_preserve_progress_balances_and_inventory(self):
        self.assertEqual(self.account.start_quest(self.body), {"OpenedStages": []})
        expected = json.loads(json.dumps(self.profile))
        expected["UserProgress"]["QuestProgresses"].append(
            {"Id": 57, "Grade": -1, "InnerProgress": 0, "CustomStates": {}}
        )
        expected["UserProgress"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        GuestStore(self.db, REFERENCE_DIR).account.start_quest(self.body)
        self.assertEqual(self.account.profile(), expected)

    def test_active_stage_and_catalog_membership_are_required(self):
        for changed in (
            {"QuestId": True},
            {"QuestId": 999},
            {"StageId": 100020001},
            {"StageCustom": {"X": 1}},
        ):
            with self.assertRaises(ValueError):
                self.account.start_quest(self.body | changed)
        self.db.execute("DELETE FROM campaign_session")
        self.db.commit()
        with self.assertRaises(ValueError):
            self.account.start_quest(self.body)
        self.assertEqual(self.account.profile(), self.profile)

    def test_catalog_failure_and_profile_write_failure_leave_no_partial_quest(self):
        for catalog in ({}, {"chapters": {"10001": [True]}}, {"chapters": {"10001": [57, 57]}}):
            with patch.object(self.account.references, "json", return_value=catalog):
                with self.assertRaises(ValueError):
                    self.account.start_quest(self.body)
        self.db.execute(
            "CREATE TRIGGER reject_quest BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.account.start_quest(self.body)
        self.assertEqual(self.account.profile(), self.profile)
