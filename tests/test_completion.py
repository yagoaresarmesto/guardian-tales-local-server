# SPDX-License-Identifier: Apache-2.0
"""Catalog clear exits keep rewards, quest state and later active sessions intact."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import GuestStore

FIXTURES = Path(__file__).parent / "fixtures"


class CompletionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "completion_catalog.json"
        self.catalog_file.write_bytes((FIXTURES / "completion_catalog.json").read_bytes())
        story = json.loads((FIXTURES / "story_catalog.json").read_bytes())
        story["stages"]["100010003"] = {
            "stamina": 15,
            "requires_cleared": [100010002],
            "quest_ids": [27],
        }
        (self.references / "story_catalog.json").write_text(json.dumps(story))
        self.db = sqlite3.connect(":memory:")
        self.account = GuestStore(self.db, self.references).account
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
        profile = self.account.profile()
        profile["UserProgress"]["StageStates"] = {"100010001": 7, "100010002": 3}
        profile["UserProgress"]["LastPlayedStageId"] = 100010002
        self.save(profile)
        self.db.execute("INSERT INTO campaign_session VALUES(1,100010002)")
        self.db.executemany(
            "INSERT INTO campaign_progress VALUES(100010002,10,?,'true')", [(2,), (9,)]
        )
        self.db.commit()
        self.body = {
            "StageId": 100010002,
            "ExitName": "synthetic_next_exit",
            "IsClearExit": True,
            "StageCustom": {"HitCount": 13, "NoDamage": False, "QuestId": None, "Score": None},
        }

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def save(self, profile):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()

    def test_clear_preserves_all_rewards_and_quests_and_opens_earned_next_entry(self):
        expected = self.account.profile()
        stage_progress = self.account.stage_progress(100010002)
        response = self.account.end_stage(self.body)
        expected["UserProgress"]["StageStates"]["100010002"] = 7
        expected["UserProgress"]["StageStates"]["100010003"] = 1
        expected["UserProgress"]["Cas"] += 2
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(response["User"], expected["User"])
        self.assertEqual(response["StageState"], 7)
        self.assertEqual(response["StageProgress"], stage_progress)
        self.assertEqual(response["AddedItems"], [])
        self.assertEqual(self.db.execute("SELECT * FROM campaign_session").fetchall(), [])
        self.assertEqual(
            self.db.execute("SELECT * FROM campaign_completions").fetchall(),
            [(100010002, "synthetic_next_exit", 13, 0)],
        )
        self.assertEqual(self.db.execute("SELECT * FROM campaign_grade_claims").fetchall(), [])

    def test_retry_after_reopening_preserves_a_later_active_stage(self):
        response = self.account.end_stage(self.body)
        saved = self.account.profile()
        self.db.execute("INSERT INTO campaign_session VALUES(1,100010003)")
        self.db.commit()
        reopened = GuestStore(self.db, self.references).account
        self.assertEqual(reopened.end_stage(self.body), response)
        self.assertEqual(reopened.profile(), saved)
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010003,)]
        )

    def test_invalid_exit_custom_state_and_unfinished_encounters_do_not_mutate(self):
        before = self.account.profile()
        for body in (
            self.body | {"StageId": True},
            self.body | {"StageId": 100010003},
            self.body | {"ExitName": "unknown"},
            self.body | {"IsClearExit": False},
            self.body | {"StageCustom": {"HitCount": True}},
            self.body | {"StageCustom": {"QuestId": 27}},
            self.body | {"StageCustom": {"NoDamage": 1}},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.account.end_stage(body)
        self.db.execute("DELETE FROM campaign_progress WHERE key=9")
        self.db.commit()
        with self.assertRaises(ValueError):
            self.account.end_stage(self.body)
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(self.db.execute("SELECT * FROM campaign_completions").fetchall(), [])
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010002,)]
        )

    def test_invalid_catalog_and_wrong_active_or_locked_stage_preserve_the_save(self):
        before = self.account.profile()
        for patch in ({"required_monsters": [True]}, {"required_monsters": [2, 2]}, {"extra": 1}):
            catalog = json.loads((FIXTURES / "completion_catalog.json").read_bytes())
            catalog["stages"]["100010002"].update(patch)
            self.catalog_file.write_text(json.dumps(catalog))
            with self.assertRaises(ValueError):
                self.account.end_stage(self.body)
        self.catalog_file.write_bytes((FIXTURES / "completion_catalog.json").read_bytes())
        self.db.execute("UPDATE campaign_session SET stage_id=100010001")
        self.db.commit()
        with self.assertRaises(ValueError):
            self.account.end_stage(self.body)
        self.db.execute("UPDATE campaign_session SET stage_id=100010002")
        self.db.commit()
        before["UserProgress"]["StageStates"]["100010002"] = 1
        self.save(before)
        with self.assertRaises(ValueError):
            self.account.end_stage(self.body)
        self.assertEqual(self.account.profile(), before)

    def test_failed_save_rolls_back_completion_openings_and_session_cleanup(self):
        before = self.account.profile()
        self.db.execute(
            "CREATE TRIGGER reject_clear BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.account.end_stage(self.body)
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(self.db.execute("SELECT * FROM campaign_completions").fetchall(), [])
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010002,)]
        )
