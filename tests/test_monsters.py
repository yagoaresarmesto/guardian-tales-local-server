# SPDX-License-Identifier: Apache-2.0
"""Stage-local catalog rewards preserve balances and defeat receipts on retries."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import GuestStore

FIXTURE = Path(__file__).parent / "fixtures/monster_catalog.json"


class MonsterCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "monster_catalog.json"
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
        self.db.execute("INSERT INTO campaign_session VALUES(1,100010002)")
        self.db.commit()
        self.body = {
            "StageId": 100010002,
            "MonsterHandleNames": ["first_goblin_1", "synthetic_slime", "first_goblin_1"],
            "StageCustom": None,
        }

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_mixed_rewards_deduplicate_batches_overlap_and_restart_without_other_changes(self):
        before = self.account.profile()
        response = self.account.beat_monsters(self.body)
        self.assertEqual((response["DropExp"], response["DropGold"]), (7, 24))
        saved = self.account.profile()
        reopened = GuestStore(self.db, self.references).account
        retry = reopened.beat_monsters(self.body)
        self.assertEqual((retry["DropExp"], retry["DropGold"]), (0, 0))
        self.assertEqual(reopened.profile(), saved)
        response = reopened.beat_monsters(
            self.body | {"MonsterHandleNames": ["synthetic_slime", "synthetic_boss"]}
        )
        self.assertEqual((response["DropExp"], response["DropGold"]), (2, 17))
        expected = json.loads(json.dumps(before))
        assets = {a["Id"]: a for a in expected["User"]["Assets"]}
        assets[70004]["Amount"] += 9
        assets[70001]["Amount"] += 41
        expected["User"]["Cas"] += 2
        self.assertEqual(reopened.profile(), expected)
        self.assertEqual(
            self.db.execute(
                "SELECT stage_id,category,key,value FROM campaign_progress ORDER BY key"
            ).fetchall(),
            [(100010002, 10, key, "true") for key in (1, 9, 254)],
        )
        self.assertNotEqual(reopened.stage_progress(100010002), "")

    def test_same_handle_and_index_in_another_stage_have_independent_receipts(self):
        self.account.beat_monsters(self.body | {"MonsterHandleNames": ["first_goblin_1"]})
        self.db.execute("UPDATE campaign_session SET stage_id=100010001")
        self.db.commit()
        response = self.account.beat_monsters(
            self.body | {"StageId": 100010001, "MonsterHandleNames": ["first_goblin_1"]}
        )
        self.assertEqual((response["DropExp"], response["DropGold"]), (79, 87))
        self.assertEqual(
            self.db.execute(
                "SELECT stage_id,key FROM campaign_progress ORDER BY stage_id"
            ).fetchall(),
            [(100010001, 1), (100010002, 1)],
        )

    def test_invalid_reports_unknown_stages_and_wrong_active_stage_cannot_grant_rewards(self):
        before = self.account.profile()
        for body in (
            None,
            {},
            self.body | {"StageId": True},
            self.body | {"StageId": 100010003},
            self.body | {"MonsterHandleNames": []},
            self.body | {"MonsterHandleNames": "first_goblin_1"},
            self.body | {"MonsterHandleNames": ["first_goblin_1", "unknown"]},
            self.body | {"MonsterHandleNames": [True]},
            self.body | {"StageCustom": {"Score": 1}},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.account.beat_monsters(body)
        self.db.execute("UPDATE campaign_session SET stage_id=100010001")
        self.db.commit()
        with self.assertRaises(ValueError):
            self.account.beat_monsters(self.body)
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaign_progress").fetchone(), (0,))

    def test_invalid_catalogs_and_missing_catalog_cannot_change_saved_state(self):
        before = self.account.profile()
        for patch in (
            {"index": True},
            {"index": 255},
            {"index": 9},
            {"experience": -1},
            {"gold": False},
            {"extra": 1},
        ):
            catalog = json.loads(FIXTURE.read_bytes())
            catalog["stages"]["100010002"]["first_goblin_1"].update(patch)
            self.catalog_file.write_text(json.dumps(catalog))
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.account.beat_monsters(self.body)
        self.catalog_file.unlink()
        with self.assertRaises(ValueError):
            self.account.beat_monsters(self.body)
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaign_progress").fetchone(), (0,))

    def test_failed_profile_write_rolls_back_defeat_markers_and_both_balances(self):
        before = self.account.profile()
        self.db.execute(
            "CREATE TRIGGER reject_monsters BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.account.beat_monsters(self.body)
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaign_progress").fetchone(), (0,))
