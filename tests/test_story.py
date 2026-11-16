# SPDX-License-Identifier: Apache-2.0
"""Story entry keeps earned openings, stamina and each stage's progress separate."""

import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import GuestStore
from guardian_tales.story import load_story_catalog, open_eligible_stages

FIXTURE = Path(__file__).parent / "fixtures/story_catalog.json"


class StoryEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "story_catalog.json"
        self.catalog_file.write_bytes(FIXTURE.read_bytes())
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
        profile["UserProgress"]["StageStates"] = {"100010001": 3, "110010005": 1}
        profile["UserProgress"]["LastPlayedStageId"] = 100010001
        profile["UserProgress"]["QuestProgresses"] = [
            {"Id": 27, "Grade": -1, "InnerProgress": 4, "CustomStates": {}}
        ]
        assets = {a["Id"]: a for a in profile["User"]["Assets"]}
        assets[70006]["Amount"] = 5
        assets[70032]["Amount"] = 20
        self.save(profile)
        self.db.execute("INSERT INTO campaign_session VALUES(1,100010001)")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def save(self, profile):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()

    def clear_first(self):
        profile = self.account.profile()
        profile["UserProgress"]["StageStates"]["100010001"] = 7
        self.save(profile)
        self.account = GuestStore(self.db, self.references).account
        return self.account.profile()

    def configure_passage(self):
        catalog = json.loads(FIXTURE.read_bytes())
        catalog["stages"]["110011001"] = {
            "stamina": 10,
            "requires_cleared": [100010001],
            "quest_ids": [],
        }
        self.catalog_file.write_text(json.dumps(catalog))
        self.account = GuestStore(self.db, self.references).account

    def test_passage_opens_after_inn_and_spends_reserve_once_when_charge_is_empty(self):
        self.configure_passage()
        profile = self.account.profile()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70006)["Amount"] = 0
        self.save(profile)
        before = self.clear_first()
        self.assertEqual(before["UserProgress"]["StageStates"]["110011001"], 1)
        response = self.account.start_stage({"StageId": 110011001})
        expected = json.loads(json.dumps(before))
        reserve = next(a for a in expected["User"]["Assets"] if a["Id"] == 70032)
        reserve["Amount"] -= 10
        reserve["Spent"] += 10
        expected["User"]["Cas"] += 1
        expected["UserProgress"]["Cas"] += 1
        expected["UserProgress"]["StageStates"]["110011001"] = 3
        expected["UserProgress"]["LastPlayedStageId"] = 110011001
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(response["StageProgress"], "")
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(110011001,)]
        )
        reopened = GuestStore(self.db, self.references).account
        self.assertEqual(reopened.start_stage({"StageId": 110011001}), response)
        self.assertEqual(reopened.profile(), expected)

    def test_passage_prerequisite_and_insufficient_total_stamina_preserve_the_save(self):
        self.configure_passage()
        before = self.account.profile()
        with self.assertRaises(ValueError):
            self.account.start_stage({"StageId": 110011001})
        self.assertEqual(self.account.profile(), before)
        before = self.clear_first()
        assets = {a["Id"]: a for a in before["User"]["Assets"]}
        assets[70006]["Amount"], assets[70032]["Amount"] = 0, 9
        self.save(before)
        with self.assertRaises(ValueError):
            self.account.start_stage({"StageId": 110011001})
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010001,)]
        )

    def test_chapter_progress_initializes_passage_and_keeps_saved_progress_separate(self):
        self.configure_passage()
        before = self.clear_first()
        response = self.account.read("/stage/get-stage-progresses", {"ChapterCode": 10001})
        self.assertIn("110011001", response["StageProgresses"])
        self.assertEqual(response["StageProgresses"]["110011001"], "")
        self.db.execute("INSERT INTO campaign_progress VALUES(100010001,2,1,'true')")
        self.db.execute("INSERT INTO campaign_progress VALUES(110011001,3,2,'true')")
        self.db.commit()
        response = self.account.read("/stage/get-stage-progresses", {"ChapterCode": 10001})
        self.assertEqual(
            response["StageProgresses"]["110011001"], self.account.stage_progress(110011001)
        )
        self.assertNotEqual(
            response["StageProgresses"]["110011001"], response["StageProgresses"]["100010001"]
        )
        self.assertEqual(response["StageProgresses"]["100010002"], "")
        self.assertEqual(response["UserProgress"], before["UserProgress"])
        self.assertEqual(self.account.profile(), before)

    def test_earned_opening_entry_split_stamina_and_free_reentry_survive_reopening(self):
        before = self.clear_first()
        self.assertEqual(
            before["UserProgress"]["StageStates"], {"100010001": 7, "110010005": 1, "100010002": 1}
        )
        self.assertEqual(GuestStore(self.db, self.references).account.profile(), before)
        response = self.account.start_stage({"StageId": 100010002})
        expected = json.loads(json.dumps(before))
        assets = {a["Id"]: a for a in expected["User"]["Assets"]}
        assets[70006]["Amount"] = 0
        assets[70006]["Spent"] += 5
        assets[70032]["Amount"] = 10
        assets[70032]["Spent"] += 10
        expected["User"]["Cas"] += 1
        expected["UserProgress"]["StageStates"]["100010002"] = 3
        expected["UserProgress"]["LastPlayedStageId"] = 100010002
        expected["UserProgress"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(response["StageProgress"], "")
        reopened = GuestStore(self.db, self.references).account
        self.assertEqual(reopened.start_stage({"StageId": 100010002}), response)
        self.assertEqual(reopened.profile(), expected)
        reopened.start_stage({"StageId": 100010001})
        reopened.start_stage({"StageId": 100010002})
        self.assertEqual(reopened.profile()["User"], expected["User"])
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010002,)]
        )

    def test_prerequisites_unknown_stages_and_malformed_requests_do_not_mutate(self):
        before = self.account.profile()
        for body in (
            None,
            {},
            {"StageId": True},
            {"StageId": 100010002},
            {"StageId": 100010003},
            {"StageId": 100010001, "Extra": 1},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.account.start_stage(body)
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010001,)]
        )

    def test_insufficient_stamina_and_profile_write_failure_preserve_previous_session(self):
        profile = self.clear_first()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70032)["Amount"] = 9
        self.save(profile)
        with self.assertRaises(ValueError):
            self.account.start_stage({"StageId": 100010002})
        self.assertEqual(self.account.profile(), profile)
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70032)["Amount"] = 20
        self.save(profile)
        self.db.execute(
            "CREATE TRIGGER reject_entry BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.account.start_stage({"StageId": 100010002})
        self.assertEqual(self.account.profile(), profile)
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010001,)]
        )

    def test_invalid_catalog_values_are_rejected_without_changing_the_save(self):
        before = self.account.profile()
        for patch in (
            {"stamina": True},
            {"stamina": -1},
            {"requires_cleared": [100010002]},
            {"requires_cleared": [True]},
            {"quest_ids": [False]},
        ):
            catalog = json.loads(FIXTURE.read_bytes())
            catalog["stages"]["100010002"].update(patch)
            self.catalog_file.write_text(json.dumps(catalog))
            with self.assertRaises(ValueError):
                self.account.start_stage({"StageId": 100010002})
            self.assertEqual(self.account.profile(), before)

    def test_chapter_progress_keeps_each_stage_and_synchronizes_openings(self):
        before = self.clear_first()
        self.db.execute("INSERT INTO campaign_progress VALUES(100010001,2,1,'true')")
        self.db.execute("INSERT INTO campaign_progress VALUES(100010002,3,2,'true')")
        self.db.commit()
        value = self.account.read("/stage/get-stage-progresses", {"ChapterCode": 10001})
        self.assertEqual(
            base64.b64decode(value["StageProgresses"]["100010001"]),
            bytes.fromhex("02 01 02 02 02 00 00"),
        )
        self.assertEqual(
            base64.b64decode(value["StageProgresses"]["100010002"]),
            bytes.fromhex("02 01 03 03 04 00 00"),
        )
        self.assertEqual(value["UserProgress"], before["UserProgress"])
        self.assertEqual(self.account.profile(), before)

    def test_active_stage_catalog_quests_and_sequential_main_checkpoints(self):
        self.clear_first()
        self.account.start_stage({"StageId": 100010002})
        self.account.start_quest({"StageId": 100010002, "QuestId": 34, "StageCustom": None})
        self.assertEqual(
            [q["Id"] for q in self.account.profile()["UserProgress"]["QuestProgresses"]], [27, 34]
        )
        with self.assertRaises(ValueError):
            self.account.start_quest({"StageId": 100010002, "QuestId": 57, "StageCustom": None})
        body = {
            "StageId": 100010002,
            "QuestId": 27,
            "Grade": -1,
            "InnerProgress": 5,
            "StageCustom": None,
        }
        self.account.progress_quest(body)
        saved = self.account.profile()
        self.assertEqual(saved["UserProgress"]["QuestProgresses"][0]["InnerProgress"], 5)
        self.account.progress_quest(body)
        self.assertEqual(self.account.profile(), saved)
        with self.assertRaises(ValueError):
            self.account.progress_quest(body | {"InnerProgress": 7})
        self.assertEqual(self.account.profile(), saved)

    def test_opening_does_not_clear_or_skip_the_next_stage(self):
        profile = self.account.profile()
        profile["UserProgress"]["StageStates"]["100010001"] = 7
        catalog = load_story_catalog(self.account.references)
        catalog["100010003"] = {"stamina": 15, "requires_cleared": [100010002], "quest_ids": [27]}
        self.assertTrue(open_eligible_stages(profile, catalog))
        self.assertEqual(profile["UserProgress"]["StageStates"]["100010002"], 1)
        self.assertNotIn("100010003", profile["UserProgress"]["StageStates"])
        saved = json.loads(json.dumps(profile))
        self.assertFalse(open_eligible_stages(profile, catalog))
        self.assertEqual(profile, saved)
