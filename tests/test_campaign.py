# SPDX-License-Identifier: Apache-2.0
"""Initial chapter progress must exist without claiming any completed content."""

import base64
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.campaign import FIRST_CHAPTER_STAGES, FIRST_STAGE_ID, encode_stage_progress
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet


def request(route, body):
    return parse_packet(
        encode_packet(Packet(0, json.dumps(body).encode(), body_type=1, sequence_id=1, api=route))
    )


class ChapterProgressTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)
        self.session.handle(
            request(
                "/auth/sign-in", {"AuthKind": 0, "AccessToken": "LOCAL_TEST", "Reconnect": False}
            )
        )

    def tearDown(self):
        self.db.close()

    def test_opening_entry_ui_has_empty_progress_objects_without_granting_progress(self):
        before = self.store.account.profile()
        response = self.session.handle(
            request("/stage/get-stage-progresses", {"ChapterCode": 10001})
        )
        value = read_json_body(parse_packet(encode_packet(response)))
        self.assertEqual(
            set(value["StageProgresses"]), {str(stage) for stage in FIRST_CHAPTER_STAGES}
        )
        self.assertTrue(all(progress == "" for progress in value["StageProgresses"].values()))
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(before["UserProgress"]["StageStates"], {})

    def test_unknown_or_malformed_chapter_does_not_change_account(self):
        before = self.store.account.profile()
        for body in (None, {}, {"ChapterCode": True}, {"ChapterCode": 10002}):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.session.handle(request("/stage/get-stage-progresses", body))
        self.assertEqual(self.store.account.profile(), before)

    def complete_prologue(self):
        self.store.account.complete_prologue(
            "lab",
            {
                "IsMale": True,
                "VoiceType": 1,
                "Weapon1ItemId": 9010010,
                "Weapon2ItemId": 9080010,
                "BobLindaQuestGrade": 0,
            },
        )

    def enter_first_phase(self):
        self.complete_prologue()
        profile = self.store.account.profile()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70032)["Amount"] = 40
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()
        self.store.account.start_stage({"StageId": FIRST_STAGE_ID})

    def test_purple_coins_retry_overlap_restart_and_native_progress_bytes(self):
        self.enter_first_phase()
        body = {
            "StageId": FIRST_STAGE_ID,
            "Items": [{"Id": key, "ItemId": 71001} for key in (4, 3, 2, 21, 22)],
            "StageCustom": None,
        }
        self.session.handle(request("/stage/pick-stage-coins", body))
        saved = self.store.account.profile()
        self.assertEqual(next(a for a in saved["User"]["Assets"] if a["Id"] == 71001)["Amount"], 5)
        # Native v2: version, store count, purple-coin category, bit count,
        # LSB-first bits, integer count, trailing stage flag.
        wire = self.store.account.stage_progress(FIRST_STAGE_ID)
        self.assertEqual(base64.b64decode(wire), bytes.fromhex("02 01 02 17 1c 00 60 00 00"))
        reopened = GuestStore(self.db).account
        reopened.pick_stage_coins(body)
        self.assertEqual(reopened.profile(), saved)
        self.assertEqual(
            reopened.read("/stage/get-stage-progresses", {"ChapterCode": 10001})["StageProgresses"][
                str(FIRST_STAGE_ID)
            ],
            wire,
        )
        reopened.pick_stage_coins(
            body | {"Items": [{"Id": 22, "ItemId": 71001}, {"Id": 23, "ItemId": 71001}]}
        )
        saved = reopened.profile()
        self.assertEqual(next(a for a in saved["User"]["Assets"] if a["Id"] == 71001)["Amount"], 6)
        for invalid in (
            {"Id": 27, "ItemId": 71001},
            {"Id": True, "ItemId": 71001},
            {"Id": 24, "ItemId": 70001},
            {"Id": 24, "ItemId": 71001, "Amount": 999},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                reopened.pick_stage_coins(body | {"Items": [{"Id": 24, "ItemId": 71001}, invalid]})
        self.assertEqual(reopened.profile(), saved)
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaign_progress").fetchone()[0], 6)

    def test_native_progress_integer_and_boolean_boundary_layout(self):
        wire = encode_stage_progress({9: {0: True, 8: -2}})
        self.assertEqual(
            base64.b64decode(wire), bytes.fromhex("02 01 09 09 01 00 01 08 fe ff ff ff 00")
        )
        for stores in ({12: {0: True}}, {2: {255: True}}, {2: {True: 1}}, {9: {1: 0x80000000}}):
            with self.subTest(stores=stores), self.assertRaises(ValueError):
                encode_stage_progress(stores)

    def test_initial_monster_rewards_are_atomic_and_not_repeated_after_restart(self):
        self.enter_first_phase()
        body = {
            "StageId": FIRST_STAGE_ID,
            "MonsterHandleNames": ["first_goblin_1", "first_goblin_2"],
            "StageCustom": None,
        }
        response = self.store.account.beat_monsters(body)
        self.assertEqual((response["DropExp"], response["DropGold"]), (158, 174))
        assets = {a["Id"]: a for a in response["User"]["Assets"]}
        self.assertEqual((assets[70004]["Amount"], assets[70001]["Amount"]), (158, 174))
        saved = self.store.account.profile()
        reopened = GuestStore(self.db).account
        retried = reopened.beat_monsters(body)
        self.assertEqual((retried["DropExp"], retried["DropGold"]), (0, 0))
        self.assertEqual(reopened.profile(), saved)
        with self.assertRaises(ValueError):
            reopened.beat_monsters(body | {"MonsterHandleNames": ["first_goblin_1", "unknown"]})
        self.assertEqual(reopened.profile(), saved)

    def test_named_items_have_stable_receipts_and_do_not_replace_starter_equipment(self):
        self.enter_first_phase()
        before = self.store.account.profile()["User"]
        body = {"StageId": FIRST_STAGE_ID, "StageItemKey": "shield", "StageCustom": None}
        response = self.store.account.pick_stage_item(body)
        self.assertEqual(response["AddedItem"]["ItemId"], 9080040)
        self.assertEqual(response["AddedItem"]["Id"], before["ItemIdCounter"] + 1)
        self.assertEqual(response["User"]["Characters"], before["Characters"])
        saved = self.store.account.profile()
        reopened = GuestStore(self.db).account
        self.assertEqual(reopened.pick_stage_item(body), response)
        self.assertEqual(reopened.profile(), saved)
        with self.assertRaises(ValueError):
            reopened.pick_stage_item(body | {"StageItemKey": "unknown"})
        self.assertEqual(reopened.profile(), saved)
        costume = reopened.pick_stage_item(body | {"StageItemKey": "costume"})
        self.assertEqual(costume["User"]["ItemMiscs"][0]["ItemId"], 10048)
        self.assertEqual(len(costume["User"]["ItemWeapons"]), len(before["ItemWeapons"]) + 1)

    def test_unlock_consumes_charged_then_reserve_stamina_once_across_restart(self):
        self.complete_prologue()
        profile = self.store.account.profile()
        for asset in profile["User"]["Assets"]:
            if asset["Id"] == 70006:
                asset["Amount"] = 5
            if asset["Id"] == 70032:
                asset["Amount"] = 40
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()
        packet = self.session.handle(request("/stage/start-stage", {"StageId": FIRST_STAGE_ID}))
        first = read_json_body(parse_packet(encode_packet(packet)))
        assets = {a["Id"]: a for a in first["User"]["Assets"]}
        self.assertEqual((assets[70006]["Amount"], assets[70032]["Amount"]), (0, 30))
        self.assertEqual((assets[70006]["Spent"], assets[70032]["Spent"]), (5, 10))
        self.assertEqual(first["UserProgress"]["StageStates"], {str(FIRST_STAGE_ID): 3})
        self.assertEqual(first["UserProgress"]["LastPlayedStageId"], FIRST_STAGE_ID)
        self.assertEqual(first["StageProgress"], "")
        restarted = GuestStore(self.db)
        self.assertEqual(restarted.account.start_stage({"StageId": FIRST_STAGE_ID}), first)
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchone()[0], FIRST_STAGE_ID
        )

    def test_glove_chest_requires_active_stage_and_retries_return_the_same_item(self):
        body = {"StageId": FIRST_STAGE_ID, "TreasureBoxKey": "mole_glove_box", "StageCustom": None}
        with self.assertRaises(PacketError):
            self.session.handle(request("/stage/open-treasure", body))
        self.enter_first_phase()
        packet = self.session.handle(request("/stage/open-treasure", body))
        result = read_json_body(parse_packet(encode_packet(packet)))
        self.assertEqual(len(result["AddedItems"]), 1)
        self.assertEqual(result["AddedItems"][0]["ItemId"], 30017)
        self.assertEqual(result["User"]["ItemMiscs"], result["AddedItems"])
        saved = self.store.account.profile()
        restarted = GuestStore(self.db).account
        self.assertEqual(restarted.open_treasure(body), result)
        self.assertEqual(restarted.profile(), saved)
        self.assertEqual(
            self.db.execute(
                "SELECT value FROM campaign_progress WHERE category=5 AND key=1"
            ).fetchone(),
            ("true",),
        )
        with self.assertRaises(ValueError):
            restarted.open_treasure(body | {"TreasureBoxKey": "unknown"})
        self.assertEqual(restarted.profile(), saved)

    def test_insufficient_stamina_does_not_unlock_or_create_active_session(self):
        self.complete_prologue()
        before = self.store.account.profile()
        with self.assertRaisesRegex(PacketError, "Not enough stamina"):
            self.session.handle(request("/stage/start-stage", {"StageId": FIRST_STAGE_ID}))
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaign_session").fetchone()[0], 0)

    def test_clear_exit_preserves_items_and_is_idempotent_after_session_ends(self):
        self.enter_first_phase()
        body = {
            "StageId": FIRST_STAGE_ID,
            "ExitName": "exit_forest_1_2",
            "IsClearExit": True,
            "StageCustom": {"HitCount": 14, "NoDamage": False},
        }
        before = self.store.account.profile()
        with self.assertRaises(ValueError):
            self.store.account.end_stage(body)
        self.assertEqual(self.store.account.profile(), before)
        quest = {"StageId": FIRST_STAGE_ID, "QuestId": 27, "StageCustom": None}
        self.store.account.start_quest(quest)
        for step in range(1, 5):
            self.store.account.progress_quest(quest | {"InnerProgress": step})
        self.store.account.open_treasure(
            {"StageId": FIRST_STAGE_ID, "TreasureBoxKey": "mole_glove_box", "StageCustom": None}
        )
        before = self.store.account.profile()
        for changed in (
            {"ExitName": "unknown"},
            {"IsClearExit": 1},
            {"StageCustom": {"HitCount": True}},
            {"StageCustom": {"Category": 9}},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.store.account.end_stage(body | changed)
        self.assertEqual(self.store.account.profile(), before)
        packet = self.session.handle(request("/stage/end-stage", body))
        response = read_json_body(parse_packet(encode_packet(packet)))
        self.assertEqual(response["StageState"], 7)
        self.assertEqual(response["AddedItems"], [])
        self.assertTrue(response["StageProgress"])
        next(asset for asset in before["User"]["Assets"] if asset["Id"] == 70003)["Amount"] += 50
        before["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile()["User"], before["User"])
        self.assertEqual(
            self.db.execute("SELECT gems FROM campaign_grade_claims").fetchone(), (50,)
        )
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaign_session").fetchone()[0], 0)
        self.assertEqual(
            self.db.execute("SELECT hit_count,no_damage FROM campaign_completions").fetchone(),
            (14, 0),
        )
        restarted = GuestStore(self.db).account
        saved = restarted.profile()
        self.assertEqual(restarted.end_stage(body), response)
        self.assertEqual(restarted.profile(), saved)

    def test_completion_tutorial_requires_clear_and_deduplicates_across_restart(self):
        self.complete_prologue()
        with self.assertRaises(PacketError):
            self.session.handle(request("/user/mark-tutorial", {"tutorialIds": [200]}))
        profile = self.store.account.profile()
        profile["UserProgress"]["StageStates"][str(FIRST_STAGE_ID)] = 7
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()
        for values in ([True], [201], [], [200, True]):
            with self.subTest(values=values), self.assertRaises(PacketError):
                self.session.handle(request("/user/mark-tutorial", {"tutorialIds": values}))
        self.assertEqual(self.store.account.profile(), profile)
        packet = self.session.handle(request("/user/mark-tutorial", {"tutorialIds": [200, 200]}))
        response = read_json_body(parse_packet(encode_packet(packet)))
        self.assertEqual(response["UserProgress"]["Tutorials"], [200])
        saved = self.store.account.profile()
        restarted = GuestStore(self.db).account
        self.assertEqual(restarted.mark_tutorial({"tutorialIds": [200]}), response)
        self.assertEqual(restarted.profile(), saved)

    def test_world_map_intro_requires_inn_clear_and_preserves_other_progress(self):
        self.complete_prologue()
        before = self.store.account.profile()
        with self.assertRaises(PacketError):
            self.session.handle(request("/user/mark-tutorial", {"tutorialIds": [1003, 2019]}))
        self.assertEqual(self.store.account.profile(), before)
        before["UserProgress"]["StageStates"][str(FIRST_STAGE_ID)] = 7
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(before),))
        self.db.commit()
        packet = self.session.handle(request("/user/mark-tutorial", {"tutorialIds": [2019, 2019]}))
        response = read_json_body(parse_packet(encode_packet(packet)))
        before["UserProgress"]["Tutorials"].append(2019)
        before["UserProgress"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), before)
        restarted = GuestStore(self.db).account
        self.assertEqual(restarted.mark_tutorial({"tutorialIds": [2019]}), response)
        self.assertEqual(restarted.profile(), before)

    def test_unfinished_prologue_or_unsupported_stage_cannot_start(self):
        before = self.store.account.profile()
        for body in (
            {"StageId": FIRST_STAGE_ID},
            {"StageId": FIRST_STAGE_ID + 1},
            {"StageId": True},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.session.handle(request("/stage/start-stage", body))
        self.assertEqual(self.store.account.profile(), before)

    def test_initial_quest_requires_stage_and_survives_restart_without_duplicates(self):
        body = {"StageId": FIRST_STAGE_ID, "QuestId": 27, "StageCustom": None}
        with self.assertRaises(PacketError):
            self.session.handle(request("/stage/start-quest", body))
        self.complete_prologue()
        profile = self.store.account.profile()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70032)["Amount"] = 40
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()
        self.store.account.start_stage({"StageId": FIRST_STAGE_ID})
        packet = self.session.handle(request("/stage/start-quest", body))
        self.assertEqual(read_json_body(parse_packet(encode_packet(packet))), {"OpenedStages": []})
        saved = self.store.account.profile()
        self.assertEqual(
            saved["UserProgress"]["QuestProgresses"],
            [{"Id": 27, "Grade": -1, "InnerProgress": 0, "CustomStates": {}}],
        )
        restarted = GuestStore(self.db)
        restarted.account.start_quest(body)
        self.assertEqual(restarted.account.profile(), saved)
        checkpoint = body | {"InnerProgress": 1}
        restarted.account.progress_quest(checkpoint)
        saved = restarted.account.profile()
        self.assertEqual(saved["UserProgress"]["QuestProgresses"][0]["InnerProgress"], 1)
        self.assertEqual(saved["UserProgress"]["QuestProgresses"][0]["Grade"], -1)
        restarted = GuestStore(self.db)
        restarted.account.progress_quest(checkpoint)
        self.assertEqual(restarted.account.profile(), saved)
        for value in (True, -1, 13, 3):
            with self.subTest(value=value), self.assertRaises(ValueError):
                restarted.account.progress_quest(checkpoint | {"InnerProgress": value})
        restarted.account.progress_quest(checkpoint | {"InnerProgress": 2})
        saved = restarted.account.profile()
        restarted.account.progress_quest(checkpoint)
        self.assertEqual(restarted.account.profile(), saved)
        for changed in ({"QuestId": True}, {"QuestId": 28}, {"StageCustom": {"X": 1}}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                restarted.account.start_quest(body | changed)
        self.assertEqual(restarted.account.profile(), saved)
