# SPDX-License-Identifier: Apache-2.0
"""Regenerating obstacles can be acknowledged without payment, rewards or deletion."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.snapshots import CLIENT, preserved_read
from guardian_tales.village import MAX_REVISION, MAX_TIME, current_village
from guardian_tales.village import ROUTE as HARVEST
from guardian_tales.village_obstacle import ROUTE
from tests.village.test_village_harvest import NOW, VillageFixture


class VillageObstacleMockTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.mock_path = self.references / "village_obstacle_mock_catalog.json"
        self.mock_catalog = {"client": CLIENT, "regenerating_specs": {"9001": 60}}
        self.write_mock_catalog()
        self.catalog["buildings"]["9001"] = {"kind": "other"}
        self.write_catalog()
        self.initial["Buildings"].append(
            {
                "Id": 9,
                "SpecId": 9001,
                "Status": 3,
                "EndTime": NOW - 1,
                "Position": [4, 5],
                "DeployHeroes": None,
            }
        )
        self.save_village(self.initial)

    def write_mock_catalog(self):
        self.mock_path.write_text(json.dumps(self.mock_catalog))

    def call(self, body=None, route=ROUTE, sequence=121, now=NOW):
        return super().call(body, route, sequence, now)

    def test_only_selected_obstacle_status_clock_and_village_revision_change(self):
        profile = self.store.account.profile()
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        expected = copy.deepcopy(self.initial)
        expected["Buildings"][-1].update(Status=3, EndTime=NOW + 60)
        expected["Cas"] += 1
        self.assertEqual(self.call({"buildingId": 9}), {"UserLobbyVillage": expected})
        self.assertEqual(current_village(self.db), expected)
        self.assertEqual(
            preserved_read(self.db, "/lobby-village/enter")["UserLobbyVillage"], expected
        )
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )

    def test_active_obstacle_starts_regeneration_and_future_timer_is_not_extended(self):
        village = copy.deepcopy(self.initial)
        village["Buildings"][-1].update(Status=0, EndTime=0)
        self.save_village(village)
        first = self.call({"buildingId": 9})
        self.assertEqual(first["UserLobbyVillage"]["Buildings"][-1]["Status"], 3)
        self.assertEqual(self.call({"buildingId": 9}, sequence=122, now=NOW + 1), first)
        self.assertEqual(current_village(self.db), first["UserLobbyVillage"])

    def test_old_retry_preserves_later_regeneration_and_collection_without_catalog(self):
        self.call({"buildingId": 9})
        self.call(route=HARVEST, sequence=122)
        self.call({"buildingId": 9}, sequence=123, now=NOW + 60)
        profile = self.store.account.profile()
        village = current_village(self.db)
        self.mock_path.unlink()
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"buildingId": 9}, now=NOW + 120), {"UserLobbyVillage": village})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.store.account.profile(), profile)
        self.reject_without_writes({"buildingId": 1})

    def test_reopening_reconnect_and_fresh_login_keep_building_position_and_timer(self):
        first = self.call({"buildingId": 9})
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"buildingId": 9}), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.assertEqual(self.call({"buildingId": 9}), first)
        self.call({"buildingId": 9}, sequence=122, now=NOW + 60)
        saved = current_village(self.db)
        self.assertEqual(saved["Cas"], self.initial["Cas"] + 2)
        self.assertEqual(saved["Buildings"][-1]["Position"], [4, 5])

    def test_foreign_normal_ambiguous_and_invalid_obstacles_cannot_be_changed(self):
        self.reject_without_writes({"buildingId": 1})
        self.reject_without_writes({"buildingId": 999})
        for field, value in (
            ("SpecId", 1001),
            ("Status", 2),
            ("Status", True),
            ("EndTime", -1),
            ("EndTime", "bad"),
        ):
            village = copy.deepcopy(self.initial)
            village["Buildings"][-1][field] = value
            self.save_village(village)
            self.reject_without_writes({"buildingId": 9})
        village = copy.deepcopy(self.initial)
        village["UserId"] = 1
        self.save_village(village)
        self.reject_without_writes({"buildingId": 9})
        village = copy.deepcopy(self.initial)
        village["Buildings"].append(dict(village["Buildings"][-1]))
        self.save_village(village)
        self.reject_without_writes({"buildingId": 9})

    def test_revision_and_regeneration_clock_limits_reject_without_writes(self):
        village = copy.deepcopy(self.initial)
        village["Cas"] = MAX_REVISION
        self.save_village(village)
        self.reject_without_writes({"buildingId": 9})
        self.save_village(self.initial)
        before = list(self.db.iterdump())
        for now in (0, True, MAX_TIME - 59):
            with self.assertRaises(ValueError):
                self.store.account.remove_village_obstacle({"buildingId": 9}, "bad-clock", now)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_explicit_config_exact_building_id_request_identity_and_authentication(self):
        original = copy.deepcopy(self.mock_catalog)
        for key, value in (
            ("client", {}),
            ("regenerating_specs", {}),
            ("regenerating_specs", {"09001": 60}),
            ("regenerating_specs", {"9001": True}),
            ("regenerating_specs", {"9001": 0}),
        ):
            self.mock_catalog = dict(original, **{key: value})
            self.write_mock_catalog()
            self.reject_without_writes({"buildingId": 9})
        self.mock_path.write_text(" " * 65537)
        self.reject_without_writes({"buildingId": 9})
        self.mock_path.unlink()
        self.reject_without_writes({"buildingId": 9})
        self.mock_catalog = original
        self.write_mock_catalog()
        for body in (
            None,
            {},
            [],
            {"buildingId": True},
            {"buildingId": 0},
            {"BuildingId": 9},
            {"buildingId": 9, "Reward": False},
        ):
            self.reject_without_writes(body)
        for op in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.remove_village_obstacle({"buildingId": 9}, op, NOW)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes({"buildingId": 9})

    def test_receipt_failure_rolls_back_obstacle_clock_revision_and_overlay(self):
        self.db.execute(
            "CREATE TRIGGER reject_obstacle BEFORE INSERT ON village_obstacle_mock_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call({"buildingId": 9})
        self.assertEqual(list(self.db.iterdump()), before)
