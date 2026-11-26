# SPDX-License-Identifier: Apache-2.0
"""Editing one saved Orbital team preserves captured seeds and unrelated state."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.accounts.snapshots import CLIENT, import_snapshot, preserved_read
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.teams.presets import GEAR_FIELDS, MAX_REVISION, current_group
from tests.account.test_snapshots import synthetic_snapshot

ROUTE = "/preset/set-presets"


class PresetFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.references = self.root / "references"
        self.references.mkdir()
        (self.references / "orbital_entry_catalog.json").write_text(
            json.dumps({"client": CLIENT, "floors": [1, 2]})
        )
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["SelectedPresetId"] = {"InfiniteTower": 401, "Rift": 101}
        character = {"Id": 1, **dict.fromkeys(GEAR_FIELDS)}
        character.update(Weapon1=1, Weapon2=2)
        self.initial_group = {
            "Cas": 7,
            "Presets": [
                {
                    "Id": ident,
                    "Name": "Synthetic team",
                    "Order": order,
                    "Characters": [copy.deepcopy(character)],
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

    def call(self, body, route=ROUTE, sequence=31):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(request))))

    def body(self, ident=402, selected=False):
        preset = copy.deepcopy(
            next(p for p in current_group(self.db)["Presets"] if p["Id"] == ident)
        )
        preset["Characters"] = [
            {k: v for k, v in c.items() if v is not None} for c in preset["Characters"]
        ]
        return {"PartyPreset": preset, "SetSelected": selected}

    def reject_without_writes(self, body, route=ROUTE):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route)
        self.assertEqual(list(self.db.iterdump()), before)


class PresetEditTests(PresetFixture, unittest.TestCase):
    def test_edit_changes_one_team_and_preserves_profile_captured_seed_and_other_reads(self):
        profile = self.store.account.profile()
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        before_reads = preserved_read(self.db, "/preset/get-presets")
        body = self.body()
        body["PartyPreset"]["Name"] = "Edited team"
        response = self.call(body)
        expected = copy.deepcopy(self.initial_group)
        expected["Cas"] += 1
        expected["Presets"][2]["Name"] = "Edited team"
        self.assertEqual(
            response,
            {
                "UserPartyPreset2": expected,
                "User": {key: profile["User"][key] for key in ("Id", "Cas", "SelectedPresetId")},
            },
        )
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(current_group(self.db), expected)
        after_reads = preserved_read(self.db, "/preset/get-presets")
        self.assertEqual(after_reads, dict(before_reads, UserPartyPreset2=expected))
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.call({"floor": 1, "presetId": 402}, "/tower-infinity/start-stage"), {}
        )

    def test_save_and_select_changes_only_choice_revision_and_target_definition(self):
        profile = self.store.account.profile()
        body = self.body(selected=True)
        body["PartyPreset"]["Name"] = "Chosen team"
        response = self.call(body)
        expected = copy.deepcopy(profile)
        expected["User"]["SelectedPresetId"]["InfiniteTower"] = 402
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            response["User"],
            {key: expected["User"][key] for key in ("Id", "Cas", "SelectedPresetId")},
        )
        self.assertEqual(current_group(self.db)["Presets"][:2], self.initial_group["Presets"][:2])
        self.assertEqual(current_group(self.db)["Cas"], 8)

    def test_omitted_native_gear_slots_clear_saved_slot_without_changing_inventory(self):
        profile = self.store.account.profile()
        body = self.body()
        del body["PartyPreset"]["Characters"][0]["Weapon2"]
        self.call(body)
        self.assertIsNone(current_group(self.db)["Presets"][2]["Characters"][0]["Weapon2"])
        self.assertEqual(self.store.account.profile(), profile)

    def test_noop_native_serialization_does_not_increment_revisions_or_create_overlay(self):
        profile = self.store.account.profile()
        body = self.body(401, selected=True)
        self.call(body)
        self.assertEqual(current_group(self.db), self.initial_group)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertIsNone(self.db.execute("SELECT value FROM party_preset_state").fetchone())
        before = list(self.db.iterdump())
        self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_retry_reopen_and_new_epoch_preserve_later_edits_and_selections(self):
        first = self.body(selected=True)
        first["PartyPreset"]["Name"] = "First"
        self.call(first)
        second = self.body(selected=True)
        second["PartyPreset"]["Name"] = "Second"
        self.call(second, sequence=32)
        self.call({"PresetId": 401}, "/preset/set-selected-preset", 33)
        before = list(self.db.iterdump())
        response = self.call(first)
        self.assertEqual(response["UserPartyPreset2"]["Presets"][2]["Name"], "Second")
        self.assertEqual(response["User"]["SelectedPresetId"]["InfiniteTower"], 401)
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes(second)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.call(first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.call(first)
        self.assertEqual(current_group(self.db)["Presets"][2]["Name"], "First")

    def test_authentication_exact_envelope_scope_creation_and_reordering_reject(self):
        body = self.body()
        self.session = BootstrapSession(self.store)
        self.reject_without_writes(body)
        self.open_session()
        invalid = [
            None,
            {},
            {"PartyPreset": body["PartyPreset"], "SetSelected": 1},
            dict(body, User={}),
        ]
        for field, value in (
            ("Id", 101),
            ("Id", 499),
            ("Order", 99),
            ("Order", True),
            ("Name", "bad\nname"),
            ("Name", "x" * 65),
            ("Characters", None),
        ):
            case = copy.deepcopy(body)
            case["PartyPreset"][field] = value
            invalid.append(case)
        for case in invalid:
            with self.subTest(body=case):
                self.reject_without_writes(case)

    def test_unowned_repeated_or_injected_character_data_rejects_atomically(self):
        for character in (
            {"Id": 999},
            {"Id": True},
            {"Id": 1, "Weapon1": 999},
            {"Id": 1, "Weapon1": False},
            {"Id": 1, "Experience": 10000},
        ):
            body = self.body()
            body["PartyPreset"]["Characters"] = [character]
            self.reject_without_writes(body)
        for count in (2, 5):
            body = self.body()
            body["PartyPreset"]["Characters"] *= count
            self.reject_without_writes(body)

    def test_empty_team_can_be_saved_but_cannot_be_selected_or_entered(self):
        body = self.body()
        body["PartyPreset"]["Characters"] = []
        self.call(body)
        before = list(self.db.iterdump())
        for route, request in (
            ("/preset/set-selected-preset", {"PresetId": 402}),
            ("/tower-infinity/start-stage", {"floor": 1, "presetId": 402}),
        ):
            with self.assertRaises(PacketError):
                self.call(request, route)
        body["SetSelected"] = True
        with self.assertRaises(PacketError):
            self.call(body, sequence=32)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_group_or_account_revisions_reject_without_partial_updates(self):
        group = copy.deepcopy(self.initial_group)
        for value in (True, MAX_REVISION):
            group["Cas"] = value
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO party_preset_state VALUES(1,?)", (json.dumps(group),)
                )
            body = self.body()
            body["PartyPreset"]["Name"] = "Changed"
            self.reject_without_writes(body)
        with self.db:
            self.db.execute("DELETE FROM party_preset_state")
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        body = self.body(selected=True)
        body["PartyPreset"]["Name"] = "Changed"
        self.reject_without_writes(body)

    def test_failed_receipt_rolls_back_current_presets_selection_and_both_revisions(self):
        first = self.body()
        first["PartyPreset"]["Name"] = "First"
        self.call(first)
        self.db.execute(
            "CREATE TRIGGER fail_edit BEFORE INSERT ON preset_edit_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        body = self.body(selected=True)
        body["PartyPreset"]["Name"] = "Second"
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.call(body, sequence=32)
        self.assertEqual(list(self.db.iterdump()), before)
        self.db.execute("DROP TRIGGER fail_edit")
        self.db.commit()
        self.call(body, sequence=32)
        self.assertEqual(current_group(self.db)["Presets"][2]["Name"], "Second")
        self.assertEqual(
            self.store.account.profile()["User"]["SelectedPresetId"]["InfiniteTower"], 402
        )
