# SPDX-License-Identifier: Apache-2.0
"""Orbital deployments persist without changing parties, equipment or clear progress."""

import copy
import json
import sqlite3
import unittest
from contextlib import closing

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.orbital import (
    ORBITAL_ENTRY_ROUTE,
    ORBITAL_EXIT_ROUTE,
    ORBITAL_FORMATION_ROUTE,
    save_formation,
)
from guardian_tales.protocol import PacketError
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import MAX_REVISION
from tests.village.test_village_harvest import NOW, VillageFixture


class OrbitalFormationTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        profile = self.store.account.profile()
        profile["UserProgress"]["Cas"] = 0x80000008
        profile["UserProgress"]["TowerInfinity"] = {
            "Floor": -2,
            "Formation": {"Id": 0, "Positions": [1, 2, 3, 4], "Metadata": "preserve"},
            "Formations": {"1": {"Id": 1, "Positions": [5, 6, 7, 8]}},
            "SelectedParty": 1,
        }
        self.save_profile(profile)
        with self.db:
            self.db.execute(
                "INSERT INTO party_preset_state VALUES(1,?)",
                (json.dumps({"Presets": [{"Id": 400, "Characters": [{"Id": 1, "Weapon1": 1}]}]}),),
            )
        self.request = {"Positions": [20, 1, 8, 12]}

    def call(self, body=None, route=ORBITAL_FORMATION_ROUTE, sequence=3101, now=NOW):
        return super().call(body, route, sequence, now)

    def reject(self, body, sequence=3101):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_save_changes_only_legacy_positions_and_progress_revision_and_retains_all_other_tables(
        self,
    ):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        expected["UserProgress"]["TowerInfinity"]["Formation"]["Positions"] = self.request[
            "Positions"
        ]
        expected["UserProgress"]["Cas"] += 1
        source = self.source.read_bytes()
        tables = [
            r[0]
            for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if r[0] not in ("local_account", "orbital_formation_requests")
        ]
        rows = {t: self.db.execute('SELECT * FROM "' + t + '"').fetchall() for t in tables}
        self.assertEqual(self.call(self.request), {"UserProgress": expected["UserProgress"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        for name, values in rows.items():
            self.assertEqual(self.db.execute('SELECT * FROM "' + name + '"').fetchall(), values)

    def test_grid_edges_and_position_order_are_preserved_even_with_a_short_party(self):
        for sequence, positions in enumerate(([1, 2, 19, 20], [20, 19, 2, 1]), 3101):
            result = self.call({"Positions": positions}, sequence=sequence)
            self.assertEqual(
                result["UserProgress"]["TowerInfinity"]["Formation"]["Positions"], positions
            )
        self.assertEqual(len(self.store.account.profile()["User"]["Characters"]), 1)

    def test_unchanged_deployment_records_once_without_incrementing_revision(self):
        body = {"Positions": [1, 2, 3, 4]}
        before = self.store.account.profile()
        self.assertEqual(self.call(body), {"UserProgress": before["UserProgress"]})
        self.assertEqual(self.store.account.profile(), before)
        dump, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call(body), {"UserProgress": before["UserProgress"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(self.db.total_changes, changes)

    def test_delayed_retry_preserves_later_positions_floor_resources_and_current_response(self):
        self.call(self.request)
        self.call({"Positions": [2, 4, 6, 8]}, sequence=3102)
        current = self.store.account.profile()
        current["UserProgress"]["TowerInfinity"]["Floor"] = 5
        current["User"]["Assets"][0]["Amount"] += 31
        current["User"]["Characters"][0]["Experience"] += 7
        self.save_profile(current)
        dump, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call(self.request), {"UserProgress": current["UserProgress"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(self.db.total_changes, changes)
        self.reject({"Positions": [12, 8, 1, 20]})

    def test_reopen_reconnect_and_account_fetch_preserve_formation_and_retry_identity(self):
        expected = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(reconnect=True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), expected)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(
            self.call({}, "/auth/fetch-account")["UserProgress"], expected["UserProgress"]
        )
        self.open_session(reconnect=False)
        current = self.store.account.profile()
        self.assertEqual(self.call(self.request), {"UserProgress": current["UserProgress"]})
        self.assertEqual(self.store.account.profile(), current)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM orbital_formation_requests").fetchone(), (2,)
        )

    def test_malformed_incomplete_duplicate_out_of_range_and_foreign_keys_reject_atomically(self):
        for body in (
            None,
            [],
            {},
            {"Positions": None},
            {"Positions": {}},
            {"Positions": []},
            {"Positions": [1, 2, 3]},
            {"Positions": [1, 2, 3, 4, 5]},
            {"Positions": [1, 2, 3, 3]},
            {"Positions": [True, 2, 3, 4]},
            {"Positions": [1.0, 2, 3, 4]},
            {"Positions": ["1", 2, 3, 4]},
            {"Positions": [0, 2, 3, 4]},
            {"Positions": [-1, 2, 3, 4]},
            {"Positions": [21, 2, 3, 4]},
            {"Positions": [[], 2, 3, 4]},
            dict(self.request, PresetId=400),
            dict(self.request, floor=3),
        ):
            with self.subTest(body=body):
                self.reject(body)
        for identity in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                save_formation(self.store, self.request, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_authentication_and_completed_account_are_required(self):
        self.session = BootstrapSession(self.store)
        self.reject(self.request)
        self.open_session(reconnect=True)
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        self.reject(self.request)

    def test_invalid_saved_tower_formation_floor_and_revision_reject_without_partial_updates(self):
        original = self.store.account.profile()
        for field, values in (
            ("Cas", (None, True, -1, 0x8000000000000000)),
            ("TowerInfinity", (None, [], {})),
        ):
            for value in values:
                profile = copy.deepcopy(original)
                profile["UserProgress"][field] = value
                self.save_profile(profile)
                self.reject(self.request)
        for field, values in (
            ("Floor", (None, True, 1.0, -0x80000000, 0x80000000)),
            ("Formation", ([], {}, {"Id": True}, {"Id": -1})),
        ):
            for value in values:
                profile = copy.deepcopy(original)
                profile["UserProgress"]["TowerInfinity"][field] = value
                self.save_profile(profile)
                self.reject(self.request)

    def test_missing_legacy_formation_is_created_without_changing_other_formation_maps(self):
        original = self.store.account.profile()
        for missing in (False, True):
            profile = copy.deepcopy(original)
            if missing:
                del profile["UserProgress"]["TowerInfinity"]["Formation"]
            else:
                profile["UserProgress"]["TowerInfinity"]["Formation"] = None
            self.save_profile(profile)
            expected = copy.deepcopy(profile)
            expected["UserProgress"]["TowerInfinity"]["Formation"] = {
                "Id": 0,
                "Positions": self.request["Positions"],
            }
            expected["UserProgress"]["Cas"] += 1
            self.assertEqual(
                self.call(self.request, sequence=3101 + missing),
                {"UserProgress": expected["UserProgress"]},
            )
            self.assertEqual(self.store.account.profile(), expected)

    def test_changed_formation_rejects_at_revision_ceiling_but_noop_and_retry_remain_valid(self):
        profile = self.store.account.profile()
        profile["UserProgress"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        self.reject(self.request)
        noop = {"Positions": profile["UserProgress"]["TowerInfinity"]["Formation"]["Positions"]}
        self.assertEqual(self.call(noop), {"UserProgress": profile["UserProgress"]})
        before = list(self.db.iterdump())
        self.assertEqual(self.call(noop), {"UserProgress": profile["UserProgress"]})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_receipt_failure_rolls_back_formation_and_revision(self):
        with self.db:
            self.db.execute(
                "CREATE TRIGGER fail_formation BEFORE INSERT ON orbital_formation_requests BEGIN SELECT RAISE(ABORT,'test failure'); END"
            )
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_entry_and_exit_after_repositioning_remain_read_only_and_keep_the_saved_layout(self):
        self.call(self.request)
        (self.references / "orbital_entry_catalog.json").write_text(
            json.dumps({"client": CLIENT, "floors": [1, 2, 3]})
        )
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"floor": 3, "presetId": 400}, ORBITAL_ENTRY_ROUTE), {})
        self.assertEqual(
            self.call({"floor": 3, "isCleared": False, "damages": [1]}, ORBITAL_EXIT_ROUTE), {}
        )
        self.assertEqual(list(self.db.iterdump()), before)

    def test_victory_and_its_delayed_retry_preserve_a_later_formation(self):
        (self.references / "orbital_entry_catalog.json").write_text(
            json.dumps({"client": CLIENT, "floors": [1, 2, 3]})
        )
        (self.references / "orbital_completion_catalog.json").write_text(
            json.dumps({"client": CLIENT, "no_rewards": True})
        )
        body = {"floor": 3, "isCleared": True, "damages": [1]}
        self.call(body, ORBITAL_EXIT_ROUTE, sequence=3102)
        self.call(self.request)
        current = self.store.account.profile()
        before = list(self.db.iterdump())
        reply = self.call(body, ORBITAL_EXIT_ROUTE, sequence=3102)
        self.assertEqual(reply["UserProgress"], current["UserProgress"])
        self.assertEqual(
            reply["TowerInfinity"]["Formation"]["Positions"], self.request["Positions"]
        )
        self.assertEqual(list(self.db.iterdump()), before)

    def test_fresh_completed_account_supports_native_default_formation_without_external_catalogs(
        self,
    ):
        with closing(sqlite3.connect(":memory:")) as db:
            store = GuestStore(db)
            store.account.complete_prologue(
                "Synthetic",
                {
                    "IsMale": True,
                    "VoiceType": 0,
                    "Weapon1ItemId": 9010010,
                    "Weapon2ItemId": 9080010,
                    "BobLindaQuestGrade": 0,
                },
            )
            before = store.account.profile()
            result = save_formation(store, self.request, "fresh-formation-01")
            expected = copy.deepcopy(before)
            expected["UserProgress"]["TowerInfinity"]["Formation"]["Positions"] = self.request[
                "Positions"
            ]
            expected["UserProgress"]["Cas"] += 1
            self.assertEqual(result, {"UserProgress": expected["UserProgress"]})
            self.assertEqual(store.account.profile(), expected)
