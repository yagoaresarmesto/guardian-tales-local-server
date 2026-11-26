# SPDX-License-Identifier: Apache-2.0
"""A completed campaign keeps independent save data and can be reapplied safely."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from guardian_tales import campaign_cli, story_world_pass
from guardian_tales.bootstrap import GuestStore
from guardian_tales.campaign import encode_stage_progress
from guardian_tales.campaign_complete import (
    campaign_test_enabled,
    complete_campaign,
    decode_progress,
)
from guardian_tales.raid_static import compress, digest


class CompletedCampaignTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.account = GuestStore(self.db, root).account
        rows = {
            "chapterdata": {
                "Chapter": [
                    {"ChapterId": code, "Chapters": "chapter_1", "FirstStageId": code * 10000 + 1}
                    for code in (10001, 10201)
                ]
            },
            "stages": [
                {"Id": stage_id, "Tilemap": {"Default": name}, "Quests": [27], "Stamina": 15}
                for stage_id, name in (
                    (100010001, "one"),
                    (110010001, "side"),
                    (102010001, "hell"),
                )
            ],
            "quests": [
                {"Id": 27, "Chapter": 1, "EndingGrades": [0]},
                {"Id": 42, "Chapter": 1, "EndingGrades": [2, 0]},
                {"Id": 8000, "Chapter": 900, "EndingGrades": [0]},
            ],
            "followers": {
                "Followers": [{"Id": 9, "StageId": 110010001}, {"Id": 8, "StageId": 700}]
            },
            "questtargetstage": [{"QuestId": 27, "Progress": 14}],
            "worldpass": {
                "Part": [{"Id": 1}],
                "Rewards": [
                    {
                        "Id": 3,
                        "PartId": 1,
                        "Level": 2,
                        "ClearQuestId": 27,
                        "FreeRewardType": "Normal",
                        "GoldRewardType": "Custom",
                        "FreeRewards": [{"Amount": 10, "ItemId": 70003}],
                        "GoldRewards": [
                            {"Amount": 4, "ItemId": 70003},
                            {"Amount": 5, "ItemId": 70003},
                        ],
                    }
                ],
            },
            "stagemetaitem": {
                name: {
                    "HandleNames": {
                        "PurpleCoin": ["", "coin"],
                        "StarPiece": ["", "star"],
                        "Item": ["", "drop"],
                        "Box": [""],
                    }
                }
                for name in ("one", "side", "hell")
            },
        }
        rows["stagemetaitem"]["side"]["StoneBoardItems"] = []
        chunks = []
        for name, value in rows.items():
            body = json.dumps(value)
            chunks.append(f"{name}\n{body}\n1\n{digest(body.encode())}\n")
        (root / "static_data_get.bin").write_bytes(compress(("".join(chunks) + "\n\n\n").encode()))

        profile = self.account.profile()
        progress = profile["UserProgress"]
        progress["StageStates"] = {"100000001": 4, "900000001": 9}
        progress["QuestProgresses"] = [
            {"Id": 42, "Grade": 2, "InnerProgress": 3, "CustomStates": {"choice": 3}},
            {"Id": 8000, "Grade": -1, "InnerProgress": 6, "CustomStates": None},
        ]
        profile["PurpleCoins"] = {"90000": {"Current": 0, "Total": 5}}
        native = encode_stage_progress({1: {2: -42}, 3: {1: True}})
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,'snapshot','before','{}',?)",
                (json.dumps({"100010001": native}),),
            )

    def test_actual_resources_retries_and_nonstory_state(self):
        before = self.account.profile()
        result = complete_campaign(self.db, self.account.references)
        self.assertEqual(
            result,
            dict(chapters=2, stages=3, quests=2, purple_coins=3, star_pieces=3, stone_boards=1),
        )
        self.assertTrue(campaign_test_enabled(self.db))
        p = self.account.profile()
        progress = p["UserProgress"]
        self.assertEqual(progress["StageStates"]["100010001"], 31)
        self.assertEqual(progress["StageStates"]["102010001"], 1543)
        self.assertEqual(progress["StageStates"]["110010001"], 7)
        self.assertEqual(progress["StageStates"]["900000001"], 9)
        self.assertEqual(progress["QuestProgresses"][:2], before["UserProgress"]["QuestProgresses"])
        self.assertEqual(progress["QuestProgresses"][2]["InnerProgress"], 14)
        self.assertEqual(progress["QuestProgresses"][2]["Grade"], 0)
        self.assertEqual(p["User"], before["User"])
        self.assertEqual(p["PurpleCoins"]["10001"], {"Current": 2, "Total": 2})
        self.assertEqual(p["PurpleCoins"]["90000"], before["PurpleCoins"]["90000"])
        self.assertEqual(progress["Followers"], [9])
        self.assertEqual(
            self.db.execute("SELECT stage_id,pieces FROM campaign_stone_pieces").fetchall(),
            [(110010001, 3)],
        )
        stores, _ = decode_progress(self.account.stage_progress(100010001))
        self.assertEqual(stores, {1: {2: -42}, 2: {1: True}, 3: {1: True}, 4: {1: True}})
        writes = self.db.total_changes
        self.assertEqual(complete_campaign(self.db, self.account.references), result)
        self.assertEqual(self.db.total_changes, writes)

    def test_invalid_import_rolls_back_all_progress(self):
        with self.db:
            self.db.execute(
                "UPDATE imported_account SET stage_progresses=? WHERE id=1",
                (json.dumps({"102010001": "AQ=="}),),
            )
        before = self.account.profile()
        with self.assertRaisesRegex(ValueError, "Unsupported imported"):
            complete_campaign(self.db, self.account.references)
        self.assertEqual(self.account.profile(), before)
        self.assertFalse(campaign_test_enabled(self.db))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM campaign_progress").fetchone(), (0,))

    def test_cli_previews_creates_recoverable_backup_and_skips_reapply(self):
        root = self.account.references.directory
        database = root / "server.sqlite3"
        original = self.account.profile()
        with closing(sqlite3.connect(database)) as saved:
            self.db.backup(saved)
        self.assertTrue(campaign_cli.run(root, root, False)["would_change"])
        self.assertFalse((root / "backups").exists())
        result = campaign_cli.run(root, root, True)
        self.assertEqual(result["result"], "applied")
        backup = Path(result["backup"])
        with closing(sqlite3.connect(backup)) as restored:
            self.assertEqual(
                json.loads(restored.execute("SELECT profile FROM local_account").fetchone()[0]),
                original,
            )
            self.assertFalse(campaign_test_enabled(restored))
        self.assertEqual(campaign_cli.run(root, root, True)["result"], "already_complete")
        self.assertEqual(list(backup.parent.glob("*.sqlite3")), [backup])

    def test_world_pass_claims_follow_quest_choice_and_gold_ownership(self):
        handle = story_world_pass.handle
        body = {"PartId": 1, "Level": 2, "IsGold": False, "Index": -1}
        with self.assertRaises(ValueError):
            handle(self.account, story_world_pass.CLAIM, body)
        complete_campaign(self.db, self.account.references)
        with self.assertRaises(ValueError):
            handle(self.account, story_world_pass.CLAIM, dict(body, IsGold=True, Index=1))
        earned = handle(self.account, story_world_pass.CLAIM, body)
        self.assertEqual(earned["AddedItems"][0]["Amount"], 10)
        self.assertEqual(handle(self.account, story_world_pass.CLAIM, body)["AddedItems"], [])

        profile = self.account.profile()
        profile["UserWorldClearPass"]["PurchasedGoldPass"] = [1]
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        all_body = {"PartId": 1, "CustomGoldRewardIndexes": {"2": 1}}
        with self.assertRaises(ValueError):
            handle(
                self.account,
                story_world_pass.CLAIM_ALL,
                dict(all_body, CustomGoldRewardIndexes={"2": 2}),
            )
        response = handle(self.account, story_world_pass.CLAIM_ALL, all_body)
        self.assertEqual(response["AddedItems"][0]["Amount"], 5)
        state = response["UserWorldClearPass"]
        self.assertEqual(state["GoldRewardClaimedList"], [3])
        self.assertEqual(state["FreeRewardClaimedList"], [3])
        self.assertEqual(state["PurchasedGoldPass"], [1])
        self.assertEqual(
            state["SelectedCustomSlots"], [dict(PartId=1, Level=2, IsGold=True, Index=1)]
        )
        self.assertEqual(
            handle(self.account, story_world_pass.CLAIM_ALL, all_body)["AddedItems"], []
        )
