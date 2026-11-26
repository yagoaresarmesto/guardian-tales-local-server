# SPDX-License-Identifier: Apache-2.0
"""Free imported training preserves balances, respects native caps and retries atomically."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import PacketError, encode_packet
from tests.account.test_snapshots import request


class ImportedTrainingTests(unittest.TestCase):
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
        self.profile["UserProgress"]["StageStates"]["100010001"] = 7
        hero = self.profile["User"]["Characters"][0]
        hero.update(CharacterId=31, LimitBreaks=1, BlessLevel=1)
        myth = copy.deepcopy(hero)
        myth.update(Id=2, CharacterId=33)
        self.profile["User"]["Characters"].append(myth)
        xp = next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70004)
        xp.update(Amount=0, Spent=123)
        self.save()
        self.catalog = {
            "client": dict(CLIENT),
            "free_experience": True,
            "experience_by_level": [v * 100 for v in range(15)],
            "caps": [
                {"opened_stage_id": 0, "max_level": 2},
                {"opened_stage_id": 100020001, "max_level": 4},
            ],
            "limit_break_coefficient": 3,
            "blessing_coefficient": 2,
            "myth_coefficient": 4,
            "max_limit_breaks": 1,
            "max_bless_level": 1,
            "character_ids": [1, 31, 33],
            "myth_ids": [33],
        }
        self.write_catalog()

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def write_catalog(self):
        (self.root / "imported_training_catalog.json").write_text(json.dumps(self.catalog))

    def train(self, changes, key="request"):
        return self.account.add_character_experience({"Experiences": changes}, key)

    def test_non_knights_blessed_and_myth_heroes_gain_xp_without_any_asset_cost(self):
        result = self.train({"1": 700, "2": 1100})
        expected = copy.deepcopy(self.profile)
        expected["User"]["Characters"][0]["Experience"] = 700
        expected["User"]["Characters"][1]["Experience"] = 1100
        expected["User"]["Cas"] += 1
        expected["UserRecord"]["AddCharacterExperienceAmount"] += 1800
        expected["UserRecord"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(result, {k: expected[k] for k in ("User", "UserRecord")})
        for key in ("1", "2"):
            with self.assertRaises(ValueError):
                self.train({key: 1}, "above-cap")
        self.assertEqual(self.account.profile(), expected)

    def test_story_unlock_partial_training_and_plain_heroes_use_native_threshold_index(self):
        self.profile["User"]["Characters"][0].update(LimitBreaks=0, BlessLevel=0)
        self.save()
        self.train({"1": 199})
        self.train({"1": 1}, "cap")
        with self.assertRaises(ValueError):
            self.train({"1": 1}, "blocked")
        self.profile = self.account.profile()
        self.profile["UserProgress"]["StageStates"]["100020001"] = 1
        self.save()
        self.train({"1": 200}, "opened")
        self.assertEqual(self.account.profile()["User"]["Characters"][0]["Experience"], 400)

    def test_reconnect_reopen_current_state_retry_and_same_delta_with_new_identity(self):
        first = BootstrapSession(self.store)
        signin = {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False}
        first.handle(request("/auth/sign-in", signin))
        packet = request("/user/add-character-experience", {"Experiences": {"1": 100}})
        first.handle(packet)
        reopened = GuestStore(self.db, self.root)
        resumed = BootstrapSession(reopened)
        resumed.handle(request("/auth/sign-in", {**signin, "Reconnect": True}))
        resumed.handle(packet)
        self.assertEqual(self.account.profile()["User"]["Characters"][0]["Experience"], 100)
        self.train({"1": 100}, "new-id")
        current = self.account.profile()
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(resumed.handle(packet))))["User"],
            current["User"],
        )
        self.assertEqual(current["User"]["Characters"][0]["Experience"], 200)
        with self.assertRaises(PacketError):
            resumed.handle(request("/user/add-character-experience", {"Experiences": {"1": 200}}))
        self.assertEqual(self.account.profile(), current)

    def test_lifetime_xp_crossing_int32_is_safe_on_training_retry_and_login(self):
        limit = 2**31 - 1
        self.profile["UserRecord"]["AddCharacterExperienceAmount"] = limit - 100
        self.save()
        session = BootstrapSession(self.store)
        signin = {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False}
        session.handle(request("/auth/sign-in", signin))
        for sequence, (delta, gained) in enumerate(((99, 99), (1, 100), (100, 200)), 51):
            packet = request("/user/add-character-experience", {"Experiences": {"1": delta}})
            packet["sequence_id"] = sequence
            reply = json.loads(session.handle(packet).body)
            total = limit - 100 + gained
            saved = self.account.profile()
            self.assertEqual(saved["User"]["Characters"][0]["Experience"], gained)
            self.assertEqual(saved["UserRecord"]["AddCharacterExperienceAmount"], total)
            self.assertEqual(
                reply["UserRecord"],
                {**saved["UserRecord"], "AddCharacterExperienceAmount": min(total, limit)},
            )
            self.assertEqual(reply["User"], saved["User"])

        reopened = BootstrapSession(GuestStore(self.db, self.root))
        reopened.handle(request("/auth/sign-in", {**signin, "Reconnect": True}))
        self.assertEqual(json.loads(reopened.handle(packet).body), reply)
        fetched = json.loads(reopened.handle(request("/auth/fetch-account")).body)
        self.assertEqual(fetched, {**saved, "UserRecord": reply["UserRecord"]})
        self.assertEqual(self.account.profile(), saved)

    def test_invalid_requests_unowned_heroes_and_batch_overcap_make_no_changes(self):
        for changes in (
            {},
            {"1": True},
            {"1": 0},
            {"1": -1},
            {"01": 100},
            {"2147483648": 100},
            {"1": 0x80000000},
            {"1": 100, "9": 100},
            {"1": 100, "2": 1101},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.train(changes)
            self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM imported_character_training_requests").fetchone(),
            (0,),
        )

    def test_missing_mismatched_and_malformed_policy_cannot_enable_imported_training(self):
        original = copy.deepcopy(self.catalog)
        for field, value in (
            ("client", {**CLIENT, "version_code": True}),
            ("free_experience", False),
            ("experience_by_level", [0, 10, 9]),
            ("max_limit_breaks", True),
            ("myth_ids", [99]),
            ("caps", [{"opened_stage_id": 0, "max_level": 99}]),
        ):
            self.catalog = {**original, field: value}
            self.write_catalog()
            with self.assertRaises(ValueError):
                self.train({"1": 100})
        (self.root / "imported_training_catalog.json").unlink()
        with self.assertRaises(ValueError):
            self.train({"1": 100})
        self.assertEqual(self.account.profile(), self.profile)

    def test_invalid_saved_modifiers_revisions_and_counter_overflow_are_rejected(self):
        for section, field, value in (
            ("hero", "LimitBreaks", 2),
            ("hero", "BlessLevel", -1),
            ("hero", "Experience", True),
            ("hero", "CharacterId", 99),
            ("User", "Cas", 0x7FFFFFFFFFFFFFFF),
            ("UserRecord", "AddCharacterExperienceAmount", 0x7FFFFFFFFFFFFFFF),
        ):
            self.profile = copy.deepcopy(self.account.profile())
            target = (
                self.profile["User"]["Characters"][0]
                if section == "hero"
                else self.profile[section]
            )
            old = target[field]
            target[field] = value
            self.save()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.train({"1": 100})
            self.assertEqual(self.account.profile(), self.profile)
            target[field] = old
            self.save()

    def test_profile_failure_rolls_back_training_receipt(self):
        self.db.execute(
            "CREATE TRIGGER reject_training BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.train({"1": 100, "2": 100})
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM imported_character_training_requests").fetchone(),
            (0,),
        )
