# SPDX-License-Identifier: Apache-2.0
"""Inventory protection batches preserve item values, resources and later choices."""

import copy
import sqlite3
import unittest

from guardian_tales.accounts.account import AccountStore
from guardian_tales.inventory.item_lock import INVENTORIES, LOCK, MAX_BATCH, UNLOCK
from guardian_tales.inventory.items import inventory_item
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import MAX_REVISION
from tests.village.test_village_harvest import NOW, VillageFixture


class ItemLockTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        profile = self.store.account.profile()
        profile["User"]["ItemMiscs"].append(inventory_item(31, 201))
        stack = inventory_item(41, 301)
        stack["Amount"] = 12
        profile["User"]["ItemStackables"].append(stack)
        self.target(profile).update(
            Locked=True,
            Experience=555,
            LimitBreaks=5,
            Options=[dict(OptionId=2, Level=12, Locked=True, OptionSource=0)],
            EngraveOptions=[dict(OptionId=901, Level=2)],
            PreservedMetadata={"Value": 7},
        )
        profile["User"]["ItemIdCounter"] = 50
        self.save_profile(profile)
        self.request = {"itemIndexes": [1]}

    def call(self, body=None, route=UNLOCK, sequence=2301, now=NOW):
        return super().call(body, route, sequence, now)

    def target(self, profile):
        return profile["User"]["ItemWeapons"][0]

    def reject(self, body, route=UNLOCK, sequence=2301):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route, sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_observed_unlock_changes_only_protection_and_one_user_revision(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.target(expected)["Locked"] = False
        expected["User"]["Cas"] += 1
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        source = self.source.read_bytes()
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )

    def test_lock_and_unlock_mixed_inventory_batch_preserve_options_and_equipment(self):
        before = self.store.account.profile()
        request = {"itemIndexes": [41, 1, 31]}
        for sequence, route, locked in ((2301, LOCK, True), (2302, UNLOCK, False)):
            expected = copy.deepcopy(before)
            for key in INVENTORIES:
                for row in expected["User"][key]:
                    if row["Id"] in request["itemIndexes"]:
                        row["Locked"] = locked
            expected["User"]["Cas"] += 1
            self.assertEqual(self.call(request, route, sequence), {"User": expected["User"]})
            self.assertEqual(self.store.account.profile(), expected)
            before = expected

    def test_old_canonical_retry_returns_current_locks_values_and_balances(self):
        request = {"itemIndexes": [1, 31]}
        self.call(request)
        self.call(request, LOCK, 2302)
        current = self.store.account.profile()
        self.target(current)["Options"][0]["Level"] = 11
        current["User"]["Assets"][0]["Amount"] += 17
        self.save_profile(current)
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"itemIndexes": [31, 1]}), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.reject(request, LOCK)
        self.reject({"itemIndexes": [1]})

    def test_replay_does_not_resurrect_a_target_removed_by_a_later_operation(self):
        self.call(self.request)
        current = self.store.account.profile()
        current["User"]["ItemWeapons"].pop(0)
        self.save_profile(current)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject(self.request, sequence=2302)

    def test_reopen_reconnect_and_new_login_keep_saved_flag_and_receipts(self):
        first = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        profile = self.store.account.profile()
        self.assertEqual(self.call(self.request), {"User": profile["User"]})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM item_lock_requests").fetchone(), (2,)
        )

    def test_noop_at_revision_ceiling_records_request_without_changing_profile(self):
        current = self.store.account.profile()
        current["User"]["Cas"] = MAX_REVISION
        self.save_profile(current)
        self.assertEqual(self.call(self.request, LOCK), {"User": current["User"]})
        self.assertEqual(self.store.account.profile(), current)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM item_lock_requests").fetchone(), (1,)
        )
        self.reject(self.request, sequence=2302)

    def test_last_revision_is_allowed_and_retry_does_not_overflow(self):
        current = self.store.account.profile()
        current["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(current)
        self.call(self.request)
        current = self.store.account.profile()
        self.assertEqual(current["User"]["Cas"], MAX_REVISION)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject(self.request, LOCK, 2302)

    def test_unknown_inventory_ids_are_not_spec_ids_and_batches_are_all_or_nothing(self):
        for ids in ([101], [999], [1, 999], [1, 201]):
            with self.subTest(ids=ids):
                self.reject({"itemIndexes": ids})

    def test_exact_schema_integer_ids_batch_bounds_and_authentication(self):
        for body in (
            None,
            {},
            [],
            {"itemIndexes": None},
            {"itemIndexes": 1},
            {"itemIndexes": "1"},
            {"ItemId": 1},
            {"itemIndexes": []},
            {"itemIndexes": [True]},
            {"itemIndexes": [1.0]},
            {"itemIndexes": ["1"]},
            {"itemIndexes": [0]},
            {"itemIndexes": [-1]},
            {"itemIndexes": [0x80000000]},
            {"itemIndexes": [1, 1]},
            {"itemIndexes": list(range(1, MAX_BATCH + 2))},
            dict(self.request, Extra=True),
        ):
            with self.subTest(body=body):
                self.reject(body)
        for operation in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.change_item_locks(self.request, operation, UNLOCK)
            self.assertEqual(list(self.db.iterdump()), before)
        with self.assertRaises(ValueError):
            self.store.account.change_item_locks(self.request, "invalid-route", "/item/sell")
        self.session = BootstrapSession(self.store)
        self.reject(self.request)

    def test_fresh_completed_account_works_but_unfinished_prologue_rejects(self):
        with sqlite3.connect(":memory:") as db:
            account = AccountStore(db, self.references)
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.change_item_locks(self.request, "early", LOCK)
            self.assertEqual(list(db.iterdump()), before)
        with self.db:
            self.db.execute("DELETE FROM imported_account")
            self.db.execute("INSERT INTO prologue_selection VALUES(1,?,?)", ("Test", "{}"))
        self.call(self.request)
        self.assertFalse(self.target(self.store.account.profile())["Locked"])

    def test_invalid_saved_inventories_and_duplicate_ids_reject_without_writes(self):
        original = self.store.account.profile()
        for key in INVENTORIES:
            current = copy.deepcopy(original)
            current["User"][key] = None
            self.save_profile(current)
            self.reject(self.request)
        current = copy.deepcopy(original)
        current["User"]["ItemMiscs"].append(copy.deepcopy(self.target(current)))
        self.save_profile(current)
        self.reject(self.request)
        current = copy.deepcopy(original)
        current["User"]["ItemWeapons"][1]["Id"] = True
        self.save_profile(current)
        self.reject(self.request)

    def test_invalid_target_flags_amount_identity_and_revision_are_rejected(self):
        original = self.store.account.profile()
        for key, value in (
            ("Locked", 1),
            ("Locked", None),
            ("Amount", 0),
            ("Amount", True),
            ("ItemId", 0),
            ("ItemId", True),
        ):
            current = copy.deepcopy(original)
            self.target(current)[key] = value
            self.save_profile(current)
            self.reject(self.request)
        for key, value in (
            ("Id", 0),
            ("Id", True),
            ("Cas", -1),
            ("Cas", True),
            ("Cas", MAX_REVISION + 1),
        ):
            current = copy.deepcopy(original)
            current["User"][key] = value
            self.save_profile(current)
            self.reject(self.request)

    def test_item_protection_needs_no_option_catalog_and_keeps_pending_proposals(self):
        # Protection does not recalculate, constrain or roll any item stat/option.
        with self.db:
            self.db.execute(
                "INSERT INTO weapon_option_proposals VALUES(?,?,?,?,?,?)",
                (1, "synthetic-proposal", 101, "[]", "[]", "{}"),
            )
        before = self.store.account.profile()
        self.target(before)["Options"][0]["Level"] = 5000
        self.save_profile(before)
        pending = self.db.execute("SELECT * FROM weapon_option_proposals").fetchall()
        self.call(self.request)
        expected = copy.deepcopy(before)
        self.target(expected)["Locked"] = False
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT * FROM weapon_option_proposals").fetchall(), pending
        )

    def test_receipt_and_profile_failures_roll_back_entire_batch(self):
        for table, event in (("local_account", "UPDATE"), ("item_lock_requests", "INSERT")):
            with self.subTest(table=table):
                self.db.execute(
                    f"CREATE TRIGGER reject_lock BEFORE {event} ON {table} "
                    "BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
                )
                self.db.commit()
                before = list(self.db.iterdump())
                with self.assertRaises(sqlite3.IntegrityError):
                    self.call({"itemIndexes": [1, 31, 41]}, LOCK)
                self.assertEqual(list(self.db.iterdump()), before)
                self.db.execute("DROP TRIGGER reject_lock")
                self.db.commit()

    def test_full_bounded_batch_changes_one_revision_and_no_other_fields(self):
        current = self.store.account.profile()
        current["User"]["ItemWeapons"].extend(
            inventory_item(1000 + i, 101) for i in range(MAX_BATCH)
        )
        self.save_profile(current)
        request = {"itemIndexes": list(range(1000, 1000 + MAX_BATCH))}
        expected = copy.deepcopy(current)
        for row in expected["User"]["ItemWeapons"]:
            if row["Id"] in request["itemIndexes"]:
                row["Locked"] = True
        expected["User"]["Cas"] += 1
        self.assertEqual(self.call(request, LOCK), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
