# SPDX-License-Identifier: Apache-2.0
import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.campaigns import story_interactions as api
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import PacketError, encode_packet
from tests.account.test_snapshots import request


class StoryInteractionTests(unittest.TestCase):
    stage = 100140013

    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = {
            "chapterdata": {
                "Chapter": [
                    {"ChapterId": 10014, "FirstStageId": self.stage, "Chapters": "chapter_14"}
                ]
            },
            "stages": [
                {
                    "Id": self.stage,
                    "Name": "demonshire_4_1",
                    "Stamina": 0,
                    "Tilemap": {"Default": "board"},
                    "IsOpened": True,
                    "ReviveLimitCount": 2,
                },
                {
                    "Id": self.stage + 1,
                    "Name": "demonshire_4_2",
                    "Stamina": 0,
                    "Tilemap": {"Default": "branch"},
                },
                {
                    "Id": self.stage + 4,
                    "Name": "later",
                    "Stamina": 0,
                    "Tilemap": {"Default": "later"},
                },
            ],
            "mainqueststagesequence": [{"StageSequence": [self.stage, self.stage + 4, self.stage]}],
            "quests": [],
            "constants": {
                "RadarPrices": [{"Id": self.stage, "Currency": "Gem", "Price": 3}],
                "ReviveCosts": [5, 7],
            },
            "followers": {"Followers": [{"Id": 0, "StageId": self.stage}]},
            "items": [
                {"Id": 20050, "Type": "quest_item", "Name": "board_stone_piece"},
                {"Id": 10018, "Type": "costume", "Name": "costume"},
            ],
            "stagemetaitem": {
                "board": {
                    "HandleNames": {"General": ["", "door"]},
                    "Items": {"stone": {"ItemSpecId": 20050, "Amount": 1}},
                    "StoneBoardItems": [{"ItemSpecId": 10018, "Amount": 1}],
                }
            },
        }
        rows = []
        for name, table in source.items():
            data = json.dumps(table)
            rows.append(f"{name}\n{data}\n1\n{digest(data.encode())}\n")
        (root / "static_data_get.bin").write_bytes(compress(("".join(rows) + "\n\n\n").encode()))
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        store = GuestStore(db, root)
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
        p = self.account.profile()
        u = p["User"]
        for a in u["Assets"]:
            if a["Id"] in (70001, 70003):
                a["Amount"] = 40
        u["ItemIdCounter"] += 1
        self.piece = u["ItemIdCounter"]
        u["ItemMiscs"].append({"Id": self.piece, "ItemId": 20050, "Amount": 3, "Locked": False})
        with db:
            db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(p),))
        self.session = BootstrapSession(store)
        self.seq = 0
        self.call("/auth/sign-in", {"AuthKind": 0, "AccessToken": "test", "Reconnect": False})
        self.call("/stage/start-stage", {"StageId": self.stage})

    def call(self, route, body, *, retry=False):
        if not retry:
            self.seq += 1
        packet = request(route, body)
        packet["sequence_id"] = self.seq
        return read_json_body(parse_packet(encode_packet(self.session.handle(packet))))

    def balance(self, spec):
        return next(
            r["Amount"] for r in self.account.profile()["User"]["Assets"] if r["Id"] == spec
        )

    def test_payments_rollback_puzzle_state_and_retry(self):
        state = {
            "StageId": self.stage,
            "StageCustom": {
                "Category": 1,
                "CustomValues": [{"KeyIndex": 1, "KeyName": "door", "BooleanValue": True}],
            },
        }
        with self.assertRaises(PacketError):
            self.call(api.PAY_GOLD, state | {"Gold": 41})
        self.assertEqual(self.account.stage_progress(self.stage), "")
        gold = state | {"Gold": 10}
        self.call(api.PAY_GOLD, gold)
        self.call(api.PAY_GOLD, gold, retry=True)
        self.assertEqual(self.balance(70001), 30)
        with self.assertRaises(PacketError):
            self.call(api.PAY_GOLD, state | {"Gold": 2}, retry=True)
        self.call(api.PAY_ITEMS, state | {"UseItems": {str(self.piece): 2}})
        with self.assertRaises(PacketError):
            self.call(api.PAY_ITEMS, state | {"UseItems": {str(self.piece): 2}})
        self.assertEqual(
            next(
                r["Amount"]
                for r in self.account.profile()["User"]["ItemMiscs"]
                if r["Id"] == self.piece
            ),
            1,
        )

    def test_first_visit_to_hub_opens_scripted_nonclear_destinations(self):
        branch = {"StageId": self.stage + 1}
        with self.assertRaises(PacketError):
            self.call("/stage/start-stage", branch)
        result = self.call(
            "/stage/end-stage",
            {"StageId": self.stage, "ExitName": "exit_demonshire_4_2", "IsClearExit": False},
        )
        self.assertFalse(result["StageState"] & 4)
        self.assertEqual(result["UserProgress"]["StageStates"][str(self.stage + 1)], 1)
        self.call("/stage/start-stage", branch)

    def test_stone_board_is_persistent_and_rewarded_once(self):
        body = {"StageId": self.stage, "StonePieceItemId": self.piece}
        for count in range(1, 4):
            result = self.call(api.STONE, body)
            self.assertEqual(base64.b64decode(self.account.stage_progress(self.stage))[-1], count)
            self.assertEqual(bool(result["AddedItems"]), count == 3)
        self.call(api.STONE, body, retry=True)
        self.assertEqual(self.call(api.STONE, body)["AddedItems"], [])
        misc = self.account.profile()["User"]["ItemMiscs"]
        self.assertEqual(sum(r["ItemId"] == 10018 for r in misc), 1)
        self.assertFalse(any(r["Id"] == self.piece for r in misc))

    def test_radar_follower_revives_and_new_stage_run(self):
        stage = {"StageId": self.stage}
        for _ in range(2):
            self.call(api.RADAR, {"id": self.stage})
            self.call(api.FOLLOWER, stage | {"FollowerId": 0})
        self.assertEqual(self.account.profile()["UserProgress"]["Followers"], [0])
        self.assertTrue(
            self.account.profile()["UserProgress"]["StageStates"][str(self.stage)] & api.RADAR_FLAG
        )
        self.assertEqual(self.balance(70003), 37)
        hero = self.account.profile()["User"]["Party"]["Characters"][0]
        self.call(api.PARTY, {"Index": 0, "CharacterId": hero})
        self.assertEqual(self.call(api.TIMER, stage), {})
        self.assertEqual(self.call(api.RANKINGS, stage), {"Rankings": []})
        self.call(api.REVIVE, stage)
        self.call(api.REVIVE, stage, retry=True)
        self.call(api.REVIVE, stage)
        with self.assertRaises(PacketError):
            self.call(api.REVIVE, stage)
        self.assertEqual(self.balance(70003), 25)
        self.call("/stage/start-stage", stage)
        self.call(api.REVIVE, stage)
        self.assertEqual(self.balance(70003), 20)
