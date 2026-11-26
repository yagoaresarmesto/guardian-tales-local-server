# SPDX-License-Identifier: Apache-2.0
"""Source-preserving jewel batches grant catalog powder once per request identity."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.items import inventory_item
from guardian_tales.jewel_decompose import POWDER, ROUTE
from guardian_tales.protocol import PacketError
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import INT_MAX, MAX_REVISION
from tests.test_snapshots import request as packet
from tests.test_village_harvest import NOW, VillageFixture


class JewelDecomposeTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.jewel_catalog = {
            "client": CLIENT,
            "preserve_sources": True,
            "powder_asset_id": POWDER,
            "grade_yields": {"1": 7, "2": 19},
            "jewels": {"501": 1, "502": 2},
        }
        self.jewel_path = self.references / "jewel_decompose_mock_catalog.json"
        self.write_jewels()
        profile = self.store.account.profile()
        for inventory_id, spec_id in ((50, 501), (51, 502)):
            item = inventory_item(inventory_id, spec_id)
            item["Amount"] = 10
            profile["User"]["ItemStackables"].append(item)
        profile["User"]["ItemIdCounter"] = 51
        self.powder(profile).update(Amount=100, Spent=32, MaxAdj=4, NextCharge=None)
        profile["User"]["ItemWeapons"][0]["JewelSlots"] = [{"ItemId": 501, "Synthetic": True}]
        self.save_profile(profile)
        self.request = {"Jewels": {"50": 3, "51": 2}}

    def write_jewels(self):
        self.jewel_path.write_text(json.dumps(self.jewel_catalog))

    def call(self, body=None, route=ROUTE, sequence=511, now=NOW):
        return super().call(body, route, sequence, now)

    def powder(self, profile):
        return self.asset(profile, POWDER)

    def test_mixed_grade_batch_grants_exact_powder_and_preserves_sources_and_all_other_fields(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.powder(expected)["Amount"] += 59
        expected["User"]["Cas"] += 1
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT powder FROM jewel_decompose_requests").fetchall(), [(59,)]
        )

    def test_twenty_catalog_grades_use_their_yields_without_spec_ranges_or_selected_type_limits(
        self,
    ):
        self.jewel_catalog["grade_yields"] = {str(i): i * 3 for i in range(1, 21)}
        self.jewel_catalog["jewels"] = {str(800 + i): i for i in range(1, 21)}
        self.write_jewels()
        before = self.store.account.profile()
        jewels = {}
        for grade in range(1, 21):
            item = inventory_item(100 + grade, 800 + grade)
            item["Amount"] = 2
            before["User"]["ItemStackables"].append(item)
            jewels[str(item["Id"])] = 2
        self.save_profile(before)
        expected = copy.deepcopy(before)
        self.powder(expected)["Amount"] += 1260
        expected["User"]["Cas"] += 1
        self.call({"Jewels": jewels})
        self.assertEqual(self.store.account.profile(), expected)

    def test_new_sequence_can_repeat_the_free_operation_without_consuming_any_jewel(self):
        before = self.store.account.profile()
        self.call(self.request)
        self.call(self.request, sequence=512)
        expected = copy.deepcopy(before)
        self.powder(expected)["Amount"] += 118
        expected["User"]["Cas"] += 2
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM jewel_decompose_requests").fetchone(), (2,)
        )

    def test_exact_retry_after_reopen_catalog_removal_and_later_edits_returns_current_user(self):
        self.call(self.request)
        profile = self.store.account.profile()
        self.powder(profile)["Amount"] -= 10
        profile["User"]["ItemStackables"][-1].update(Amount=0, Locked=True)
        profile["User"]["ItemWeapons"][0]["JewelSlots"] = [{"ItemId": 502}]
        self.save_profile(profile)
        self.open_session(reconnect=True)
        self.jewel_path.unlink()
        before = list(self.db.iterdump())
        reordered = {"Jewels": {"51": 2, "50": 3}}
        self.assertEqual(self.call(reordered), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes({"Jewels": {"50": 2}})
        with self.assertRaises(ValueError):
            self.store.account.decompose_jewels(self.request, "new-without-catalog")

    def test_malformed_requests_quantities_and_canonical_ids_cannot_change_the_account(self):
        for body in (
            None,
            {},
            {"Jewels": {}},
            {"Jewels": []},
            {"Jewels": {"50": True}},
            {"Jewels": {"50": 0}},
            {"Jewels": {"50": -1}},
            {"Jewels": {"50": 1.0}},
            {"Jewels": {"050": 1}},
            {"Jewels": {"+50": 1}},
            {"Jewels": {"50": 11}},
            {"Jewels": {"50": 1}, "Extra": True},
            {"Jewels": {str(i): 1 for i in range(1, 258)}},
        ):
            with self.subTest(body=str(body)[:50]):
                self.reject_without_writes(body)
        for identity in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.decompose_jewels(self.request, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_unknown_nonstackable_locked_and_ambiguous_sources_are_guarded_atomically(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"]["ItemStackables"][-1].update(ItemId=999),
            lambda p: p["User"]["ItemStackables"][-1].update(Locked=True),
            lambda p: p["User"]["ItemStackables"][-1].update(Locked=None),
            lambda p: p["User"]["ItemStackables"][-1].update(Amount=-1),
            lambda p: p["User"]["ItemMiscs"].append(p["User"]["ItemStackables"].pop()),
            lambda p: p["User"]["ItemWeapons"].append(
                copy.deepcopy(p["User"]["ItemStackables"][-1])
            ),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        self.save_profile(original)
        self.reject_without_writes({"Jewels": {"501": 1}})
        self.reject_without_writes({"Jewels": {"50": 1, "999": 1}})

    def test_missing_mismatched_or_malformed_catalog_cannot_grant_powder(self):
        original = copy.deepcopy(self.jewel_catalog)
        self.jewel_path.unlink()
        self.reject_without_writes(self.request)
        for mutate in (
            lambda c: c.update(client={}),
            lambda c: c.update(preserve_sources=False),
            lambda c: c.update(powder_asset_id=70003),
            lambda c: c.update(jewels={}),
            lambda c: c["jewels"].update({"502": 3}),
            lambda c: c["jewels"].update({"0502": 2}),
            lambda c: c["jewels"].update({"502": True}),
            lambda c: c["grade_yields"].update({"2": -1}),
            lambda c: c["grade_yields"].update({"2": True}),
            lambda c: c["grade_yields"].update({"02": 19}),
        ):
            self.jewel_catalog = copy.deepcopy(original)
            mutate(self.jewel_catalog)
            self.write_jewels()
            self.reject_without_writes(self.request)

    def test_overflow_missing_duplicate_and_invalid_powder_or_revision_rejects_without_writes(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: self.powder(p).update(Amount=INT_MAX - 58),
            lambda p: self.powder(p).update(Amount=True),
            lambda p: p["User"].update(Cas=MAX_REVISION),
            lambda p: p["User"].update(Cas=True),
            lambda p: p["User"]["Assets"].append(copy.deepcopy(self.powder(p))),
            lambda p: p["User"].update(
                Assets=[a for a in p["User"]["Assets"] if a["Id"] != POWDER]
            ),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        self.save_profile(original)
        self.jewel_catalog["grade_yields"]["2"] = INT_MAX
        self.write_jewels()
        self.reject_without_writes(self.request)

    def test_late_profile_or_receipt_failure_rolls_back_reward_revision_and_receipt(self):
        for table, action in (("local_account", "UPDATE"), ("jewel_decompose_requests", "INSERT")):
            self.db.execute(
                f"CREATE TRIGGER reject_jewel BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.store.account.decompose_jewels(self.request, "rollback")
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_jewel")
            self.db.commit()

    def test_packet_requires_authentication_and_reconnect_does_not_pay_twice(self):
        with self.assertRaises(PacketError):
            BootstrapSession(self.store).handle(packet(ROUTE, self.request))
        self.call(self.request)
        before = self.store.account.profile()
        self.open_session(reconnect=True)
        writes = self.db.total_changes
        self.assertEqual(self.call(self.request), {"User": before["User"]})
        self.assertEqual(self.db.total_changes, writes)
        self.open_session(reconnect=False)
        self.call(self.request)
        after = self.store.account.profile()
        self.assertEqual(self.powder(after)["Amount"], self.powder(before)["Amount"] + 59)
        self.assertEqual(after["User"]["ItemStackables"], before["User"]["ItemStackables"])

    def test_unfinished_fresh_account_cannot_use_the_explicit_mock(self):
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.references).account
            before = account.profile()
            with self.assertRaises(ValueError):
                account.decompose_jewels(self.request, "unfinished")
            self.assertEqual(account.profile(), before)
