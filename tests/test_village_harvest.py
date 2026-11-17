# SPDX-License-Identifier: Apache-2.0
"""Village production persists together with balances and retry identities."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.snapshots import CLIENT, import_snapshot, preserved_read
from guardian_tales.village import GOLD, INT_MAX, MAX_REVISION, ROUTE, SOUL_POINTS, current_village
from tests.test_snapshots import synthetic_snapshot

NOW = 1800000000


class VillageFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.references = self.root / "references"
        self.references.mkdir()
        self.catalog = {
            "client": CLIENT,
            "min_seconds": 600,
            "inn_factor": 10,
            "facility_divisor": 10,
            "sp_base_max": 0,
            "rarity_bonus": [5, 10, 15],
            "match_bonus": 10,
            "buildings": {
                "1001": {
                    "kind": "inn",
                    "sp_rate": 0.1,
                    "gold_rate": 0.2,
                    "sp_storage": 10000,
                    "gold_storage": 1000,
                    "manufacture_max": 10,
                },
                "2001": {
                    "kind": "producer",
                    "specialization": "synthetic",
                    "slots": 1,
                    "effects": [
                        {"item_id": SOUL_POINTS, "value": 100, "period": 60, "storage": 1000}
                    ],
                },
                "3001": {"kind": "other"},
            },
            "followers": {"10": {"rarity": 0, "specialization": "synthetic"}},
        }
        self.catalog_path = self.references / "village_harvest_catalog.json"
        self.write_catalog()
        snapshot = synthetic_snapshot()
        for item in (GOLD, SOUL_POINTS):
            rows = snapshot["profile"]["User"]["Assets"]
            asset = next((r for r in rows if r["Id"] == item), None)
            if asset is None:
                asset = {"Id": item, "Amount": 0, "Spent": 0, "MaxAdj": 0, "NextCharge": None}
                rows.append(asset)
            asset.update(Amount=100, MaxAdj=50000)
        self.initial = {
            "UserId": 9400,
            "Cas": 17,
            "LastHarvestTime": {"SoulPoint": NOW - 600, "Gold": NOW - 600},
            "Manufacture": [{"Type": i, "Level": i} for i in (1, 2, 3)],
            "VillagerIds": [10],
            "Buildings": [
                {"Id": 1, "SpecId": 1001, "Status": 0, "EndTime": 0, "DeployHeroes": [1]},
                {
                    "Id": 2,
                    "SpecId": 2001,
                    "Status": 2,
                    "EndTime": NOW - 600,
                    "DeployVillagers": [10],
                    "DeployHeroes": None,
                },
                {
                    "Id": 3,
                    "SpecId": 3001,
                    "Status": 4,
                    "EndTime": NOW + 600,
                    "DeployVillagers": None,
                },
            ],
            "PurchasedShopItemCount": {"12": 1},
            "BaseCampParties": [{"Id": 1, "Characters": [1]}],
            "Airship": {"NextVisitTime": NOW + 900},
            "Complaints": [],
        }
        snapshot["startup_reads"]["/lobby-village/enter"]["value"][
            "UserLobbyVillage"
        ] = self.initial
        self.source = self.root / "synthetic.json"
        self.source.write_text(json.dumps(snapshot))
        self.state = self.root / "state"
        import_snapshot(self.source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def write_catalog(self):
        self.catalog_path.write_text(json.dumps(self.catalog))

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db, self.references)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            "/auth/sign-in",
            1,
        )

    def call(self, body=None, route=ROUTE, sequence=51, now=NOW):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        with patch("guardian_tales.village.time.time", return_value=now):
            return read_json_body(parse_packet(encode_packet(self.session.handle(request))))

    def asset(self, profile, item):
        return next(a for a in profile["User"]["Assets"] if a["Id"] == item)

    def save_profile(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))

    def save_village(self, village):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO village_state VALUES(1,?)", (json.dumps(village),)
            )

    def reject_without_writes(self, body=None):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)


class VillageHarvestTests(VillageFixture, unittest.TestCase):
    def test_collection_updates_only_balances_clocks_and_revisions(self):
        profile = self.store.account.profile()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        source = self.source.read_bytes()
        before_read = preserved_read(self.db, "/lobby-village/enter")
        response = self.call()
        self.assertEqual(
            response["AddedItems"],
            [{"ItemId": SOUL_POINTS, "Amount": 835}, {"ItemId": GOLD, "Amount": 120}],
        )
        expected = copy.deepcopy(profile)
        self.asset(expected, SOUL_POINTS)["Amount"] += 835
        self.asset(expected, GOLD)["Amount"] += 120
        expected["User"]["Cas"] += 1
        village = copy.deepcopy(self.initial)
        village["LastHarvestTime"] = {"SoulPoint": NOW, "Gold": NOW}
        village["Buildings"][1]["EndTime"] = NOW
        village["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            response,
            {
                "User": expected["User"],
                "UserLobbyVillage": village,
                "AddedItems": response["AddedItems"],
            },
        )
        self.assertEqual(
            preserved_read(self.db, "/lobby-village/enter"),
            dict(before_read, UserLobbyVillage=village),
        )
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(self.source.read_bytes(), source)

    def test_minimum_and_period_boundaries_do_not_grant_early(self):
        response = self.call(now=NOW - 1)
        self.assertEqual(response["AddedItems"], [])
        self.assertEqual(current_village(self.db), self.initial)
        response = self.call(sequence=52)
        self.assertEqual(response["AddedItems"][0]["Amount"], 835)

    def test_producer_periods_bonus_and_storage_caps(self):
        self.catalog["buildings"]["1001"].update(sp_rate=0, gold_rate=0)
        self.write_catalog()
        response = self.call(now=NOW + 59)
        self.assertEqual(response["AddedItems"], [{"ItemId": SOUL_POINTS, "Amount": 115}])
        response = self.call(sequence=52, now=NOW + 100000)
        self.assertEqual(response["AddedItems"], [{"ItemId": SOUL_POINTS, "Amount": 1000}])

    def test_soul_point_cap_preserves_full_resource_clocks_but_collects_gold(self):
        profile = self.store.account.profile()
        self.asset(profile, SOUL_POINTS)["Amount"] = 50000
        self.save_profile(profile)
        response = self.call()
        self.assertEqual(response["AddedItems"], [{"ItemId": GOLD, "Amount": 120}])
        village = response["UserLobbyVillage"]
        self.assertEqual(village["LastHarvestTime"]["SoulPoint"], NOW - 600)
        self.assertEqual(village["Buildings"][1], self.initial["Buildings"][1])
        self.assertEqual(
            self.asset(self.store.account.profile(), SOUL_POINTS), self.asset(profile, SOUL_POINTS)
        )

    def test_partial_capacity_and_gold_overflow_are_clamped_without_negative_rewards(self):
        profile = self.store.account.profile()
        self.asset(profile, SOUL_POINTS)["Amount"] = 49990
        self.asset(profile, GOLD)["Amount"] = INT_MAX - 5
        self.save_profile(profile)
        response = self.call()
        self.assertEqual(
            response["AddedItems"],
            [{"ItemId": SOUL_POINTS, "Amount": 10}, {"ItemId": GOLD, "Amount": 5}],
        )
        self.assertEqual(response["UserLobbyVillage"]["Buildings"][1]["EndTime"], NOW)

    def test_future_and_zero_clocks_are_not_initialized_or_backfilled(self):
        village = copy.deepcopy(self.initial)
        village["LastHarvestTime"] = {"SoulPoint": NOW + 1, "Gold": 0}
        village["Buildings"][1]["EndTime"] = 0
        self.save_village(village)
        before = self.store.account.profile()
        self.assertEqual(self.call()["AddedItems"], [])
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(current_village(self.db), village)

    def test_retry_after_later_collection_returns_current_state_and_frozen_notices(self):
        first = self.call()
        self.call(sequence=52, now=NOW + 600)
        expected = self.store.account.profile()
        village = current_village(self.db)
        self.catalog_path.unlink()
        before = list(self.db.iterdump())
        response = self.call({}, now=NOW + 1200)
        self.assertEqual(
            response,
            {
                "User": expected["User"],
                "UserLobbyVillage": village,
                "AddedItems": first["AddedItems"],
            },
        )
        self.assertEqual(list(self.db.iterdump()), before)

    def test_reopening_reconnect_and_fresh_login_do_not_recollect_old_ticks(self):
        self.call()
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.call()
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        profile = self.store.account.profile()
        self.assertEqual(self.call()["AddedItems"], [])
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.call(None, "/lobby-village/enter")["UserLobbyVillage"], current_village(self.db)
        )

    def test_parameters_authentication_and_missing_catalog_reject_without_writes(self):
        for body in ({"amount": 100}, {"itemId": SOUL_POINTS}, [], False):
            self.reject_without_writes(body)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes()
        self.open_session()
        self.catalog_path.unlink()
        self.reject_without_writes()

    def test_unknown_or_unowned_deployments_and_malformed_buildings_reject(self):
        for field, value in (
            ("SpecId", 9999),
            ("Status", True),
            ("EndTime", "yesterday"),
            ("DeployVillagers", [99]),
            ("DeployVillagers", [10, 10]),
            ("DeployVillagers", False),
        ):
            village = copy.deepcopy(self.initial)
            village["Buildings"][1][field] = value
            self.save_village(village)
            self.reject_without_writes()

    def test_invalid_owner_manufacture_and_revision_limits_reject(self):
        for field, value in (
            ("UserId", 99),
            ("Manufacture", [{"Type": 1, "Level": 1}]),
            ("Cas", MAX_REVISION),
        ):
            village = copy.deepcopy(self.initial)
            village[field] = value
            self.save_village(village)
            self.reject_without_writes()
        self.save_village(self.initial)
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        self.reject_without_writes()

    def test_invalid_catalogs_reject_before_balance_or_clock_updates(self):
        for field, value in (
            ("client", {}),
            ("min_seconds", True),
            ("facility_divisor", 0),
            ("buildings", {}),
            ("followers", {}),
            ("rarity_bonus", [True]),
        ):
            original = self.catalog[field]
            self.catalog[field] = value
            self.write_catalog()
            self.reject_without_writes()
            self.catalog[field] = original
        self.catalog_path.write_text(" " * (2 * 1024 * 1024 + 1))
        self.reject_without_writes()

    def test_gold_facility_uses_its_own_clock_and_no_specialization_match(self):
        spec = self.catalog["buildings"]["2001"]
        spec["effects"][0]["item_id"] = GOLD
        spec["specialization"] = "unmatched"
        self.write_catalog()
        response = self.call()
        self.assertEqual(
            response["AddedItems"],
            [{"ItemId": SOUL_POINTS, "Amount": 720}, {"ItemId": GOLD, "Amount": 225}],
        )

    def test_unfinished_facilities_and_other_village_systems_are_unchanged(self):
        village = copy.deepcopy(self.initial)
        village["Buildings"][1]["Status"] = 1
        self.save_village(village)
        result = self.call()
        self.assertEqual(result["AddedItems"][0]["Amount"], 720)
        self.assertEqual(result["UserLobbyVillage"]["Buildings"], village["Buildings"])

    def test_receipt_failure_rolls_back_balances_clocks_and_both_revisions(self):
        self.db.execute(
            "CREATE TRIGGER fail_harvest BEFORE INSERT ON village_harvest_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.call()
        self.assertEqual(list(self.db.iterdump()), before)
