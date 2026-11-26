# SPDX-License-Identifier: Apache-2.0
"""Synthetic milestones exercise atomic batches independently of game content."""

import base64
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet


class BeginnerBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "beginner_mission_catalog.json"
        self.ids = [5, 12, 64, 120, 201, 400, 511]
        self.catalog = {
            "missions": {
                str(m): {
                    "summon_count": i + 1,
                    "rewards": [
                        {
                            "item_id": 110007 if i == 0 else 110015,
                            "amount": 2 if i == 0 else 1,
                            "storage": "stackable",
                        }
                    ],
                }
                for i, m in enumerate(self.ids)
            }
        }
        self.catalog["missions"]["512"] = {
            "summon_count": 10,
            "rewards": [{"item_id": 70003, "amount": 17, "storage": "asset"}],
        }
        self.write_catalog()
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db, self.references)
        self.account = self.store.account
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
        p = self.account.profile()
        p["UserRecord"]["SummonCharacterCount"] = 7
        p["UserProgress"]["StageStates"]["100010001"] = 7
        p["User"]["ItemIdCounter"] = 42
        p["User"]["ItemStackables"] = [{"Id": 42, "ItemId": 110015, "Amount": 3}]
        self.save(p)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def write_catalog(self):
        self.catalog_file.write_text(json.dumps(self.catalog), encoding="utf-8")

    def save(self, profile):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()

    def claim(self, ids):
        return self.account.claim_beginner_missions({"missionIds": ids})

    def assert_unchanged(self, before, receipts=0):
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM beginner_mission_claims").fetchone(), (receipts,)
        )

    def test_seven_milestones_merge_stacks_preserve_profile_and_replay_after_restart(self):
        expected = self.account.profile()
        response = self.claim(self.ids + [self.ids[0]])
        expected["User"]["ItemStackables"][0]["Amount"] = 9
        expected["User"]["ItemStackables"].append(
            self.account.profile()["User"]["ItemStackables"][1]
        )
        self.assertEqual(expected["User"]["ItemStackables"][1]["Amount"], 2)
        expected["User"]["ItemIdCounter"] += 1
        expected["User"]["Cas"] += 1
        flags = bytearray(64)
        for mission_id in self.ids:
            flags[mission_id // 8] |= 1 << (mission_id % 8)
        expected["UserMission"]["GuideClaimed"] = base64.b64encode(flags).decode()
        expected["UserMission"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(len(response["AddedItems"]), 7)
        self.account = GuestStore(self.db, self.references).account
        self.assertEqual(self.claim(self.ids), response)
        self.assert_unchanged(expected, 7)

    def test_overlap_with_old_receipt_does_not_restore_consumed_rewards(self):
        first = self.claim([0])
        p = self.account.profile()
        p["User"]["ItemStackables"][0]["Amount"] = 1
        p["UserRecord"]["SummonCharacterCount"] = 10
        self.save(p)
        self.claim([0, 5, 512, 5])
        saved = self.account.profile()
        amounts = {i["ItemId"]: i["Amount"] for i in saved["User"]["ItemStackables"]}
        self.assertEqual(amounts, {110015: 1, 110007: 2})
        self.assertEqual(
            next(a["Amount"] for a in saved["User"]["Assets"] if a["Id"] == 70003), 317
        )
        response = self.claim([512, 0, 5])
        self.assertEqual(response["AddedItems"][1:4], first["AddedItems"])
        self.assert_unchanged(saved, 3)

    def test_ineligible_unknown_and_invalid_requests_cannot_partially_grant(self):
        before = self.account.profile()
        for ids in (self.ids + [512], [5, 999], [True], [], None, [[5]], [5] * 513):
            with self.subTest(ids=str(ids)[:50]), self.assertRaises(ValueError):
                self.claim(ids)
            self.assert_unchanged(before)
        before["UserRecord"]["SummonCharacterCount"] = 0
        self.save(before)
        with self.assertRaises(ValueError):
            self.claim([5])
        self.assert_unchanged(before)

    def test_invalid_catalogs_cannot_change_progress(self):
        original = copy.deepcopy(self.catalog)
        invalid = [[], {"missions": {}}, {"missions": {"0": original["missions"]["5"]}}]
        for field, value in (("summon_count", True), ("rewards", [])):
            bad = copy.deepcopy(original)
            bad["missions"]["5"][field] = value
            invalid.append(bad)
        for field, value in (("storage", "weapon"), ("amount", 0), ("item_id", True)):
            bad = copy.deepcopy(original)
            bad["missions"]["5"]["rewards"][0][field] = value
            invalid.append(bad)
        before = self.account.profile()
        for bad in invalid:
            self.catalog = bad
            self.write_catalog()
            with self.subTest(catalog=bad), self.assertRaises(ValueError):
                self.claim([5])
            self.assert_unchanged(before)

    def test_claim_bit_and_receipt_mismatch_reject_entire_batch(self):
        self.claim([5])
        self.db.execute("DELETE FROM beginner_mission_claims WHERE mission_id=5")
        self.db.commit()
        before = self.account.profile()
        with self.assertRaises(ValueError):
            self.claim([12, 5])
        self.assert_unchanged(before)

    def test_late_receipt_write_failure_rolls_back_all_rewards_and_flags(self):
        before = self.account.profile()
        self.db.execute(
            "CREATE TRIGGER reject_batch BEFORE INSERT ON beginner_mission_claims "
            "WHEN NEW.mission_id=511 BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.claim(self.ids)
        self.assert_unchanged(before)

    def test_late_overflow_cannot_save_earlier_rewards(self):
        before = self.account.profile()
        before["User"]["ItemStackables"][0]["Amount"] = 0x7FFFFFFF
        self.save(before)
        with self.assertRaises(ValueError):
            self.claim([5, 12])
        self.assert_unchanged(before)

    def test_authenticated_packet_batch_returns_user_mission_and_reward_notices(self):
        session = BootstrapSession(self.store)
        packet = parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps({"missionIds": self.ids}).encode(),
                    body_type=1,
                    sequence_id=8,
                    api="/mission/claim-beginner-all",
                )
            )
        )
        before = self.account.profile()
        with self.assertRaises(PacketError):
            session.handle(packet)
        self.assert_unchanged(before)
        session.signed_in = True
        result = read_json_body(parse_packet(encode_packet(session.handle(packet))))
        self.assertEqual(set(result), {"User", "UserMission", "AddedItems"})
        self.assertEqual(len(result["AddedItems"]), 7)
