# SPDX-License-Identifier: Apache-2.0
"""Catalog clear exits keep rewards, quest state and later active sessions intact."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.runtime.bootstrap import GuestStore
from tests import FIXTURES


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


class NativeMapInteractionTests(unittest.TestCase):
    def setUp(self):
        from guardian_tales.modes.guild.raid_static import compress, digest

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        tables = {
            "chapterdata": {
                "Chapter": [
                    {"ChapterId": 10022, "Chapters": "chapter_22", "FirstStageId": 100220001},
                    {"ChapterId": 10201, "Chapters": "chapter_1_hell", "FirstStageId": 102010001},
                ]
            },
            "stages": [
                {
                    "Id": 100220001,
                    "Name": "first",
                    "Stamina": 0,
                    "Tilemap": {"Default": "one"},
                    "IsOpened": True,
                },
                {"Id": 100220002, "Name": "second", "Stamina": 0, "Tilemap": {"Default": "two"}},
                {
                    "Id": 102010001,
                    "Name": "hell_forest_1",
                    "Stamina": 0,
                    "Tilemap": {"Default": "hell"},
                    "IsOpened": True,
                },
            ],
            "quests": [],
            "constants": {"GemsForStageClearGrade": 50},
            "items": [{"Id": 9010010, "Type": "weapon"}, {"Id": 20050, "Type": "quest_item"}],
            "weaponenhance": {"LevelExps": [{"TotalExps": 200}]},
            "stagemetaitem": {
                "one": {
                    "HandleNames": {
                        "Box": ["", "box"],
                        "Item": ["", "left", "right"],
                        "Exit": ["", "cave", "gate"],
                        "PurpleCoin": ["", "coin"],
                        "StarPiece": ["", "star"],
                    },
                    "Boxes": {
                        "box": [
                            {"ItemSpecId": 9010010, "Amount": 1, "Level": 1},
                            {"ItemSpecId": 70001, "Amount": 4},
                        ]
                    },
                    "Items": {k: {"ItemSpecId": 20050, "Amount": 1} for k in ("left", "right")},
                },
                "two": {"HandleNames": {"PurpleCoin": [""], "StarPiece": [""], "Exit": [""]}},
                "hell": {"HandleNames": {"PurpleCoin": [""], "StarPiece": [""], "Exit": [""]}},
            },
        }
        data = []
        for k, v in tables.items():
            raw = json.dumps(v)
            data.append(f"{k}\n{raw}\n1\n{digest(raw.encode())}\n")
        (directory / "static_data_get.bin").write_bytes(
            compress(("".join(data) + "\n\n\n").encode())
        )
        (directory / "story_map_events.json").write_text(
            json.dumps(
                {
                    "tilemaps": {
                        "one": {"exits": {"gate": "second"}, "inner_exits": {"cave": True}},
                        "two": {},
                    }
                }
            )
        )
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.account = GuestStore(self.db, directory).account
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
        self.account.start_stage({"StageId": 100220001})
        self.body = {"StageId": 100220001}

    def test_multi_item_chest_quest_item_quantity_and_failed_write(self):
        chest = self.body | {"TreasureBoxKey": "box"}
        with self.assertRaises(ValueError):
            self.account.open_treasure(chest | {"StageCustom": {"StageId": 100220002}})
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaign_loot").fetchone(), (0,))
        got = self.account.open_treasure(chest)
        self.assertEqual(
            [(x["ItemId"], x["Amount"]) for x in got["AddedItems"]], [(9010010, 1), (70001, 4)]
        )
        self.assertEqual(got["AddedItems"][0]["Experience"], 200)
        self.assertEqual(self.account.open_treasure(chest), got)
        for name in ("left", "right", "right"):
            self.account.pick_stage_item(self.body | {"StageItemKey": name})
        self.assertEqual(
            [(i["ItemId"], i["Amount"]) for i in self.account.profile()["User"]["ItemMiscs"]],
            [(20050, 2)],
        )

    def test_gate_opens_target_across_replays_and_scripted_finish_has_no_exit_handle(self):
        with self.assertRaises(ValueError):
            self.account.end_stage(self.body | {"IsClearExit": True, "ExitName": "cave"})
        clear = self.body | {"IsClearExit": True, "ExitName": "gate"}
        result = self.account.end_stage(clear)
        self.assertEqual(result["UserProgress"]["StageStates"]["100220002"], 1)
        self.account.start_stage(self.body)
        self.assertEqual(self.account.end_stage(clear)["StageState"], result["StageState"])
        self.assertEqual(self.db.execute("SELECT * FROM campaign_session").fetchall(), [])
        self.account.start_stage({"StageId": 100220002})
        self.assertTrue(
            self.account.end_stage({"StageId": 100220002, "IsClearExit": True, "ExitName": None})[
                "StageState"
            ]
            & 4
        )

    def test_hell_returns_run_score_and_keeps_best_time_and_both_challenges(self):
        stage = {"StageId": 102010001}
        baseline = next(
            a["Amount"] for a in self.account.profile()["User"]["Assets"] if a["Id"] == 70003
        )
        for score, flag in ((81, "ChallengeA"), (92, "ChallengeB"), (76, "ChallengeA")):
            self.account.start_stage(stage)
            result = self.account.end_stage(
                stage
                | {
                    "ExitName": None,
                    "IsClearExit": True,
                    "StageCustom": {"Score": score, flag: True},
                }
            )
            self.assertEqual(result["CurrentScore"], score)
        self.assertEqual(result["StageState"], 1543)
        self.assertEqual(
            next(a["Amount"] for a in result["User"]["Assets"] if a["Id"] == 70003), baseline + 150
        )
        self.assertEqual(
            self.db.execute(
                "SELECT value FROM campaign_progress WHERE stage_id=102010001 AND category=9 AND key=0"
            ).fetchone(),
            ("76",),
        )

    def test_native_star_gems_pay_on_pickup_or_clear_once_and_never_for_precompleted_state(self):
        def gems():
            return next(
                a["Amount"] for a in self.account.profile()["User"]["Assets"] if a["Id"] == 70003
            )

        baseline = gems()
        for i, spec in enumerate((71022, 70005), 1):
            request = self.body | {"Items": [{"Id": 1, "ItemId": spec}]}
            self.account.pick_stage_coins(request)
            self.account.pick_stage_coins(request)
            self.assertEqual(gems(), baseline + 50 * i)
        clear = self.body | {"IsClearExit": True, "ExitName": "gate"}
        self.account.end_stage(clear)
        self.account.start_stage(self.body)
        self.account.end_stage(clear)
        self.assertEqual(gems(), baseline + 150)
        profile = self.account.profile()
        profile["UserProgress"]["StageStates"]["100220002"] = 31
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        self.account.start_stage({"StageId": 100220002})
        self.account.end_stage({"StageId": 100220002, "IsClearExit": True, "ExitName": None})
        self.assertEqual(gems(), baseline + 150)
