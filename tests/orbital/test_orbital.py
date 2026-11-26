# SPDX-License-Identifier: Apache-2.0
"""Orbital loading trials validate captured state without changing the account."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.orbital import ORBITAL_ENTRY_ROUTE, ORBITAL_EXIT_ROUTE
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.snapshots import CLIENT, import_snapshot
from tests.account.test_snapshots import synthetic_snapshot


class OrbitalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.references = self.root / "references"
        self.references.mkdir()
        self.catalog = self.references / "orbital_entry_catalog.json"
        self.catalog.write_text(json.dumps({"client": CLIENT, "floors": [1, 2, 3, 4]}))
        snapshot = synthetic_snapshot()
        snapshot["profile"]["UserProgress"]["TowerInfinity"]["Floor"] = 2
        self.presets = {"Presets": [{"Id": 9, "Characters": [{"Id": 1, "Weapon1": 1}]}]}
        snapshot["startup_reads"]["/preset/get-presets"]["value"]["UserPartyPreset2"] = self.presets
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(snapshot))
        self.state = self.root / "state"
        import_snapshot(self.source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.store = GuestStore(self.db, self.references)
        self.session = BootstrapSession(self.store)
        self.login()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def call(self, body, route=ORBITAL_ENTRY_ROUTE):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=20)
            )
        )
        response = self.session.handle(request)
        self.assertEqual(response.sequence_id, 20)
        self.assertEqual(response.body_type, 1)
        return read_json_body(parse_packet(encode_packet(response)))

    def login(self, reconnect=False):
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            "/auth/sign-in",
        )

    def assert_rejected_without_writes(self, body):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_entry_and_repeated_requests_preserve_every_saved_table(self):
        before = list(self.db.iterdump())
        source = self.source.read_bytes()
        for floor in (1, 2, 3, 3):
            self.assertEqual(self.call({"floor": floor, "presetId": 9}), {})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.source.read_bytes(), source)

    def test_authentication_and_request_validation_precede_authorization(self):
        self.session = BootstrapSession(self.store)
        self.assert_rejected_without_writes({"floor": 3, "presetId": 9})
        self.login()
        for body in (
            None,
            {},
            [],
            {"floor": 3},
            {"floor": 3, "presetId": True},
            {"floor": True, "presetId": 9},
            {"floor": 0, "presetId": 9},
            {"floor": -3, "presetId": 9},
            {"floor": 3, "presetId": 0},
            {"floor": 3, "presetId": 9, "Claim": True},
            {"floor": 4, "presetId": 9},
            {"floor": 99, "presetId": 9},
            {"floor": 3, "presetId": 99},
        ):
            with self.subTest(body=body):
                self.assert_rejected_without_writes(body)

    def test_missing_foreign_or_invalid_catalog_rejects_without_writes(self):
        valid = {"client": CLIENT, "floors": [1, 2, 3]}
        for invalid in (
            {},
            dict(valid, client={"version": "other"}),
            dict(valid, floors=[]),
            dict(valid, floors=[True]),
            dict(valid, floors=[1, 1]),
            dict(valid, floors=[0]),
        ):
            with self.subTest(catalog=invalid):
                self.catalog.write_text(json.dumps(invalid))
                self.assert_rejected_without_writes({"floor": 3, "presetId": 9})
        self.catalog.unlink()
        self.assert_rejected_without_writes({"floor": 3, "presetId": 9})

    def test_invalid_captured_presets_and_unowned_members_or_gear_reject(self):
        candidates = [
            None,
            {},
            {"Presets": []},
            {"Presets": self.presets["Presets"] * 2},
            {"Presets": [{"Id": 9, "Characters": []}]},
            {"Presets": [{"Id": 9, "Characters": [{"Id": 1}] * 2}]},
            {"Presets": [{"Id": 9, "Characters": [{"Id": 99}]}]},
            {"Presets": [{"Id": 9, "Characters": [{"Id": True}]}]},
            {"Presets": [{"Id": 9, "Characters": [{"Id": 1, "Weapon1": 99}]}]},
            {"Presets": [{"Id": 9, "Characters": [{"Id": 1, "Weapon1": False}]}]},
        ]
        base = json.loads(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        )
        for candidate in candidates:
            with self.subTest(presets=candidate):
                reads = copy.deepcopy(base)
                reads["/preset/get-presets"]["value"]["UserPartyPreset2"] = candidate
                with self.db:
                    self.db.execute(
                        "UPDATE imported_account SET startup_reads=?", (json.dumps(reads),)
                    )
                self.assert_rejected_without_writes({"floor": 3, "presetId": 9})

    def test_reopening_and_reconnecting_do_not_persist_attempts_or_advance_floors(self):
        self.call({"floor": 3, "presetId": 9})
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.store = GuestStore(self.db, self.references)
        self.session = BootstrapSession(self.store)
        self.login(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"floor": 3, "presetId": 9}), {})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.store.account.profile()["UserProgress"]["TowerInfinity"]["Floor"], 2)

    def test_results_formation_changes_and_fresh_accounts_remain_unsupported(self):
        before = list(self.db.iterdump())
        for route in ("/tower-infinity/end-stage", "/tower-infinity/save-formation"):
            with self.assertRaises(PacketError):
                self.call({"floor": 3, "isCleared": True, "damages": []}, route)
        self.assertEqual(list(self.db.iterdump()), before)
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        self.assert_rejected_without_writes({"floor": 3, "presetId": 9})

    def test_non_clear_exits_preserve_every_table_source_and_floor_without_attempt_records(self):
        before = list(self.db.iterdump())
        source = self.source.read_bytes()
        for floor, damages in ((1, []), (2, [0]), (3, [1, 22, 333, 0x7FFFFFFF])):
            body = {"floor": floor, "isCleared": False, "damages": damages}
            self.assertEqual(self.call(body, ORBITAL_EXIT_ROUTE), {})
            self.assertEqual(self.call(body, ORBITAL_EXIT_ROUTE), {})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(self.store.account.profile()["UserProgress"]["TowerInfinity"]["Floor"], 2)

    def test_non_clear_exit_authentication_schema_damage_bounds_and_victory_rejection(self):
        valid = {"floor": 3, "isCleared": False, "damages": [0, 1, 2, 3]}
        self.session = BootstrapSession(self.store)
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(valid, ORBITAL_EXIT_ROUTE)
        self.assertEqual(list(self.db.iterdump()), before)
        self.login()
        for body in (
            None,
            {},
            [],
            dict(valid, floor=True),
            dict(valid, floor=0),
            dict(valid, floor=4),
            dict(valid, floor=99),
            dict(valid, isCleared=True),
            dict(valid, isCleared=0),
            dict(valid, damages=None),
            dict(valid, damages={}),
            dict(valid, damages=[True]),
            dict(valid, damages=[-1]),
            dict(valid, damages=[1.5]),
            dict(valid, damages=[0x80000000]),
            dict(valid, damages=[0] * 5),
            dict(valid, Claim=True),
        ):
            before = list(self.db.iterdump())
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, ORBITAL_EXIT_ROUTE)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_non_clear_exit_requires_matching_catalog_and_valid_signed_saved_progress(self):
        valid = {"floor": 3, "isCleared": False, "damages": []}
        original = self.store.account.profile()
        for floor in (2, -2):
            profile = copy.deepcopy(original)
            profile["UserProgress"]["TowerInfinity"]["Floor"] = floor
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            before = list(self.db.iterdump())
            self.assertEqual(self.call(valid, ORBITAL_EXIT_ROUTE), {})
            self.assertEqual(list(self.db.iterdump()), before)
        self.catalog.unlink()
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(valid, ORBITAL_EXIT_ROUTE)
        self.assertEqual(list(self.db.iterdump()), before)
        self.catalog.write_text(json.dumps({"client": CLIENT, "floors": [1, 2, 3]}))
        for floor in (True, None, "2", -0x80000000, 0x80000000, 1):
            profile = copy.deepcopy(original)
            profile["UserProgress"]["TowerInfinity"]["Floor"] = floor
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            before = list(self.db.iterdump())
            with self.subTest(saved_floor=floor), self.assertRaises(PacketError):
                self.call(valid, ORBITAL_EXIT_ROUTE)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_non_clear_exit_reopening_reconnect_and_new_login_remain_read_only(self):
        body = {"floor": 3, "isCleared": False, "damages": [1, 2]}
        self.call(body, ORBITAL_EXIT_ROUTE)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.store = GuestStore(self.db, self.references)
        for reconnect in (True, False):
            self.session = BootstrapSession(self.store)
            self.login(reconnect)
            before = list(self.db.iterdump())
            self.assertEqual(self.call(body, ORBITAL_EXIT_ROUTE), {})
            self.assertEqual(list(self.db.iterdump()), before)

    def test_non_clear_exit_rejects_incomplete_prologue_without_writes(self):
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call({"floor": 1, "isCleared": False, "damages": []}, ORBITAL_EXIT_ROUTE)
        self.assertEqual(list(self.db.iterdump()), before)
