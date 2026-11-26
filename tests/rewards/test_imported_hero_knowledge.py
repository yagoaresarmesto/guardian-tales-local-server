# SPDX-License-Identifier: Apache-2.0
"""Imported hero-book progress follows native thresholds without repaying official flags."""

import base64
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.characters import new_character
from guardian_tales.imported_hero_knowledge import opened_nodes
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import PacketError, encode_packet
from guardian_tales.snapshots import CLIENT
from tests.account.test_snapshots import request

TABLES = (
    "imported_hero_knowledge_baselines",
    "imported_hero_knowledge_claims",
    "imported_hero_knowledge_requests",
)


def tree(data):
    return "AQAAAA==|" + base64.b64encode(data).decode()


class ImportedHeroKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db, self.root)
        self.account = self.store.account
        self.account.complete_prologue(
            "Synthetic",
            {
                "IsMale": True,
                "VoiceType": 0,
                "Weapon1ItemId": 101,
                "Weapon2ItemId": 102,
                "BobLindaQuestGrade": 0,
            },
        )
        self.db.execute(
            "INSERT INTO imported_account VALUES(1,?,?,?,?)", ("0" * 64, "synthetic", "{}", "{}")
        )
        self.profile = self.account.profile()
        self.profile["User"]["Characters"] = [new_character(1, 101), new_character(2, 201)]
        self.save()
        objectives = [
            (1, "Get", 0),
            (2, "Evolve", 2),
            (3, "Evolve", 4),
            (4, "LevelUp", 3),
            (5, "LimitBreak", 5),
            (6, "AwakeningSkill", 3),
            (8, "Ascend", 5),
            (9, "Blessing", 3),
            (10, "Myth", 6),
        ]
        self.catalog = {
            "client": dict(CLIENT),
            "experience_by_level": [0, 37, 111, 222, 370],
            "heroes": {
                "101": {"origin_id": 100, "rank": 1},
                "102": {"origin_id": 100, "rank": 4},
                "103": {"origin_id": 100, "rank": 5},
                "104": {"origin_id": 100, "rank": 6},
                "201": {"origin_id": 200, "rank": 1},
            },
            "origins": {
                "100": {
                    "nodes": [0, 2, 9],
                    "objectives": [
                        {
                            "id": 10000 + seq,
                            "type": kind,
                            "value": value,
                            "rewards": [{"item_id": 70003, "amount": seq}],
                        }
                        for seq, kind, value in objectives
                    ],
                },
                "200": {
                    "nodes": [0],
                    "objectives": [{"id": 20001, "type": "Get", "value": 0, "rewards": []}],
                },
            },
        }
        self.catalog_file = self.root / "imported_hero_knowledge_catalog.json"
        self.write_catalog()

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def write_catalog(self):
        self.catalog_file.write_text(json.dumps(self.catalog))

    def claim(self, ids=None, key="claim"):
        return self.account.claim_hero_knowledge({"CharacterIds": [1] if ids is None else ids}, key)

    def counts(self):
        return tuple(self.db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES)

    def state(self):
        return self.account.profile(), self.counts()

    def gem(self, profile):
        return next(a for a in profile["User"]["Assets"] if a["Id"] == 70003)

    def test_all_eight_types_use_saved_progress_and_leave_every_other_field_unchanged(self):
        hero = self.profile["User"]["Characters"][0]
        hero.update(
            CharacterId=104,
            Experience=222,
            LimitBreaks=5,
            BlessLevel=3,
            AwakeningTree=tree(b"\x05\x02"),
            Knowledge=1 << 20,
        )
        self.save()
        expected = copy.deepcopy(self.profile)
        expected["User"]["Characters"][0]["Knowledge"] |= 0b1110111111
        expected["User"]["Characters"][1]["Knowledge"] = 1
        expected["User"]["Cas"] += 1
        self.gem(expected)["Amount"] += 48
        result = self.claim([2, 1, 1])
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(result["User"], expected["User"])
        self.assertEqual(sum(r["Amount"] for r in result["AddedItems"]), 48)
        self.assertEqual(self.counts(), (2, 10, 1))

    def test_native_xp_index_and_raw_evolution_thresholds_collect_new_progress(self):
        self.claim()
        self.profile = self.account.profile()
        self.profile["User"]["Characters"][0].update(CharacterId=102, Experience=221)
        self.save()
        self.assertEqual([r["Amount"] for r in self.claim(key="evolved")["AddedItems"]], [2, 3])
        self.profile = self.account.profile()
        self.profile["User"]["Characters"][0]["Experience"] = 222
        self.save()
        self.assertEqual([r["Amount"] for r in self.claim(key="level")["AddedItems"]], [4])
        self.assertEqual(self.counts(), (1, 4, 3))

    def test_ascension_and_myth_use_boolean_native_values(self):
        self.profile["User"]["Characters"][0]["CharacterId"] = 103
        self.save()
        result = self.claim()
        self.assertEqual([r["Amount"] for r in result["AddedItems"]], [1, 2, 3, 8])
        self.profile = self.account.profile()
        self.profile["User"]["Characters"][0]["CharacterId"] = 104
        self.save()
        self.assertEqual([r["Amount"] for r in self.claim(key="myth")["AddedItems"]], [10])

    def test_awakening_counts_only_configured_bits_and_ignores_encoded_old_spec(self):
        self.assertEqual(opened_nodes("", [0, 2, 9]), 0)
        self.assertEqual(opened_nodes(None, [0, 2, 9]), 0)
        self.assertEqual(opened_nodes(tree(b"\xff"), [0, 2, 9]), 2)
        self.assertEqual(opened_nodes(tree(b"\x05\xfe\xff"), [0, 2, 9]), 3)
        self.profile["User"]["Characters"][0]["AwakeningTree"] = tree(b"\xff")
        self.save()
        self.assertEqual([r["Amount"] for r in self.claim()["AddedItems"]], [1])
        self.profile = self.account.profile()
        self.profile["User"]["Characters"][0]["AwakeningTree"] = tree(b"\x05\x02")
        self.save()
        self.assertEqual([r["Amount"] for r in self.claim(key="nodes")["AddedItems"]], [6])
        for bad in (True, 1, "x", "AQ==|AAAA", "AQAAAA==|!", "AQAAAA==|AA==|AA=="):
            with self.subTest(tree=bad), self.assertRaises(ValueError):
                opened_nodes(bad, [0])

    def test_official_flags_are_nonpaying_even_if_current_state_is_below_objective(self):
        self.profile["User"]["Characters"][0]["Knowledge"] = (1 << 20) | (1 << 8) | 1
        self.save()
        expected = copy.deepcopy(self.profile)
        self.assertEqual(self.claim()["AddedItems"], [])
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(self.counts(), (1, 0, 1))
        writes = self.db.total_changes
        self.claim()
        self.assertEqual(self.db.total_changes, writes)
        self.claim(key="noop")
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(self.counts(), (1, 0, 2))

    def test_retry_after_reopen_catalog_removal_and_spending_returns_current_profile(self):
        original = self.claim()
        self.profile = self.account.profile()
        self.gem(self.profile)["Amount"] -= 1
        self.profile["User"]["Characters"][0]["Experience"] = 222
        self.save()
        self.account = GuestStore(self.db, self.root).account
        self.catalog_file.unlink()
        writes = self.db.total_changes
        result = self.claim([1, 1])
        self.assertEqual(result["AddedItems"], original["AddedItems"])
        self.assertEqual(result["User"], self.profile["User"])
        self.assertEqual(writes, self.db.total_changes)
        with self.assertRaises(ValueError):
            self.claim([2])

    def test_missing_baseline_receipt_or_reset_flags_cannot_silently_rebase(self):
        self.claim()
        saved = self.account.profile()
        for sql in (
            "DELETE FROM imported_hero_knowledge_baselines",
            "DELETE FROM imported_hero_knowledge_claims",
            "UPDATE imported_hero_knowledge_baselines SET character_id=2",
        ):
            self.db.execute("SAVEPOINT corrupt")
            self.db.execute(sql)
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                self.claim(key="new")
            self.assertEqual(self.account.profile(), saved)
            self.db.execute("ROLLBACK TO corrupt")
            self.db.execute("RELEASE corrupt")
        self.profile = copy.deepcopy(saved)
        self.profile["User"]["Characters"][0]["Knowledge"] = 0
        self.save()
        before = self.state()
        with self.assertRaises(ValueError):
            self.claim(key="reset")
        self.assertEqual(self.state(), before)

    def test_malformed_or_unowned_batches_are_atomic_and_duplicate_origins_are_rejected(self):
        before = self.state()
        for ids in ([], [True], [0], [1, 99], [101], [1] * 513):
            with self.subTest(ids=str(ids)[:30]), self.assertRaises(ValueError):
                self.claim(ids)
            self.assertEqual(self.state(), before)
        for body, key in (
            ({}, "x"),
            ({"CharacterIds": None}, "x"),
            ({"CharacterIds": [1], "Extra": 1}, "x"),
            ({"CharacterIds": [1]}, ""),
            ({"CharacterIds": [1]}, None),
        ):
            with self.assertRaises(ValueError):
                self.account.claim_hero_knowledge(body, key)
            self.assertEqual(self.state(), before)
        self.profile["User"]["Characters"][1]["CharacterId"] = 102
        self.save()
        before = self.state()
        with self.assertRaises(ValueError):
            self.claim([1])
        self.assertEqual(self.state(), before)

    def test_missing_or_malformed_catalog_cannot_mark_or_reward(self):
        original = copy.deepcopy(self.catalog)
        before = self.state()
        self.catalog_file.unlink()
        with self.assertRaises(ValueError):
            self.claim()
        for mutate in (
            lambda c: c.update(client={}),
            lambda c: c.update(experience_by_level=[0, 0]),
            lambda c: c["heroes"]["101"].update(rank=True),
            lambda c: c["origins"]["100"].update(nodes=[0, 0]),
            lambda c: c["origins"]["100"]["objectives"][0].update(type="Unknown"),
            lambda c: c["origins"]["100"]["objectives"][0].update(id=10032),
            lambda c: c["origins"]["100"]["objectives"][0].update(
                rewards=[{"item_id": 70004, "amount": 1}]
            ),
            lambda c: c["origins"]["100"]["objectives"][1].update(id=10001),
            lambda c: c["origins"]["100"]["objectives"][6].update(value=6),
        ):
            self.catalog = copy.deepcopy(original)
            mutate(self.catalog)
            self.write_catalog()
            with self.assertRaises(ValueError):
                self.claim()
            self.assertEqual(self.state(), before)

    def test_invalid_saved_numbers_trees_balance_and_revision_reject_whole_batch(self):
        original = copy.deepcopy(self.profile)
        for field, value in (
            ("Experience", True),
            ("LimitBreaks", -1),
            ("BlessLevel", None),
            ("Knowledge", 1 << 31),
            ("AwakeningTree", "malformed"),
        ):
            self.profile = copy.deepcopy(original)
            self.profile["User"]["Characters"][0][field] = value
            self.save()
            before = self.state()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.claim([2, 1])
            self.assertEqual(self.state(), before)
        for mutate in (
            lambda p: self.gem(p).update(Amount=0x7FFFFFFF),
            lambda p: p["User"].update(Cas=0x7FFFFFFFFFFFFFFF),
            lambda p: p["User"]["Assets"].append(copy.deepcopy(self.gem(p))),
            lambda p: p["User"].update(Assets=[a for a in p["User"]["Assets"] if a["Id"] != 70003]),
        ):
            self.profile = copy.deepcopy(original)
            mutate(self.profile)
            self.save()
            before = self.state()
            with self.assertRaises(ValueError):
                self.claim([2, 1])
            self.assertEqual(self.state(), before)

    def test_late_claim_baseline_request_and_profile_failures_roll_back_everything(self):
        before = self.state()
        for table, action, condition in (
            (TABLES[0], "INSERT", "WHEN NEW.character_id=2"),
            (TABLES[1], "INSERT", "WHEN NEW.character_id=2"),
            (TABLES[2], "INSERT", ""),
            ("local_account", "UPDATE", ""),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_knowledge BEFORE {action} ON {table} {condition} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.claim([1, 2])
            self.assertEqual(self.state(), before)
            self.db.execute("DROP TRIGGER reject_knowledge")
            self.db.commit()

    def test_imported_packet_authentication_and_reconnect_receipt(self):
        route = "/collection/claim-hero-knowledge-all"
        packet = request(route, {"CharacterIds": [1, 2]})
        first = BootstrapSession(self.store)
        with self.assertRaises(PacketError):
            first.handle(packet)
        signin = {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False}
        first.handle(request("/auth/sign-in", signin))
        response = read_json_body(parse_packet(encode_packet(first.handle(packet))))
        before = self.state()
        resumed = BootstrapSession(GuestStore(self.db, self.root))
        resumed.handle(request("/auth/sign-in", {**signin, "Reconnect": True}))
        writes = self.db.total_changes
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(resumed.handle(packet)))), response
        )
        self.assertEqual(self.state(), before)
        self.assertEqual(writes, self.db.total_changes)

    def test_unrequested_heroes_and_unmet_objectives_remain_unclaimed(self):
        before = copy.deepcopy(self.profile)
        result = self.claim([2])
        expected = copy.deepcopy(before)
        expected["User"]["Characters"][1]["Knowledge"] = 1
        expected["User"]["Cas"] += 1
        self.assertEqual(result, {"User": expected["User"], "AddedItems": []})
        self.assertEqual(self.account.profile(), expected)
        result = self.claim([1], "one")
        self.assertEqual([r["Amount"] for r in result["AddedItems"]], [1])
        self.assertEqual(self.account.profile()["User"]["Characters"][0]["Knowledge"], 1)
