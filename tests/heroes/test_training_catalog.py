# SPDX-License-Identifier: Apache-2.0
"""Training costs come from catalogs, while retries use request identities."""

import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, encode_packet
from tests import FIXTURES

REFERENCE_DIR = FIXTURES / "reference"


class CatalogTrainingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db, REFERENCE_DIR)
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
        self.profile = self.account.profile()
        self.profile["UserProgress"]["StageStates"]["100010001"] = 7
        next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 1000
        self.save()

    def tearDown(self):
        self.db.close()

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def train(self, changes, key):
        return self.account.add_character_experience({"Experiences": changes}, key)

    def packet(self, route, body, sequence):
        return parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )

    def test_arbitrary_catalog_costs_spend_once_and_survive_reopening(self):
        self.train({"1": 37}, "initial")
        response = self.train({"1": 63}, "second")
        expected = json.loads(json.dumps(self.profile))
        expected["User"]["Characters"][0]["Experience"] = 100
        next(a for a in expected["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 900
        expected["User"]["Cas"] += 2
        expected["UserRecord"]["AddCharacterExperienceAmount"] += 100
        expected["UserRecord"]["Cas"] += 2
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(self.train({"1": 63}, "second"), response)
        reopened = GuestStore(self.db, REFERENCE_DIR).account
        self.assertEqual(
            reopened.add_character_experience({"Experiences": {"1": 63}}, "second"), response
        )
        self.assertEqual(reopened.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT * FROM first_knight_training").fetchall(), [(1, 37)]
        )

    def test_same_cost_can_be_a_new_valid_request_and_old_retry_returns_current_state(self):
        self.train({"1": 100}, "first")
        second = self.train({"1": 100}, "second")
        self.assertEqual(second["User"]["Characters"][0]["Experience"], 200)
        self.assertEqual(self.train({"1": 100}, "first"), second)
        self.assertEqual(self.train({"1": 100}, "fresh-session-retry"), second)
        self.assertEqual(
            next(a for a in second["User"]["Assets"] if a["Id"] == 70004)["Amount"], 800
        )
        with self.assertRaises(ValueError):
            self.train({"1": 37}, "second")
        self.assertEqual(self.account.profile()["User"], second["User"])

    def test_batches_use_owned_characters_and_one_shared_balance_atomically(self):
        another = json.loads(json.dumps(self.profile["User"]["Characters"][0]))
        another["Id"] = 2
        self.profile["User"]["Characters"].append(another)
        self.save()
        for changes in ({"1": 37, "3": 37}, {"1": 37, "2": 550}):
            with self.assertRaises(ValueError):
                self.train(changes, "bad-batch")
            self.assertEqual(self.account.profile(), self.profile)
        response = self.train({"1": 100, "2": 37}, "batch")
        self.assertEqual([c["Experience"] for c in response["User"]["Characters"]], [100, 37])
        self.assertEqual(
            next(a for a in response["User"]["Assets"] if a["Id"] == 70004)["Amount"], 863
        )
        self.assertEqual(self.train({"2": 37, "1": 100}, "batch"), response)

    def test_story_cap_balance_and_malformed_inputs_preserve_profile(self):
        for changes in (
            {},
            {"1": True},
            {"1": 0},
            {"1": -1},
            {"01": 37},
            {"2": 37},
            {"1": 38},
            {"1": 350},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.train(changes, "bad")
        self.assertEqual(self.account.profile(), self.profile)
        self.profile["UserProgress"]["StageStates"]["100020001"] = 1
        self.save()
        self.train({"1": 550}, "larger-cap")
        self.assertEqual(self.account.profile()["User"]["Characters"][0]["Experience"], 550)
        saved = self.account.profile()
        with self.assertRaises(ValueError):
            self.train({"1": 250}, "over-cap")
        self.assertEqual(self.account.profile(), saved)
        self.profile = json.loads(json.dumps(self.profile))
        next(a for a in self.profile["User"]["Assets"] if a["Id"] == 70004)["Amount"] = 36
        self.save()
        with self.assertRaises(ValueError):
            self.train({"1": 37}, "unaffordable")
        self.assertEqual(self.account.profile(), self.profile)

    def test_invalid_catalog_and_advanced_character_are_rejected(self):
        for catalog in (
            [],
            {},
            {"experience_by_level": [0, True], "caps": []},
            {"experience_by_level": [0, 37, 20], "caps": [{"opened_stage_id": 0, "max_level": 2}]},
        ):
            with patch.object(self.account.references, "json", return_value=catalog):
                with self.assertRaises(ValueError):
                    self.train({"1": 37}, "bad-catalog")
        self.profile["User"]["Characters"][0]["LimitBreaks"] = 1
        self.save()
        with self.assertRaises(ValueError):
            self.train({"1": 37}, "advanced")
        self.assertEqual(self.account.profile(), self.profile)

    def test_profile_failure_rolls_back_request_receipt_and_tutorial_marker(self):
        self.db.execute(
            "CREATE TRIGGER reject_training BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.train({"1": 100}, "failed")
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_training_requests").fetchone(), (0,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM first_knight_training").fetchone(), (0,)
        )

    def test_reconnect_reuses_request_epoch_and_fresh_login_allows_sequence_reuse(self):
        first = BootstrapSession(self.store)
        signin = {"AuthKind": 0, "AccessToken": "test-only", "Reconnect": False}
        first.handle(self.packet("/auth/sign-in", signin, 1))
        epoch = first.request_epoch
        training = self.packet("/user/add-character-experience", {"Experiences": {"1": 100}}, 7)
        first.handle(training)
        resumed = BootstrapSession(GuestStore(self.db, REFERENCE_DIR))
        resumed.handle(self.packet("/auth/sign-in", {**signin, "Reconnect": True}, 2))
        self.assertEqual(resumed.request_epoch, epoch)
        resumed.handle(training)
        self.assertEqual(self.account.profile()["User"]["Characters"][0]["Experience"], 100)
        fresh = BootstrapSession(self.store)
        fresh.handle(self.packet("/auth/sign-in", signin, 1))
        self.assertNotEqual(fresh.request_epoch, epoch)
        response = read_json_body(parse_packet(encode_packet(fresh.handle(training))))
        self.assertEqual(response["User"]["Characters"][0]["Experience"], 200)

    def test_existing_tutorial_receipt_is_preserved_when_enabling_catalog_training(self):
        self.profile["User"]["Characters"][0]["Experience"] = 37
        self.profile["UserRecord"]["AddCharacterExperienceAmount"] = 37
        self.save()
        self.db.execute("INSERT INTO first_knight_training VALUES(1,37)")
        self.db.commit()
        self.train({"1": 37}, "legacy-retry")
        self.assertEqual(self.account.profile(), self.profile)
        self.train({"1": 63}, "next")
        self.assertEqual(self.account.profile()["User"]["Characters"][0]["Experience"], 100)
