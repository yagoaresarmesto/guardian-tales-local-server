# SPDX-License-Identifier: Apache-2.0
"""Fixed mastery collections preserve normal points, levels and other village state."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.basecamp import MASTERY_POINTS, ROUTE
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.snapshots import CLIENT, preserved_read
from guardian_tales.village import INT_MAX, MAX_REVISION, current_village
from tests.test_village_harvest import NOW, VillageFixture

AMOUNT = 100000000


class BaseCampHarvestTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.debug_catalog = {
            "client": CLIENT,
            "portal_specs": [9001],
            "min_seconds": 60,
            "debug_mastery_points": AMOUNT,
        }
        self.debug_path = self.references / "basecamp_harvest_catalog.json"
        self.write_debug_catalog()
        self.initial["Buildings"].append(
            {"Id": 9, "SpecId": 9001, "Status": 2, "EndTime": NOW - 60}
        )
        self.save_village(self.initial)
        self.catalog["buildings"]["9001"] = {"kind": "other"}
        self.write_catalog()
        profile = self.store.account.profile()
        profile["User"].update(GuardianExperience=1234, GuardianMasteryLevel=1)
        for item in (70013, MASTERY_POINTS):
            asset = next((r for r in profile["User"]["Assets"] if r["Id"] == item), None)
            if asset is None:
                asset = {"Id": item, "Amount": 0, "Spent": -1, "MaxAdj": 0, "NextCharge": None}
                profile["User"]["Assets"].append(asset)
            asset["Amount"] = 17
        self.save_profile(profile)

    def write_debug_catalog(self):
        self.debug_path.write_text(json.dumps(self.debug_catalog))

    def call(self, body=None, route=ROUTE, sequence=61, now=NOW):
        return super().call(body, route, sequence, now)

    def test_one_collection_grants_exact_mastery_without_touching_other_assets_or_levels(self):
        profile = self.store.account.profile()
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        response = self.call()
        notices = [{"ItemId": MASTERY_POINTS, "Amount": AMOUNT}]
        expected = copy.deepcopy(profile)
        self.asset(expected, MASTERY_POINTS)["Amount"] += AMOUNT
        expected["User"]["Cas"] += 1
        village = copy.deepcopy(self.initial)
        village["Buildings"][-1]["EndTime"] = NOW
        village["Cas"] += 1
        self.assertEqual(
            response, {"User": expected["User"], "UserLobbyVillage": village, "AddedItems": notices}
        )
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(
            preserved_read(self.db, "/lobby-village/enter")["UserLobbyVillage"], village
        )
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(self.source.read_bytes(), source)

    def test_minimum_interval_future_and_zero_anchors_do_not_grant_or_change_revisions(self):
        profile = self.store.account.profile()
        for index, anchor in enumerate((0, NOW - 59, NOW + 1)):
            village = copy.deepcopy(self.initial)
            village["Buildings"][-1]["EndTime"] = anchor
            self.save_village(village)
            self.assertEqual(self.call(sequence=61 + index)["AddedItems"], [])
            self.assertEqual(current_village(self.db), village)
            self.assertEqual(self.store.account.profile(), profile)

    def test_retry_returns_frozen_notice_and_current_state_after_later_collection(self):
        first = self.call()
        self.call(sequence=62, now=NOW + 60)
        profile = self.store.account.profile()
        village = current_village(self.db)
        self.debug_path.unlink()
        before = list(self.db.iterdump())
        self.assertEqual(
            self.call({}, now=NOW + 120),
            {
                "User": profile["User"],
                "UserLobbyVillage": village,
                "AddedItems": first["AddedItems"],
            },
        )
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.asset(profile, MASTERY_POINTS)["Amount"], 17 + 2 * AMOUNT)

    def test_reopening_reconnect_and_new_login_keep_used_clock_and_receipts(self):
        first = self.call()
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        profile = self.store.account.profile()
        self.assertEqual(self.call()["AddedItems"], [])
        self.assertEqual(self.store.account.profile(), profile)

    def test_no_implicit_reward_without_explicit_matching_debug_configuration(self):
        for key, value in (
            ("client", {}),
            ("debug_mastery_points", True),
            ("debug_mastery_points", 0),
            ("min_seconds", 0),
            ("portal_specs", [9001, 9001]),
            ("portal_specs", [True]),
        ):
            original = self.debug_catalog[key]
            self.debug_catalog[key] = value
            self.write_debug_catalog()
            self.reject_without_writes()
            self.debug_catalog[key] = original
        self.debug_path.write_text(" " * 4097)
        self.reject_without_writes()
        self.debug_path.unlink()
        self.reject_without_writes()

    def test_authentication_parameters_and_locked_mastery_reject_without_writes(self):
        for body in ({"amount": AMOUNT}, {"itemId": 70013}, [], False):
            self.reject_without_writes(body)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes()
        self.open_session()
        profile = self.store.account.profile()
        profile["User"]["GuardianMasteryLevel"] = -1
        self.save_profile(profile)
        self.reject_without_writes()

    def test_missing_ambiguous_or_unready_camp_and_invalid_anchors_reject(self):
        for field, value in (
            ("SpecId", 9999),
            ("Status", 0),
            ("Status", True),
            ("EndTime", "invalid"),
        ):
            village = copy.deepcopy(self.initial)
            village["Buildings"][-1][field] = value
            self.save_village(village)
            self.reject_without_writes()
        village = copy.deepcopy(self.initial)
        village["Buildings"].append(dict(village["Buildings"][-1], Id=10))
        self.save_village(village)
        self.reject_without_writes()

    def test_balance_overflow_rejects_the_entire_fixed_reward(self):
        profile = self.store.account.profile()
        self.asset(profile, MASTERY_POINTS)["Amount"] = INT_MAX - AMOUNT + 1
        self.save_profile(profile)
        self.reject_without_writes()

    def test_invalid_account_or_village_revisions_reject_without_advancing_camp(self):
        for kind in ("account", "village"):
            profile = self.store.account.profile()
            village = copy.deepcopy(self.initial)
            profile["User"]["Cas"] = 1
            if kind == "account":
                profile["User"]["Cas"] = MAX_REVISION
            else:
                village["Cas"] = MAX_REVISION
            self.save_profile(profile)
            self.save_village(village)
            self.reject_without_writes()

    def test_receipt_failure_rolls_back_points_camp_clock_and_both_revisions(self):
        self.db.execute(
            "CREATE TRIGGER fail_basecamp BEFORE INSERT ON basecamp_harvest_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.call()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_regular_collection_and_mastery_collection_preserve_each_others_state(self):
        regular = self.call(None, "/lobby-village/harvest-all", 51)
        mastery = self.call()
        self.assertEqual(
            mastery["UserLobbyVillage"]["LastHarvestTime"],
            regular["UserLobbyVillage"]["LastHarvestTime"],
        )
        before = list(self.db.iterdump())
        replay = self.call(None, "/lobby-village/harvest-all", 51)
        self.assertEqual(replay["User"], mastery["User"])
        self.assertEqual(replay["UserLobbyVillage"], mastery["UserLobbyVillage"])
        self.assertEqual(replay["AddedItems"], regular["AddedItems"])
        self.assertEqual(list(self.db.iterdump()), before)

    def test_changing_debug_amount_affects_only_new_valid_collections(self):
        first = self.call()
        self.debug_catalog["debug_mastery_points"] = 7
        self.write_debug_catalog()
        self.assertEqual(self.call(), first)
        second = self.call(sequence=62, now=NOW + 60)
        self.assertEqual(second["AddedItems"], [{"ItemId": MASTERY_POINTS, "Amount": 7}])
        self.assertEqual(
            self.asset(self.store.account.profile(), MASTERY_POINTS)["Amount"], 17 + AMOUNT + 7
        )
