# SPDX-License-Identifier: Apache-2.0
"""No-gold sales preserve unrelated progress and cannot debit twice."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.item_lock import INVENTORIES, MAX_BATCH
from guardian_tales.item_sell import EQUIPMENT_FIELDS, ROUTE
from guardian_tales.items import inventory_item
from guardian_tales.protocol import PacketError
from guardian_tales.village import MAX_REVISION
from tests.village.test_village_harvest import NOW, VillageFixture


class ItemSellTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        profile = self.store.account.profile()
        profile["User"]["ItemWeapons"].extend(inventory_item(i, 101) for i in range(11, 19))
        profile["User"]["ItemMiscs"].append(inventory_item(31, 201))
        stack = inventory_item(41, 301)
        stack["Amount"] = 12
        profile["User"]["ItemStackables"].append(stack)
        profile["User"]["ItemIdCounter"] = 50
        self.save_profile(profile)
        self.request = {"SellItems": {str(i): 1 for i in range(11, 19)}}

    def call(self, body=None, route=ROUTE, sequence=2601, now=NOW):
        return super().call(body, route, sequence, now)

    def item(self, profile, ident=11):
        return next(r for k in INVENTORIES for r in profile["User"][k] if r["Id"] == ident)

    def reject(self, body, sequence=2601):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def expected_sale(self, before, request):
        expected = copy.deepcopy(before)
        for key in INVENTORIES:
            for row in expected["User"][key]:
                row["Amount"] -= request["SellItems"].get(str(row["Id"]), 0)
            expected["User"][key] = [r for r in expected["User"][key] if r["Amount"]]
        expected["User"]["Cas"] += 1
        return expected

    def test_eight_item_batch_removes_only_selected_rows_without_gold_or_rewards(self):
        before = self.store.account.profile()
        expected = self.expected_sale(before, self.request)
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM item_sell_requests").fetchone(), (1,)
        )

    def test_mixed_inventories_partial_stack_and_depleted_row_removal(self):
        request = {"SellItems": {"11": 1, "31": 1, "41": 5}}
        expected = self.expected_sale(self.store.account.profile(), request)
        self.assertEqual(self.call(request), {"User": expected["User"]})
        self.assertEqual(self.item(self.store.account.profile(), 41)["Amount"], 7)
        rest = {"SellItems": {"41": 7}}
        expected = self.expected_sale(expected, rest)
        self.assertEqual(self.call(rest, sequence=2602), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)

    def test_canonical_retry_preserves_later_quantities_locks_and_balances_without_writes(self):
        request = {"SellItems": {"31": 1, "41": 3}}
        self.call(request)
        self.call({"SellItems": {"41": 2}}, sequence=2602)
        current = self.store.account.profile()
        self.item(current, 41)["Locked"] = True
        current["User"]["Assets"][0]["Amount"] += 19
        self.save_profile(current)
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"SellItems": {"41": 3, "31": 1}}), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.reject({"SellItems": {"31": 1, "41": 4}})

    def test_delayed_retry_does_not_remove_a_later_recreated_inventory_row(self):
        self.call(self.request)
        current = self.store.account.profile()
        recreated = inventory_item(11, 202)
        recreated["Locked"] = True
        current["User"]["ItemWeapons"].append(recreated)
        current["User"]["Characters"][0]["Weapon1"] = 11
        self.save_profile(current)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_reopen_reconnect_and_new_login_preserve_debits_and_receipts(self):
        request = {"SellItems": {"41": 3}}
        first = self.call(request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(request), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        expected = self.expected_sale(self.store.account.profile(), request)
        self.assertEqual(self.call(request), {"User": expected["User"]})
        self.assertEqual(self.item(self.store.account.profile(), 41)["Amount"], 6)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM item_sell_requests").fetchone(), (2,)
        )

    def test_new_request_cannot_resell_removed_items_or_overdraw_partial_stacks(self):
        self.call(self.request)
        self.reject(self.request, sequence=2602)
        self.reject({"SellItems": {"41": 13}}, sequence=2603)
        self.reject({"SellItems": {"11": 1, "41": 2}}, sequence=2604)

    def test_one_locked_missing_ambiguous_or_insufficient_target_rejects_entire_batch(self):
        original = self.store.account.profile()
        for field, value in (
            ("Locked", True),
            ("Locked", 0),
            ("Amount", 0),
            ("Amount", True),
            ("ItemId", 0),
        ):
            current = copy.deepcopy(original)
            self.item(current, 18)[field] = value
            self.save_profile(current)
            self.reject(self.request)
        self.save_profile(original)
        self.reject({"SellItems": {"11": 1, "99999": 1}})
        self.reject({"SellItems": {"11": 1, "18": 2}})
        current = copy.deepcopy(original)
        current["User"]["ItemMiscs"].append(copy.deepcopy(self.item(current)))
        self.save_profile(current)
        self.reject(self.request)

    def test_sold_equipment_clears_only_its_nullable_character_slot_without_rewards(self):
        original = self.store.account.profile()
        for index, field in enumerate(sorted(EQUIPMENT_FIELDS)):
            current = copy.deepcopy(original)
            current["User"]["Characters"][0][field] = 11
            self.save_profile(current)
            expected = self.expected_sale(current, self.request)
            expected["User"]["Characters"][0][field] = None
            self.assertEqual(
                self.call(self.request, sequence=2700 + index), {"User": expected["User"]}
            )
            self.assertEqual(self.store.account.profile(), expected)

    def test_equipment_costumes_remain_protected_without_an_unequip_contract(self):
        original = self.store.account.profile()
        current = copy.deepcopy(original)
        current["User"]["Characters"][0]["EquipCostumes"] = {"1": 11}
        self.save_profile(current)
        self.reject(self.request)

    def test_all_holders_are_cleared_but_unselected_equipment_and_hero_progress_remain(self):
        current = self.store.account.profile()
        hero = copy.deepcopy(current["User"]["Characters"][0])
        hero.update(Id=2, Experience=765, Weapon1=11, Weapon2=13)
        current["User"]["Characters"].append(hero)
        current["User"]["CharacterIdCounter"] = 2
        current["User"]["Characters"][0]["Weapon1"] = 11
        self.save_profile(current)
        request = {"SellItems": {"11": 1}}
        expected = self.expected_sale(current, request)
        for row in expected["User"]["Characters"]:
            row["Weapon1"] = None
        self.assertEqual(self.call(request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)

    def test_partial_stack_sale_keeps_assignment_until_its_final_quantity_is_removed(self):
        current = self.store.account.profile()
        current["User"]["Characters"][0]["Costume"] = 41
        self.save_profile(current)
        request = {"SellItems": {"41": 3}}
        expected = self.expected_sale(current, request)
        self.assertEqual(self.call(request), {"User": expected["User"]})
        final = {"SellItems": {"41": 9}}
        expected = self.expected_sale(expected, final)
        expected["User"]["Characters"][0]["Costume"] = None
        self.assertEqual(self.call(final, sequence=2602), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)

    def test_rejected_batch_does_not_unequip_or_remove_any_of_its_valid_targets(self):
        current = self.store.account.profile()
        current["User"]["Characters"][0]["Weapon1"] = 11
        self.item(current, 18)["Locked"] = True
        self.save_profile(current)
        self.reject(self.request)

    def test_captured_and_latest_preset_equipment_references_are_protected(self):
        captured = json.loads(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        )
        captured["/preset/get-presets"]["value"] = {
            "UserPartyPreset2": {"Presets": [{"Characters": [{"Weapon1": 11}]}]}
        }
        with self.db:
            self.db.execute("UPDATE imported_account SET startup_reads=?", (json.dumps(captured),))
        self.reject(self.request)
        with self.db:
            self.db.execute(
                "INSERT INTO party_preset_state VALUES(1,?)", (json.dumps({"Presets": []}),)
            )
        expected = self.expected_sale(self.store.account.profile(), self.request)
        self.assertEqual(self.call(self.request), {"User": expected["User"]})

    def test_training_assignments_remain_protected_even_after_saved_cooldown(self):
        current = self.store.account.profile()
        current["User"]["TrainingSlots"] = {
            "2": {"ItemId": 11, "NextReactivateTime": "2000-01-01T00:00:00+00:00"}
        }
        self.save_profile(current)
        self.reject(self.request)

    def test_socketed_jewels_block_sale_but_empty_socket_arrays_do_not(self):
        original = self.store.account.profile()
        for slots in ([280020], {"0": 280020}, "280020"):
            current = copy.deepcopy(original)
            self.item(current)["JewelSlots"] = slots
            self.save_profile(current)
            self.reject(self.request)
        current = copy.deepcopy(original)
        self.item(current)["JewelSlots"] = [0, None]
        self.save_profile(current)
        self.assertEqual(
            self.call(self.request), {"User": self.expected_sale(current, self.request)["User"]}
        )

    def test_malformed_schema_ids_counts_and_batch_bound_are_rejected(self):
        for body in (
            None,
            [],
            {},
            {"SellItems": {}},
            {"SellItems": []},
            {"SellItems": {"11": 1}, "Gold": 0},
            {"SellItems": {str(1000 + i): 1 for i in range(MAX_BATCH + 1)}},
        ):
            self.reject(body)
        for key in ("0", "-1", "011", "+11", "1.0", "١١", "2147483648"):
            self.reject({"SellItems": {key: 1}})
        for count in (True, False, 0, -1, 1.0, "1", None, 2147483648):
            self.reject({"SellItems": {"11": count}})
        self.reject({"SellItems": {"101": 1}})

    def test_invalid_saved_inventory_and_use_references_reject_without_changes(self):
        original = self.store.account.profile()
        for field, value in (
            ("ItemWeapons", None),
            ("ItemMiscs", {}),
            ("ItemStackables", [None]),
            ("Characters", None),
            ("Characters", [None]),
            ("TrainingSlots", []),
            ("TrainingSlots", {"2": {"ItemId": True}}),
        ):
            current = copy.deepcopy(original)
            current["User"][field] = value
            self.save_profile(current)
            self.reject(self.request)
        current = copy.deepcopy(original)
        current["User"]["Characters"][0]["Weapon1"] = "11"
        self.save_profile(current)
        self.reject(self.request)

    def test_revision_ceiling_blocks_new_sale_but_not_saved_replay(self):
        self.call(self.request)
        current = self.store.account.profile()
        current["User"]["Cas"] = MAX_REVISION
        self.save_profile(current)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": current["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject({"SellItems": {"31": 1}}, sequence=2602)

    def test_authentication_prologue_and_operation_identity_are_required(self):
        for operation in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.sell_items(self.request, operation)
            self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            account = AccountStore(db, self.references)
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.sell_items(self.request, "early")
            self.assertEqual(list(db.iterdump()), before)
        self.session = BootstrapSession(self.store)
        self.reject(self.request)

    def test_fresh_completed_account_and_nullable_costume_map_support_sale(self):
        with self.db:
            self.db.execute("DELETE FROM imported_account")
            self.db.execute("INSERT INTO prologue_selection VALUES(1,?,?)", ("Test", "{}"))
        current = self.store.account.profile()
        current["User"]["Characters"][0]["EquipCostumes"] = None
        self.save_profile(current)
        self.assertEqual(
            self.call(self.request), {"User": self.expected_sale(current, self.request)["User"]}
        )

    def test_pending_proposals_removed_only_for_fully_sold_items(self):
        with self.db:
            for ident in (11, 12, 41):
                self.db.execute(
                    "INSERT INTO weapon_option_proposals VALUES(?,?,?,?,?,?)",
                    (ident, "synthetic", 101, "[]", "[]", "{}"),
                )
                self.db.execute(
                    "INSERT INTO relic_option_proposals VALUES(?,?,?,?,?,?,?)",
                    (ident, "synthetic", 101, 1, "[]", "[]", "{}"),
                )
        self.call({"SellItems": {"11": 1, "41": 2}})
        for table in ("weapon_option_proposals", "relic_option_proposals"):
            self.assertEqual(
                self.db.execute(f"SELECT item_id FROM {table} ORDER BY item_id").fetchall(),
                [(12,), (41,)],
            )

    def test_profile_receipt_and_proposal_failures_roll_back_every_debit(self):
        current = self.store.account.profile()
        current["User"]["Characters"][0]["Weapon1"] = 11
        self.save_profile(current)
        with self.db:
            self.db.execute(
                "INSERT INTO weapon_option_proposals VALUES(?,?,?,?,?,?)",
                (11, "synthetic", 101, "[]", "[]", "{}"),
            )
        for table, event in (
            ("local_account", "UPDATE"),
            ("item_sell_requests", "INSERT"),
            ("weapon_option_proposals", "DELETE"),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_sale BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):
                self.call(self.request)
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_sale")
            self.db.commit()

    def test_full_bounded_batch_preserves_counter_and_all_unselected_items(self):
        current = self.store.account.profile()
        current["User"]["ItemWeapons"].extend(
            inventory_item(1000 + i, 101) for i in range(MAX_BATCH)
        )
        current["User"]["ItemIdCounter"] = 2000
        self.save_profile(current)
        request = {"SellItems": {str(1000 + i): 1 for i in range(MAX_BATCH)}}
        expected = self.expected_sale(current, request)
        self.assertEqual(self.call(request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
