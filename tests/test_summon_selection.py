# SPDX-License-Identifier: Apache-2.0
"""Wishlist choices persist without currency spending, summons or inventory grants."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet

FIXTURE = Path(__file__).parent / "fixtures/summon_selection_catalog.json"


class SummonSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "summon_selection_catalog.json"
        self.catalog_file.write_bytes(FIXTURE.read_bytes())
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
        profile = self.account.profile()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70003)["Amount"] = 1000400
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def call(self, route, body=None):
        packet = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, sequence_id=8, api=route)
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(packet))))

    def test_catalog_reads_match_checksums_and_refresh_after_catalog_changes(self):
        before = self.account.profile()
        entry = self.call("/summon/enter")
        catalog = self.call("/summon/on-event")
        self.assertEqual(entry["Checksum"], catalog["Checksum"])
        self.assertNotEqual(entry["Checksum"], "local-empty-v1")
        self.assertFalse(entry["IsActiveEvent"])
        self.assertIsNone(catalog["SelectableSummonEvent"])
        self.assertEqual(
            catalog["SelectableCharacter"], json.loads(FIXTURE.read_bytes())["characters"]
        )
        changed = json.loads(FIXTURE.read_bytes())
        changed["characters"][0]["IsNew"] = True
        self.catalog_file.write_text(json.dumps(changed))
        refreshed = self.call("/summon/enter")
        self.assertNotEqual(refreshed["Checksum"], entry["Checksum"])
        self.assertEqual(refreshed["Checksum"], self.call("/summon/on-event")["Checksum"])
        self.assertEqual(self.account.profile(), before)

    def test_selection_replacement_clear_and_retries_change_only_saved_wishlist(self):
        expected = self.account.profile()
        body = {"RequestOriginIds": [101, 102, 103, 104, 105]}
        response = self.call("/summon/set-select-character", body)
        expected["UserShop"]["SelectedSummonCharacters"] = body["RequestOriginIds"]
        expected["UserShop"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(response, {"UserShop": expected["UserShop"]})
        reopened = GuestStore(self.db, self.references).account
        self.assertEqual(reopened.read("/summon/set-select-character", body), response)
        self.assertEqual(reopened.profile(), expected)
        for selected in ([105, 104], []):
            reopened.read("/summon/set-select-character", {"RequestOriginIds": selected})
            expected["UserShop"]["SelectedSummonCharacters"] = selected
            expected["UserShop"]["Cas"] += 1
            self.assertEqual(reopened.profile(), expected)

    def test_invalid_sentinel_unknown_duplicate_and_unauthenticated_choices_cannot_mutate(self):
        before = self.account.profile()
        for body in (
            None,
            {},
            {"RequestOriginIds": [-1]},
            {"RequestOriginIds": [True]},
            {"RequestOriginIds": [999]},
            {"RequestOriginIds": [101, 101]},
            {"RequestOriginIds": [101, 102, 103, 104, 105, 106]},
            {"RequestOriginIds": [101], "Extra": 1},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call("/summon/set-select-character", body)
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.call("/summon/set-select-character", {"RequestOriginIds": [101]})
        self.assertEqual(self.account.profile(), before)

    def test_invalid_or_missing_catalog_is_rejected_before_selection_or_read(self):
        before = self.account.profile()
        for patch in (
            {"CharacterOriginId": True},
            {"Id": 2},
            {"CharacterOriginId": 102},
            {"SummonCategory": "Unknown"},
            {"SelectableFrom": "invalid"},
        ):
            changed = json.loads(FIXTURE.read_bytes())
            changed["characters"][0].update(patch)
            self.catalog_file.write_text(json.dumps(changed))
            for route, body in (
                ("/summon/enter", None),
                ("/summon/set-select-character", {"RequestOriginIds": [101]}),
            ):
                with self.assertRaises(PacketError):
                    self.call(route, body)
        self.catalog_file.unlink()
        with self.assertRaises(PacketError):
            self.call("/summon/set-select-character", {"RequestOriginIds": [101]})
        self.assertEqual(self.call("/summon/enter")["Checksum"], "local-empty-v1")
        self.assertEqual(self.account.profile(), before)

    def test_failed_wishlist_write_preserves_the_previous_profile(self):
        before = self.account.profile()
        self.db.execute(
            "CREATE TRIGGER reject_selection BEFORE UPDATE ON local_account "
            "BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.call("/summon/set-select-character", {"RequestOriginIds": [101]})
        self.assertEqual(self.account.profile(), before)
