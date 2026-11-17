# SPDX-License-Identifier: Apache-2.0
"""Deleting saved Orbital definitions is atomic and survives imported reads."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.presets import GEAR_FIELDS, MAX_REVISION, current_group
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.snapshots import CLIENT, import_snapshot, preserved_read
from tests.test_snapshots import synthetic_snapshot

ROUTE = "/preset/delete-preset"


class PresetDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.references = self.root / "references"
        self.references.mkdir()
        (self.references / "orbital_entry_catalog.json").write_text(
            json.dumps({"client": CLIENT, "floors": [1]})
        )
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["SelectedPresetId"] = {"InfiniteTower": 401, "Rift": 101}
        self.initial_group = {
            "Cas": 7,
            "Presets": [
                {
                    "Id": ident,
                    "Name": "Synthetic team",
                    "Order": order,
                    "Characters": [{"Id": 1, **dict.fromkeys(GEAR_FIELDS)}],
                }
                for order, ident in enumerate((101, 401, 402))
            ],
        }
        snapshot["startup_reads"]["/preset/get-presets"]["value"][
            "UserPartyPreset2"
        ] = self.initial_group
        self.source = self.root / "synthetic.json"
        self.source.write_text(json.dumps(snapshot))
        self.state = self.root / "state"
        import_snapshot(self.source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db, self.references)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            "/auth/sign-in",
            1,
        )

    def call(self, body, route=ROUTE, sequence=41):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(request))))

    def reject_without_writes(self, body, route=ROUTE):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_nonselected_delete_preserves_profile_other_presets_and_captured_seed(self):
        profile = self.store.account.profile()
        raw_profile = self.db.execute("SELECT profile FROM local_account").fetchone()[0]
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        source = self.source.read_bytes()
        before_read = preserved_read(self.db, "/preset/get-presets")
        response = self.call({"PresetId": 402})
        expected = copy.deepcopy(self.initial_group)
        expected["Cas"] += 1
        expected["Presets"].pop()
        self.assertEqual(response, {"UserPartyPreset2": expected, "User": profile["User"]})
        self.assertEqual(current_group(self.db), expected)
        self.assertEqual(
            preserved_read(self.db, "/preset/get-presets"),
            dict(before_read, UserPartyPreset2=expected),
        )
        self.assertEqual(
            self.db.execute("SELECT profile FROM local_account").fetchone()[0], raw_profile
        )
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM preset_delete_requests").fetchone()[0], 1
        )

    def test_selected_delete_clears_only_orbital_choice_and_increments_revisions_once(self):
        profile = self.store.account.profile()
        expected = copy.deepcopy(profile)
        expected["User"]["SelectedPresetId"]["InfiniteTower"] = 0
        expected["User"]["Cas"] += 1
        response = self.call({"PresetId": 401})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(response["User"], expected["User"])
        self.assertEqual(current_group(self.db)["Cas"], 8)
        self.assertEqual([p["Id"] for p in current_group(self.db)["Presets"]], [101, 402])

    def test_deleted_definition_cannot_be_selected_edited_or_entered(self):
        old = copy.deepcopy(self.initial_group["Presets"][2])
        self.call({"PresetId": 402})
        for route, body in (
            ("/preset/set-selected-preset", {"PresetId": 402}),
            ("/preset/set-presets", {"PartyPreset": old, "SetSelected": False}),
            ("/tower-infinity/start-stage", {"floor": 1, "presetId": 402}),
        ):
            with self.subTest(route=route):
                self.reject_without_writes(body, route)
        self.assertEqual(
            self.call({"floor": 1, "presetId": 401}, "/tower-infinity/start-stage"), {}
        )

    def test_retry_after_later_edit_choice_and_reopen_returns_current_state(self):
        body = {"PresetId": 401}
        self.call(body)
        edited = copy.deepcopy(current_group(self.db)["Presets"][1])
        edited["Name"] = "Surviving team"
        self.call({"PartyPreset": edited, "SetSelected": True}, "/preset/set-presets", 42)
        expected = {
            "UserPartyPreset2": current_group(self.db),
            "User": self.store.account.profile()["User"],
        }
        before = list(self.db.iterdump())
        self.assertEqual(self.call(body), expected)
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes({"PresetId": 402})
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(body), expected)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.reject_without_writes(body)
        self.call({"PresetId": 402})
        self.assertEqual([p["Id"] for p in current_group(self.db)["Presets"]], [101])

    def test_last_orbital_preset_can_be_removed_without_resurrecting_seed(self):
        self.call({"PresetId": 402})
        self.call({"PresetId": 401}, sequence=42)
        self.assertEqual(
            self.store.account.profile()["User"]["SelectedPresetId"]["InfiniteTower"], 0
        )
        self.open_session(False)
        response = self.call(None, "/preset/get-presets")
        self.assertEqual([p["Id"] for p in response["UserPartyPreset2"]["Presets"]], [101])

    def test_exact_envelope_authentication_scope_and_unknown_id_reject(self):
        self.session = BootstrapSession(self.store)
        self.reject_without_writes({"PresetId": 402})
        self.open_session()
        for body in (
            None,
            {},
            [],
            {"presetId": 402},
            {"PresetId": 402, "User": {}},
            *({"PresetId": value} for value in (True, "402", 402.0, 0, -1, 101, 499, 500)),
        ):
            with self.subTest(body=body):
                self.reject_without_writes(body)

    def test_ambiguous_id_and_invalid_group_revision_reject_without_writes(self):
        for revision in (True, -1, MAX_REVISION):
            group = copy.deepcopy(self.initial_group)
            group["Cas"] = revision
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO party_preset_state VALUES(1,?)", (json.dumps(group),)
                )
            self.reject_without_writes({"PresetId": 402})
        group = copy.deepcopy(self.initial_group)
        group["Presets"].append(copy.deepcopy(group["Presets"][2]))
        with self.db:
            self.db.execute("UPDATE party_preset_state SET value=?", (json.dumps(group),))
        self.reject_without_writes({"PresetId": 402})

    def test_selected_delete_checks_account_revision_before_persisting_group(self):
        profile = self.store.account.profile()
        for revision in (True, -1, MAX_REVISION):
            profile["User"]["Cas"] = revision
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            self.reject_without_writes({"PresetId": 401})

    def test_empty_definition_can_be_deleted_without_owned_member_validation(self):
        group = copy.deepcopy(self.initial_group)
        group["Presets"][2]["Characters"] = []
        with self.db:
            self.db.execute("INSERT INTO party_preset_state VALUES(1,?)", (json.dumps(group),))
        self.call({"PresetId": 402})
        self.assertEqual([p["Id"] for p in current_group(self.db)["Presets"]], [101, 401])

    def test_failed_receipt_rolls_back_definition_choice_and_both_revisions(self):
        self.db.execute(
            "CREATE TRIGGER fail_delete BEFORE INSERT ON preset_delete_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.call({"PresetId": 401})
        self.assertEqual(list(self.db.iterdump()), before)
