# SPDX-License-Identifier: Apache-2.0
"""Discovering a map changes only its target's opened flag, once."""

import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from tests import FIXTURES

REFERENCE_DIR = FIXTURES / "reference"


class SubstageDiscoveryTests(unittest.TestCase):
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
        self.profile["UserProgress"]["StageStates"] = {"100010001": 7, "110010005": 2}
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.execute("INSERT INTO campaign_session VALUES(1,100010001)")
        self.db.commit()
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True
        self.body = {"StageId": 100010001, "handleName": "test_map"}

    def tearDown(self):
        self.db.close()

    def interact(self, body):
        packet = parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps(body).encode(),
                    body_type=1,
                    api="/stage/interact-substage-item",
                    sequence_id=8,
                )
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(packet))))

    def test_opened_flag_persists_without_spending_unlocking_or_clearing(self):
        response = self.interact(self.body)
        expected = json.loads(json.dumps(self.profile))
        expected["UserProgress"]["StageStates"]["110010005"] = 3
        expected["UserProgress"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(response, {"UserProgress": expected["UserProgress"]})
        self.assertEqual(self.interact(self.body), response)
        self.assertEqual(
            GuestStore(self.db, REFERENCE_DIR).account.interact_substage_item(self.body), response
        )
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT stage_id FROM campaign_session").fetchall(), [(100010001,)]
        )

    def test_authentication_active_stage_and_exact_catalog_handle_are_required(self):
        for body in (
            None,
            {},
            self.body | {"StageId": True},
            self.body | {"StageId": 110010005},
            self.body | {"handleName": "unknown"},
            self.body | {"StageCustom": None},
        ):
            with self.assertRaises(PacketError):
                self.interact(body)
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.interact(self.body)
        self.session.signed_in = True
        self.db.execute("DELETE FROM campaign_session")
        self.db.commit()
        with self.assertRaises(PacketError):
            self.interact(self.body)
        self.assertEqual(self.account.profile(), self.profile)

    def test_invalid_catalog_and_write_failure_cannot_reveal_a_stage(self):
        for catalog in (
            {},
            {"stages": {"100010001": {"test_map": True}}},
            {"stages": {"100010001": {"test_map": 100010001}}},
        ):
            with patch.object(self.account.references, "json", return_value=catalog):
                with self.assertRaises(PacketError):
                    self.interact(self.body)
        self.db.execute(
            "CREATE TRIGGER reject_map BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.interact(self.body)
        self.assertEqual(self.account.profile(), self.profile)
