# SPDX-License-Identifier: Apache-2.0
"""Initial hero knowledge uses inventory IDs and persistent acquisition/request receipts."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.characters import new_character
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet
from tests import FIXTURES

FIXTURE = FIXTURES / "hero_knowledge_catalog.json"


class HeroKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "hero_knowledge_catalog.json"
        self.catalog_file.write_bytes(FIXTURE.read_bytes())
        self.db_file = self.references / "test-account.sqlite3"
        self.db = sqlite3.connect(self.db_file)
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
        p["User"]["Characters"].extend(new_character(i, 99 + i) for i in range(2, 5))
        p["User"]["CharacterIdCounter"] = 4
        self.asset(p, 70003)["Amount"] = 500
        self.asset(p, 70004)["Amount"] = 100
        self.save(p)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def asset(self, profile, item_id):
        return next(a for a in profile["User"]["Assets"] if a["Id"] == item_id)

    def save(self, p):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
        self.db.commit()

    def claim(self, ids=None, operation="knowledge-1"):
        return self.account.claim_hero_knowledge(
            {"CharacterIds": [2, 3, 4] if ids is None else ids}, operation
        )

    def assert_unchanged(self, p, heroes=0, batches=0):
        self.assertEqual(self.account.profile(), p)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM hero_knowledge_claims").fetchone(), (heroes,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM hero_knowledge_requests").fetchone(), (batches,)
        )

    def packet(self, route, body, seq=14):
        return parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps(body).encode(),
                    body_type=1,
                    api=route,
                    sequence_id=seq,
                )
            )
        )

    def test_batch_marks_acquisition_and_preserves_unrelated_bits_and_profile(self):
        expected = self.account.profile()
        expected["User"]["Characters"][1]["Knowledge"] = 64
        self.save(expected)
        for character in expected["User"]["Characters"][1:]:
            character["Knowledge"] |= 1
        self.asset(expected, 70003)["Amount"] += 5
        self.asset(expected, 70004)["Amount"] += 7
        expected["User"]["Cas"] += 1
        response = self.claim([2, 3, 4, 2])
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            response,
            {
                "User": expected["User"],
                "AddedItems": [
                    {"Id": 0, "ItemId": 70003, "Amount": 5},
                    {"Id": 0, "ItemId": 70004, "Amount": 7},
                ],
            },
        )
        self.assert_unchanged(expected, 3, 1)

    def test_acquisition_without_currency_reward_still_persists_knowledge(self):
        p = self.account.profile()
        response = self.claim([3])
        p["User"]["Characters"][2]["Knowledge"] = 1
        p["User"]["Cas"] += 1
        self.assertEqual(response["AddedItems"], [])
        self.assert_unchanged(p, 1, 1)

    def test_mixed_claimed_and_new_heroes_do_not_restore_spent_rewards(self):
        self.claim([2])
        p = self.account.profile()
        self.asset(p, 70003)["Amount"] -= 2
        self.save(p)
        response = self.claim([2, 3, 4], "mixed")
        self.assertEqual(response["AddedItems"], [{"Id": 0, "ItemId": 70004, "Amount": 7}])
        saved = self.account.profile()
        self.assertEqual(self.asset(saved, 70003)["Amount"], 503)
        self.assertEqual(self.claim([4, 3, 2, 2], "mixed"), response)
        self.assert_unchanged(saved, 3, 2)

    def test_receipt_survives_reopening_catalog_removal_and_later_progress(self):
        original = self.claim()
        p = self.account.profile()
        self.asset(p, 70003)["Amount"] -= 1
        p["User"]["Characters"][1]["Experience"] = 1
        self.save(p)
        self.db.close()
        self.db = sqlite3.connect(self.db_file)
        self.account = GuestStore(self.db, self.references).account
        self.catalog_file.unlink()
        retry = self.claim([4, 2, 3])
        self.assertEqual(retry["AddedItems"], original["AddedItems"])
        self.assertEqual(retry["User"], p["User"])
        self.assert_unchanged(p, 3, 1)

    def test_unknown_inventory_spec_ids_and_malformed_requests_are_atomic(self):
        p = self.account.profile()
        for ids in ([2, 999], [101], [1], [], None, [True], [[2]], [2] * 513):
            with self.subTest(ids=str(ids)[:40]), self.assertRaises(ValueError):
                self.account.claim_hero_knowledge({"CharacterIds": ids}, "bad")
            self.assert_unchanged(p)
        for body in (None, {}, {"CharacterIds": [2], "Extra": 1}):
            with self.assertRaises(ValueError):
                self.account.claim_hero_knowledge(body, "bad")
            self.assert_unchanged(p)
        p["User"]["Characters"][2]["CharacterId"] = 101
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim([2, 3])
        self.assert_unchanged(p)

    def test_advanced_progression_is_rejected_without_marking_other_objectives_complete(self):
        original = self.account.profile()
        for key, value in (
            ("Experience", 1),
            ("LimitBreaks", 1),
            ("RankUpgrade", 1),
            ("BlessLevel", 1),
            ("AwakeningTree", "unhandled"),
        ):
            p = copy.deepcopy(original)
            p["User"]["Characters"][2][key] = value
            self.save(p)
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.claim()
            self.assert_unchanged(p)

    def test_missing_or_invalid_catalog_cannot_grant(self):
        p = self.account.profile()
        original = json.loads(FIXTURE.read_text())
        invalid = [[], {}, {"heroes": {}}]
        for field, value in (
            ("knowledge_id", 10102),
            ("knowledge_id", True),
            ("origin_id", 999),
            ("rewards", [{"item_id": 70003, "amount": -1}]),
        ):
            bad = copy.deepcopy(original)
            bad["heroes"]["101"][field] = value
            invalid.append(bad)
        self.catalog_file.unlink()
        with self.assertRaises(ValueError):
            self.claim()
        for bad in invalid:
            self.catalog_file.write_text(json.dumps(bad))
            with self.subTest(catalog=bad), self.assertRaises(ValueError):
                self.claim()
            self.assert_unchanged(p)

    def test_acquisition_bit_and_receipt_mismatch_rejects_whole_batch(self):
        p = self.account.profile()
        p["User"]["Characters"][1]["Knowledge"] = 1
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p)
        p["User"]["Characters"][1]["Knowledge"] = 0
        self.save(p)
        self.claim([2])
        p = self.account.profile()
        p["User"]["Characters"][1]["Knowledge"] = 0
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p, 1, 1)

    def test_late_overflow_or_missing_reward_asset_cannot_save_earlier_heroes(self):
        p = self.account.profile()
        self.asset(p, 70004)["Amount"] = 0x7FFFFFFF
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p)
        p["User"]["Assets"] = [a for a in p["User"]["Assets"] if a["Id"] != 70004]
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p)

    def test_late_hero_request_or_profile_write_failure_rolls_back_every_marker(self):
        p = self.account.profile()
        for table, action, condition in (
            ("hero_knowledge_claims", "INSERT", "WHEN NEW.character_id=3"),
            ("hero_knowledge_requests", "INSERT", ""),
            ("local_account", "UPDATE", ""),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_knowledge BEFORE {action} ON {table} {condition} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.claim()
            self.assert_unchanged(p)
            self.db.execute("DROP TRIGGER reject_knowledge")
            self.db.commit()

    def test_authenticated_packet_reconnect_and_fresh_login_preserve_earned_markers(self):
        route = "/collection/claim-hero-knowledge-all"
        request = self.packet(route, {"CharacterIds": [2]})
        session = BootstrapSession(self.store)
        with self.assertRaises(PacketError):
            session.handle(request)
        signin = {"AuthKind": 0, "AccessToken": "synthetic-local", "Reconnect": False}
        session.handle(self.packet("/auth/sign-in", signin, 1))
        first = read_json_body(parse_packet(encode_packet(session.handle(request))))
        p = self.account.profile()
        reconnect = BootstrapSession(self.store)
        reconnect.handle(self.packet("/auth/sign-in", {**signin, "Reconnect": True}, 15))
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(reconnect.handle(request)))), first
        )
        self.assert_unchanged(p, 1, 1)
        reconnect.handle(self.packet("/auth/sign-in", signin, 1))
        response = read_json_body(
            parse_packet(
                encode_packet(reconnect.handle(self.packet(route, {"CharacterIds": [2, 4]})))
            )
        )
        self.assertEqual(response["AddedItems"], [{"Id": 0, "ItemId": 70004, "Amount": 7}])
        self.assert_unchanged(self.account.profile(), 2, 2)

    def test_existing_request_cannot_change_characters_or_omit_identity(self):
        self.claim([2])
        p = self.account.profile()
        for ids, operation in (([3], "knowledge-1"), ([2], None), ([2], "")):
            with self.assertRaises(ValueError):
                self.claim(ids, operation)
            self.assert_unchanged(p, 1, 1)

    def test_unfinished_prologue_cannot_claim_knowledge(self):
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.references).account
            before = account.profile()
            with self.assertRaises(ValueError):
                account.claim_hero_knowledge({"CharacterIds": [2]}, "too-early")
            self.assertEqual(account.profile(), before)
