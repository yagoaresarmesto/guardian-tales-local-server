# SPDX-License-Identifier: Apache-2.0
"""Catalog tutorial flags must not mutate game progress, rewards or inventory."""

import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.runtime.bootstrap import GuestStore
from tests import FIXTURES

REFERENCE_DIR = FIXTURES / "reference"


class CatalogTutorialTests(unittest.TestCase):
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
        self.profile["UserProgress"]["StageStates"]["100010001"] = 7
        self.save()

    def tearDown(self):
        self.db.close()

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def test_known_flags_persist_once_without_executing_actions_or_granting_rewards(self):
        response = self.account.mark_tutorial({"tutorialIds": [205, 206, 205]})
        expected = json.loads(json.dumps(self.profile))
        expected["UserProgress"]["Tutorials"] = [205, 206]
        expected["UserProgress"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            GuestStore(self.db, REFERENCE_DIR).account.mark_tutorial({"tutorialIds": [205]}),
            response,
        )
        self.assertEqual(self.account.profile(), expected)

    def test_inn_gate_and_unknown_or_malformed_batches_are_atomic(self):
        self.profile["UserProgress"]["StageStates"] = {}
        self.save()
        for ids in ([1003, 205], [205, 9999], [205, True], [205, []]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.account.mark_tutorial({"tutorialIds": ids})
            self.assertEqual(self.account.profile(), self.profile)
        self.account.mark_tutorial({"tutorialIds": [1003]})
        self.assertEqual(self.account.profile()["UserProgress"]["Tutorials"], [1003])

    def test_invalid_catalog_is_rejected_before_saving_flags(self):
        for catalog in (
            [],
            {},
            {"ids": [205, 205]},
            {"ids": [True]},
            {"ids": [-1]},
            {"ids": [2**31]},
        ):
            with patch.object(self.account.references, "json", return_value=catalog):
                with self.assertRaises(ValueError):
                    self.account.mark_tutorial({"tutorialIds": [205]})
            self.assertEqual(self.account.profile(), self.profile)
