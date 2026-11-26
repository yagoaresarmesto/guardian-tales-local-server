# SPDX-License-Identifier: Apache-2.0
"""Story entry keeps earned openings, stamina and each stage's progress separate."""

import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.campaigns.story import load_story_catalog, open_eligible_stages
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import PacketError, encode_packet
from tests import FIXTURES
from tests.account.test_snapshots import request

FIXTURE = FIXTURES / "story_catalog.json"


class NativeStoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        tables = {
            "chapterdata": {
                "Chapter": [
                    {
                        "ChapterId": i,
                        "Chapters": f"chapter_{i % 100}",
                        "FirstStageId": i * 10000 + 1,
                    }
                    for i in (10021, 10022)
                ]
            },
            "stages": [
                {
                    "Id": 100210001,
                    "Stamina": 15,
                    "IsOpened": True,
                    "Quests": [465],
                    "Tilemap": {"Default": "water"},
                },
                {
                    "Id": 100220001,
                    "Stamina": 15,
                    "ClearedQuests": [465],
                    "Tilemap": {"Default": "fire"},
                },
                {"Id": 110220001, "Stamina": 10, "Tilemap": {"Default": "substage"}},
                {"Id": 810220001, "Stamina": 0, "Tilemap": {"Default": "raid"}},
            ],
            "items": [
                {"Id": 30001, "Type": "orb"},
                {"Id": 10101, "Type": "costume"},
            ],
            "chapterprogressreward": [
                {
                    "ChapterId": 21,
                    "StageType": 10,
                    "Difficulty": 0,
                    "Rewards": [{"ItemId": 10101, "Amount": 1}],
                }
            ],
            "followers": {
                "Rewards": [{"Id": 1, "Count": 1, "Rewards": [{"ItemId": 70003, "Amount": 5}]}]
            },
            "unlockfeature": [
                {
                    "Id": 12,
                    "Type": "StageClear",
                    "Value": {"Default": 100210001},
                    "Rewards": [{"ItemId": 70003, "Amount": 4}],
                }
            ],
            "quests": [
                {
                    "Id": 465,
                    "EndingGrades": [0],
                    "CommonRewards": [
                        {"ItemId": 70001, "Amount": 7},
                        {"CharacterId": 19, "Level": 1},
                    ],
                }
            ],
        }
        rows = []
        for name, content in tables.items():
            raw = json.dumps(content)
            rows.append(f"{name}\n{raw}\n1\n{digest(raw.encode())}\n")
        (root / "static_data_get.bin").write_bytes(compress(("".join(rows) + "\n\n\n").encode()))
        (root / "story_handles.json").write_text(
            json.dumps(
                {
                    "tilemaps": {
                        "fire": {
                            "1": {"door": 1},
                            "2": {"coin": 1},
                            "3": {"star": 2},
                            "10": {"enemy": 3},
                        }
                    }
                }
            )
        )
        (root / "training_catalog.json").write_text(json.dumps({"experience_by_level": [0]}))
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        store = GuestStore(self.db, root)
        self.account = store.account
        self.account.complete_prologue(
            "test",
            {
                "IsMale": True,
                "VoiceType": 1,
                "Weapon1ItemId": 9010010,
                "Weapon2ItemId": 9080010,
                "BobLindaQuestGrade": 0,
            },
        )
        profile = self.account.profile()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70032)["Amount"] = 40
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        self.session = BootstrapSession(store)
        self.call("/auth/sign-in", {"AuthKind": 0, "AccessToken": "test", "Reconnect": False})

    def call(self, route, body):
        return read_json_body(
            parse_packet(encode_packet(self.session.handle(request(route, body))))
        )

    def test_story_quest_unlocks_later_world_and_map_progress_is_scoped(self):
        stages = self.call("/stage/get-stage-progresses", {"ChapterCode": 10022})["StageProgresses"]
        self.assertEqual(stages, {"100220001": "", "110220001": ""})
        with self.assertRaises(PacketError):
            self.call("/stage/start-stage", {"StageId": 100220001})
        self.call("/stage/start-stage", {"StageId": 100210001})
        body = {"StageId": 100210001, "QuestId": 465}
        self.call("/stage/start-quest", body)
        self.call("/stage/progress-quest", body | {"InnerProgress": 3})
        self.call(
            "/stage/set-custom",
            {
                "StageId": 100210001,
                "StageCustom": {"QuestId": 465, "QuestCustomState": {"stage": 1}},
            },
        )
        self.call("/stage/set-quest-custom-state", {"QuestId": 465, "CustomState": {"map": -2}})
        with self.assertRaises(PacketError):
            self.call("/stage/clear-quest", body | {"Grade": 99})
        result = self.call("/stage/clear-quest", body | {"Grade": 0})
        self.assertEqual(result["OpenedStages"], [100220001])
        self.assertEqual(result["AddedCharacters"], [{"characterId": 19}])
        self.assertEqual(result["AddedItems"], [{"Id": 0, "ItemId": 70001, "Amount": 7}])
        cleared = self.account.profile()
        retry = self.call("/stage/clear-quest", body | {"Grade": 0})
        self.assertEqual(retry["AddedItems"], [])
        self.assertEqual(self.account.profile(), cleared)
        quest = next(q for q in cleared["UserProgress"]["QuestProgresses"] if q["Id"] == 465)
        self.assertEqual(
            quest,
            {"Id": 465, "Grade": 0, "InnerProgress": 3, "CustomStates": {"stage": 1, "map": -2}},
        )

        self.call("/stage/start-stage", {"StageId": 100220001})
        stage = {"StageId": 100220001}
        custom = {
            "Category": 1,
            "CustomValues": [{"KeyIndex": 1, "KeyName": "door", "BooleanValue": True}],
        }
        self.call("/stage/set-custom", stage | {"StageCustom": custom})
        self.assertEqual(
            self.db.execute(
                "SELECT value FROM campaign_progress WHERE stage_id=100220001 AND category=1 AND key=1"
            ).fetchone(),
            ("true",),
        )
        self.call("/stage/beat-monsters", stage | {"MonsterHandleNames": ["enemy"]})
        coins = stage | {"Items": [{"Id": 1, "ItemId": 71022}, {"Id": 2, "ItemId": 70005}]}
        self.call("/stage/pick-stage-coins", coins)
        result = self.call("/stage/pick-stage-coins", coins)
        self.assertEqual(next(a["Amount"] for a in result["User"]["Assets"] if a["Id"] == 71022), 1)
        left = self.call("/stage/end-stage", stage | {"ExitName": None, "IsClearExit": False})
        self.assertEqual(left["StageState"], 3)
        self.assertTrue(left["StageProgress"])

    def test_story_reward_claims_require_progress_and_survive_retries(self):
        chapter = "/user/claim-chapter-progress-rewards", {"ChapterCode": 10021}
        feature = "/user/claim-unlock-feature-rewards", {"Feature": 12}
        follower = "/user/claim-sns-follower-rewards", {"SnsFollowerRewardId": 1}
        for route, body in (chapter, feature, follower):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(route, body)
        p = self.account.profile()
        p["UserProgress"]["StageStates"]["100210001"] = 31
        p["UserProgress"]["Followers"] = [42]
        for field in ("PurpleCoins", "StarPieces"):
            p[field]["10021"] = {"Current": 1, "Total": 1}
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(p),))
        for route, body in (chapter, feature, follower):
            self.assertEqual(len(self.call(route, body)["AddedItems"]), 1)
            saved = self.account.profile()
            self.assertEqual(self.call(route, body)["AddedItems"], [])
            self.assertEqual(self.account.profile(), saved)

    def test_gimmick_and_invalid_collectible_batch_roll_back_together(self):
        p = self.account.profile()
        p["UserProgress"]["QuestProgresses"].append(
            {"Id": 465, "Grade": 0, "InnerProgress": 3, "CustomStates": {}}
        )
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(p),))
        stage = {"StageId": 100220001}
        self.call("/stage/start-stage", stage)
        custom = {
            "Category": 1,
            "CustomValues": [{"KeyIndex": 1, "KeyName": "door", "BooleanValue": True}],
        }
        before = self.account.profile()
        with self.assertRaises(PacketError):
            self.call(
                "/stage/pick-stage-coins",
                stage | {"StageCustom": custom, "Items": [{"Id": 8, "ItemId": 71022}]},
            )
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(self.account.stage_progress(100220001), "")
        self.call(
            "/stage/pick-stage-coins",
            stage | {"StageCustom": custom, "Items": [{"Id": 1, "ItemId": 71022}]},
        )
        self.assertEqual(
            self.db.execute(
                "SELECT category,key FROM campaign_progress ORDER BY category"
            ).fetchall(),
            [(1, 1), (2, 1)],
        )


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

    def configure_discovered_stage(self):
        catalog = json.loads(FIXTURE.read_bytes())
        catalog["stages"]["110010005"] = {
            "stamina": 10,
            "requires_cleared": [],
            "quest_ids": [57],
            "requires_discovery": True,
        }
        self.catalog_file.write_text(json.dumps(catalog))
        self.account = GuestStore(self.db, self.references).account

    def test_discovered_stage_entry_preserves_quests_and_spends_its_cost_only_once(self):
        self.configure_discovered_stage()
        before = self.account.profile()
        response = self.account.start_stage({"StageId": 110010005})
        expected = json.loads(json.dumps(before))
        assets = {a["Id"]: a for a in expected["User"]["Assets"]}
        for asset in (assets[70006], assets[70032]):
            asset["Amount"] -= 5
            asset["Spent"] += 5
        expected["User"]["Cas"] += 1
        expected["UserProgress"]["Cas"] += 1
        expected["UserProgress"]["LastPlayedStageId"] = 110010005
        expected["UserProgress"]["StageStates"]["110010005"] = 3
        self.assertEqual(self.account.profile(), expected)
        reopened = GuestStore(self.db, self.references).account
        self.assertEqual(reopened.start_stage({"StageId": 110010005}), response)
        self.assertEqual(reopened.profile(), expected)
        reopened.start_quest({"StageId": 110010005, "QuestId": 57, "StageCustom": None})
        quests = reopened.profile()["UserProgress"]["QuestProgresses"]
        self.assertEqual(quests[0], before["UserProgress"]["QuestProgresses"][0])
        self.assertEqual([q["Id"] for q in quests], [27, 57])
        with self.assertRaises(ValueError):
            reopened.start_quest({"StageId": 110010005, "QuestId": 34, "StageCustom": None})

    def test_clear_prerequisites_cannot_replace_required_map_discovery(self):
        self.configure_discovered_stage()
        catalog = json.loads(self.catalog_file.read_bytes())
        catalog["stages"]["110010005"]["requires_cleared"] = [100010001]
        self.catalog_file.write_text(json.dumps(catalog))
        profile = self.account.profile()
        profile["UserProgress"]["StageStates"]["100010001"] = 7
        for state in (0, 2):
            profile["UserProgress"]["StageStates"]["110010005"] = state
            self.save(profile)
            self.account = GuestStore(self.db, self.references).account
            before = self.account.profile()
            self.assertEqual(before["UserProgress"]["StageStates"]["110010005"], state)
            with self.assertRaises(ValueError):
                self.account.start_stage({"StageId": 110010005})
            self.assertEqual(self.account.profile(), before)
            self.assertEqual(
                self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010001,)]
            )
        before["UserProgress"]["StageStates"]["110010005"] = 1
        self.save(before)
        self.account.start_stage({"StageId": 110010005})
        self.assertEqual(self.account.profile()["UserProgress"]["StageStates"]["110010005"], 3)

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
            {"requires_discovery": 1},
            {"unknown_flag": True},
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
