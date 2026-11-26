# SPDX-License-Identifier: Apache-2.0
"""Equipment extraction grants no metal and shares safe, atomic removal with sales."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.accounts.account import AccountStore
from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.inventory.item_extract import ROUTE
from guardian_tales.inventory.item_lock import MAX_BATCH
from guardian_tales.inventory.item_sell import ROUTE as SELL
from guardian_tales.inventory.items import inventory_item
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import MAX_REVISION
from guardian_tales.summons.weapon_summon import MAGIC_METAL
from tests.village.test_village_harvest import NOW, VillageFixture


class ItemExtractTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.catalog_path = self.references / "weapon_enhance_debug_catalog.json"
        self.catalog = {
            "client": CLIENT,
            "free": True,
            "level_total_exps": [100, 300],
            "weapons": {"101": 4, "102": 3, "103": 5},
            "hammer_exp": {"501": 10},
            "limit_break_coef": 1,
            "max_limit_breaks": 5,
            "myth_coef": 2,
        }
        self.catalog_path.write_text(json.dumps(self.catalog))
        profile = self.store.account.profile()
        profile["User"]["ItemWeapons"].extend(inventory_item(i, 101) for i in (11, 12, 13))
        profile["User"]["ItemMiscs"].append(inventory_item(31, 101))
        profile["User"]["ItemStackables"].append(inventory_item(41, 101))
        self.asset(profile, MAGIC_METAL).update(Amount=123, Spent=-7)
        profile["User"]["ItemIdCounter"] = 50
        self.save_profile(profile)
        self.request = {"ItemIds": [11, 12]}

    def call(self, body=None, route=ROUTE, sequence=2801, now=NOW):
        return super().call(body, route, sequence, now)

    def item(self, profile, ident=11):
        return next(row for row in profile["User"]["ItemWeapons"] if row["Id"] == ident)

    def reject(self, body, route=ROUTE, sequence=2801):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route, sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def expected(self, profile, ids):
        result = copy.deepcopy(profile)
        result["User"]["ItemWeapons"] = [
            r for r in result["User"]["ItemWeapons"] if r["Id"] not in ids
        ]
        result["User"]["Cas"] += 1
        return result

    def test_observed_two_item_extraction_changes_only_selected_rows_and_one_revision(self):
        before = self.store.account.profile()
        expected = self.expected(before, self.request["ItemIds"])
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM item_sell_requests").fetchone(), (0,)
        )
        self.assertEqual(
            self.db.execute("SELECT request FROM item_extract_requests").fetchone(),
            ('{"ItemIds":[11,12]}',),
        )

    def test_canonical_old_retry_preserves_later_stats_balances_and_inventory_without_catalog(self):
        self.call(self.request)
        current = self.store.account.profile()
        self.item(current, 13)["Experience"] = 99
        current["User"]["Assets"][0]["Amount"] += 17
        self.save_profile(current)
        self.catalog_path.unlink()
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"ItemIds": [12, 11]}), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.reject({"ItemIds": [13]})

    def test_sale_and_extraction_cannot_reuse_one_operation_identity_in_either_direction(self):
        original = self.store.account.profile()
        for first_route, first_body, second_route, second_body in (
            (SELL, {"SellItems": {"11": 1}}, ROUTE, {"ItemIds": [12]}),
            (ROUTE, {"ItemIds": [11]}, SELL, {"SellItems": {"12": 1}}),
        ):
            self.save_profile(original)
            with self.db:
                self.db.execute("DELETE FROM item_sell_requests")
                self.db.execute("DELETE FROM item_extract_requests")
            self.call(first_body, first_route)
            self.reject(second_body, second_route)
            self.call(second_body, second_route, 2802)
            expected = self.expected(original, [11, 12])
            expected["User"]["Cas"] += 1
            self.assertEqual(self.store.account.profile(), expected)

    def test_reopen_reconnect_and_new_login_keep_removed_items_and_receipts(self):
        first = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.reject(self.request)
        self.assertEqual(self.store.account.profile()["User"], first["User"])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM item_extract_requests").fetchone(), (1,)
        )

    def test_malformed_schema_ids_duplicates_and_batch_bounds_reject_without_writes(self):
        for body in (
            None,
            [],
            {},
            {"ItemIds": []},
            {"ItemIds": "11"},
            {"ItemIds": [11, 11]},
            {"ItemIds": [11], "Reward": 0},
            {"ItemIds": list(range(1000, 1001 + MAX_BATCH))},
        ):
            self.reject(body)
        for ident in (True, False, 0, -1, 1.0, "11", None, 2147483648):
            self.reject({"ItemIds": [11, ident]})
        self.reject({"ItemIds": [101]})

    def test_whole_batch_rejects_locked_missing_wrong_inventory_or_non_epic_targets(self):
        original = self.store.account.profile()
        for field, value in (
            ("Locked", True),
            ("Locked", 0),
            ("Amount", 0),
            ("Amount", 2),
            ("ItemId", 102),
            ("ItemId", 103),
            ("ItemId", 999),
        ):
            profile = copy.deepcopy(original)
            self.item(profile, 12)[field] = value
            self.save_profile(profile)
            self.reject(self.request)
        self.save_profile(original)
        for ident in (31, 41, 9999):
            self.reject({"ItemIds": [11, ident]})

    def test_equipped_extraction_clears_only_selected_slots_and_preserves_all_assets(self):
        current = self.store.account.profile()
        current["User"]["Characters"][0].update(Weapon1=11, Accessory1=12, Weapon2=13)
        self.save_profile(current)
        expected = self.expected(current, self.request["ItemIds"])
        expected["User"]["Characters"][0].update(Weapon1=None, Accessory1=None)
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)

    def test_shared_training_preset_and_socket_guards_apply_to_extraction(self):
        original = self.store.account.profile()
        profile = copy.deepcopy(original)
        profile["User"]["TrainingSlots"] = {"2": {"ItemId": 11}}
        self.save_profile(profile)
        self.reject(self.request)
        profile = copy.deepcopy(original)
        self.item(profile)["JewelSlots"] = [280020]
        self.save_profile(profile)
        self.reject(self.request)
        self.save_profile(original)
        with self.db:
            self.db.execute(
                "INSERT INTO party_preset_state VALUES(1,?)",
                (json.dumps({"Presets": [{"Characters": [{"Weapon1": 11}]}]}),),
            )
        self.reject(self.request)

    def test_new_extraction_needs_matching_catalog_but_sales_remain_catalog_free(self):
        self.catalog_path.unlink()
        self.reject(self.request)
        self.call({"SellItems": {"13": 1}}, SELL)
        for key, value in (("client", {}), ("free", False)):
            catalog = copy.deepcopy(self.catalog)
            catalog[key] = value
            self.catalog_path.write_text(json.dumps(catalog))
            self.reject(self.request, sequence=2802)

    def test_pending_proposals_removed_only_for_extracted_targets(self):
        with self.db:
            for ident in (11, 13):
                self.db.execute(
                    "INSERT INTO weapon_option_proposals VALUES(?,?,?,?,?,?)",
                    (ident, "synthetic", 101, "[]", "[]", "{}"),
                )
                self.db.execute(
                    "INSERT INTO relic_option_proposals VALUES(?,?,?,?,?,?,?)",
                    (ident, "synthetic", 101, 1, "[]", "[]", "{}"),
                )
        self.call(self.request)
        for table in ("weapon_option_proposals", "relic_option_proposals"):
            self.assertEqual(self.db.execute(f"SELECT item_id FROM {table}").fetchall(), [(13,)])

    def test_receipt_profile_and_cleanup_failures_roll_back_entire_extraction(self):
        with self.db:
            self.db.execute(
                "INSERT INTO weapon_option_proposals VALUES(?,?,?,?,?,?)",
                (11, "synthetic", 101, "[]", "[]", "{}"),
            )
        for table, event in (
            ("local_account", "UPDATE"),
            ("item_extract_requests", "INSERT"),
            ("weapon_option_proposals", "DELETE"),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_extract BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):
                self.call(self.request)
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_extract")
            self.db.commit()

    def test_fresh_completed_account_works_and_prologue_authentication_are_required(self):
        with sqlite3.connect(":memory:") as db:
            account = AccountStore(db, self.references)
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.extract_items(self.request, "early")
            self.assertEqual(list(db.iterdump()), before)
        with self.db:
            self.db.execute("DELETE FROM imported_account")
            self.db.execute("INSERT INTO prologue_selection VALUES(1,?,?)", ("Test", "{}"))
        self.call(self.request)
        self.session = BootstrapSession(self.store)
        self.reject({"ItemIds": [13]}, sequence=2802)

    def test_revision_ceiling_and_operation_identity_are_checked_without_repeat_writes(self):
        for operation in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.extract_items(self.request, operation)
            self.assertEqual(list(self.db.iterdump()), before)
        self.call(self.request)
        current = self.store.account.profile()
        current["User"]["Cas"] = MAX_REVISION
        self.save_profile(current)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject({"ItemIds": [13]}, sequence=2802)

    def test_existing_sale_receipt_format_replays_unchanged_after_extraction_table_is_added(self):
        body = {"SellItems": {"13": 1}}
        with self.db:
            self.db.execute(
                "INSERT INTO item_sell_requests VALUES(?,?)", ("old-sale", '{"SellItems":{"13":1}}')
            )
        current = self.store.account.profile()
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.store.account.sell_items(body, "old-sale"), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_full_bounded_batch_preserves_all_other_gear_assets_and_allocation_counter(self):
        current = self.store.account.profile()
        current["User"]["ItemWeapons"].extend(
            inventory_item(1000 + i, 101) for i in range(MAX_BATCH)
        )
        current["User"]["ItemIdCounter"] = 2000
        self.save_profile(current)
        ids = list(range(1000, 1000 + MAX_BATCH))
        expected = self.expected(current, ids)
        self.assertEqual(self.call({"ItemIds": ids}), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
