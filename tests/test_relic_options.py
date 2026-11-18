# SPDX-License-Identifier: Apache-2.0
"""Free relic group rolls, repeated IDs, persistent decisions and resource bounds."""

import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.items import inventory_item
from guardian_tales.protocol import PacketError
from guardian_tales.relic_options import APPLY, CHANGE
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import MAX_REVISION, current_village
from tests.test_village_harvest import NOW, VillageFixture


class RelicOptionTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        pools = {
            "1": [{"901": [2, 5], "902": [6, 8]}, {"901": [2, 5]}],
            "2": [{"903": [10, 12], "904": [20, 22]}, {"905": [480, 490]}],
        }
        self.relic_catalog = {"client": CLIENT, "free": True, "relics": {"701": pools}}
        self.relic_path = self.references / "relic_option_mock_catalog.json"
        self.write_relic_catalog()
        profile = self.store.account.profile()
        relic = inventory_item(70, 701)
        relic.update(
            Locked=True,
            JewelSlots=[123, 456],
            RelicOptions=[
                dict(OptionId=901, Level=4, Locked=False, OptionSource=1),
                dict(OptionId=901, Level=3, Locked=True, OptionSource=1),
                dict(OptionId=904, Level=21, Locked=False, OptionSource=2),
                dict(OptionId=905, Level=485, Locked=False, OptionSource=2),
            ],
        )
        profile["User"]["ItemMiscs"].append(relic)
        ticket = inventory_item(50, 501)
        ticket["Amount"] = 0
        profile["User"]["ItemStackables"].append(ticket)
        profile["User"]["ItemIdCounter"] = 70
        self.asset(profile, 70001).update(Amount=0, Spent=-42)
        self.save_profile(profile)
        self.request = {"ItemId": 70, "OptionType": 2}
        self.draw = patch("guardian_tales.relic_options.randbelow", return_value=0).start()
        self.addCleanup(patch.stopall)

    def write_relic_catalog(self):
        self.relic_path.write_text(json.dumps(self.relic_catalog))

    def call(self, body=None, route=CHANGE, sequence=191, now=NOW):
        return super().call(body, route, sequence, now)

    def apply(self, accept=True, sequence=192):
        return self.call({"ItemId": 70, "Apply": accept}, APPLY, sequence)

    def target(self, profile):
        return next(r for r in profile["User"]["ItemMiscs"] if r["Id"] == 70)

    def pending(self):
        return self.db.execute("SELECT * FROM relic_option_proposals").fetchall()

    def reject(self, body, route=CHANGE, sequence=191):
        dump = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route, sequence)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_generation_returns_sources_and_preserves_profile_currency_duplicate_ids_and_seeds(
        self,
    ):
        before = self.store.account.profile()
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        village = current_village(self.db)
        result = self.call(self.request)
        self.assertEqual(
            result,
            {
                "User": before["User"],
                "NewRelicOptions": [
                    {"OptionId": 901, "Level": 4, "OptionSource": 1},
                    {"OptionId": 901, "Level": 3, "OptionSource": 1},
                    {"OptionId": 903, "Level": 10, "OptionSource": 2},
                    {"OptionId": 905, "Level": 480, "OptionSource": 2},
                ],
            },
        )
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )

    def test_accept_changes_only_selected_group_options_and_revision_without_spending_anything(
        self,
    ):
        before = self.store.account.profile()
        self.call(self.request)
        expected = copy.deepcopy(before)
        rows = self.target(expected)["RelicOptions"]
        rows[2].update(OptionId=903, Level=10)
        rows[3]["Level"] = 480
        expected["User"]["Cas"] += 1
        self.assertEqual(self.apply(), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.pending(), [])

    def test_main_group_roll_preserves_subgroup_and_locked_repeated_slot(self):
        before = self.store.account.profile()
        self.call(dict(self.request, OptionType=1))
        self.apply()
        expected = copy.deepcopy(before)
        self.target(expected)["RelicOptions"][0]["Level"] = 2
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)

    def test_discard_preserves_entire_profile_and_revision_and_old_discard_is_idempotent(self):
        before = self.store.account.profile()
        self.call(self.request)
        self.assertEqual(self.apply(False), {"User": before["User"]})
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(self.pending(), [])
        dump = list(self.db.iterdump())
        self.apply(False)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_later_group_roll_replaces_proposal_and_old_generation_displays_latest_without_drawing(
        self,
    ):
        self.call(self.request)
        self.draw.side_effect = lambda n: n - 1
        latest = self.call(dict(self.request, OptionType=1), sequence=193)
        calls = self.draw.call_count
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), latest)
        self.assertEqual(self.draw.call_count, calls)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.apply()
        self.assertEqual(
            [r["Level"] for r in self.target(self.store.account.profile())["RelicOptions"]],
            [8, 3, 21, 485],
        )
        self.assertEqual(
            self.target(self.store.account.profile())["RelicOptions"][0]["OptionId"], 902
        )
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request)["NewRelicOptions"], latest["NewRelicOptions"])
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_old_apply_retry_keeps_new_pending_roll_and_current_jewel_state(self):
        self.call(self.request)
        self.apply()
        self.call(self.request, sequence=193)
        profile = self.store.account.profile()
        self.target(profile)["JewelSlots"] = [999]
        self.save_profile(profile)
        dump = list(self.db.iterdump())
        self.assertEqual(self.apply(), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(len(self.pending()), 1)

    def test_reopening_reconnect_and_new_login_preserve_proposals_receipts_and_resources(self):
        first = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), first)
        self.assertEqual(list(self.db.iterdump()), dump)
        accepted = self.apply()
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        dump = list(self.db.iterdump())
        self.assertEqual(self.apply(), accepted)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.open_session(False)
        self.call(self.request)
        self.apply()
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM relic_option_requests").fetchone()[0], 4
        )

    def test_saved_pools_allow_apply_discard_and_replay_after_external_catalog_removal(self):
        self.call(self.request)
        self.relic_path.unlink()
        self.apply()
        self.write_relic_catalog()
        self.call(self.request, sequence=193)
        before = self.store.account.profile()
        self.relic_path.unlink()
        self.apply(False, 194)
        self.assertEqual(self.store.account.profile(), before)

    def test_accept_retains_later_jewel_slots_and_other_item_fields(self):
        self.call(self.request)
        profile = self.store.account.profile()
        self.target(profile).update(JewelSlots=[999, 123], Experience=77, EvolveProgress=5)
        profile["User"]["Cas"] += 3
        self.save_profile(profile)
        self.apply()
        expected = copy.deepcopy(profile)
        self.target(expected)["RelicOptions"][2].update(OptionId=903, Level=10)
        self.target(expected)["RelicOptions"][3]["Level"] = 480
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)

    def test_missing_or_stale_proposal_rejects_without_writes(self):
        self.reject({"ItemId": 70, "Apply": True}, APPLY, 192)
        self.call(self.request)
        original = self.store.account.profile()
        for field, value in (("ItemId", 702), ("RelicOptions", [])):
            profile = copy.deepcopy(original)
            self.target(profile)[field] = value
            self.save_profile(profile)
            self.reject({"ItemId": 70, "Apply": True}, APPLY, 192)

    def test_corrupt_candidate_cannot_change_other_group_locked_values_sources_or_slot_pools(self):
        self.call(dict(self.request, OptionType=1))
        original = json.loads(self.pending()[0][5])
        for index, field, value in (
            (2, "Level", 22),
            (1, "Level", 5),
            (0, "OptionSource", 2),
            (0, "Locked", True),
            (0, "OptionId", 999),
            (0, "Level", True),
        ):
            rows = copy.deepcopy(original)
            rows[index][field] = value
            with self.db:
                self.db.execute(
                    "UPDATE relic_option_proposals SET after_options=?", (json.dumps(rows),)
                )
            self.reject({"ItemId": 70, "Apply": True}, APPLY, 192)

    def test_exact_schema_identity_authentication_and_completed_prologue_guards(self):
        for body in (
            None,
            {},
            [],
            dict(self.request, ItemId=True),
            dict(self.request, OptionType=True),
            dict(self.request, OptionType=0),
            dict(self.request, OptionType=3),
            dict(self.request, Extra=0),
        ):
            self.reject(body)
        for body in (
            {"ItemId": 70},
            {"ItemId": 70, "Apply": 1},
            {"ItemId": 70, "Apply": True, "OptionType": 2},
        ):
            self.reject(body, APPLY)
        for operation in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.change_or_apply_relic_options(self.request, operation, CHANGE)
        with sqlite3.connect(":memory:") as db:
            fresh = AccountStore(db, self.references)
            dump = list(db.iterdump())
            with self.assertRaises(ValueError):
                fresh.change_or_apply_relic_options(self.request, "too-early", CHANGE)
            self.assertEqual(list(db.iterdump()), dump)
        self.call(self.request)
        self.reject(dict(self.request, OptionType=1))
        self.reject({"ItemId": 70, "Apply": True}, APPLY, 191)
        self.apply()
        self.reject({"ItemId": 70, "Apply": False}, APPLY, 192)
        self.session = BootstrapSession(self.store)
        self.reject(self.request)

    def test_ownership_saved_row_source_count_and_per_slot_ranges_required(self):
        for item in (999, 1, 50):
            self.reject(dict(self.request, ItemId=item))
        original = self.store.account.profile()
        for field, value in (("ItemId", 999), ("Amount", 2), ("Locked", 0), ("RelicOptions", None)):
            profile = copy.deepcopy(original)
            self.target(profile)[field] = value
            self.save_profile(profile)
            self.reject(self.request)
        for index, field, value in (
            (0, "OptionSource", 0),
            (0, "OptionSource", True),
            (2, "OptionId", 905),
            (2, "Level", 999),
            (2, "Locked", 0),
        ):
            profile = copy.deepcopy(original)
            self.target(profile)["RelicOptions"][index][field] = value
            self.save_profile(profile)
            self.reject(self.request)
        profile = copy.deepcopy(original)
        self.target(profile)["RelicOptions"].append(dict(self.target(profile)["RelicOptions"][0]))
        self.save_profile(profile)
        self.reject(self.request)

    def test_explicit_matching_free_catalog_with_valid_slot_bounds_required(self):
        original = copy.deepcopy(self.relic_catalog)
        for key, value in (
            ("client", {}),
            ("free", False),
            ("free", 1),
            ("relics", {}),
            ("relics", {"0701": original["relics"]["701"]}),
            ("relics", {"701": {"1": [{"901": [5, 2]}], "2": []}}),
            ("relics", {"701": {"1": [{"901": [True, 5]}], "2": []}}),
            ("relics", {"701": {"1": [], "2": []}}),
        ):
            self.relic_catalog = dict(original, **{key: value})
            self.write_relic_catalog()
            self.reject(self.request)
        self.relic_path.write_bytes(b" " * (1024 * 1024 + 1))
        self.reject(self.request)
        self.relic_path.unlink()
        self.reject(self.request)

    def test_revision_ceiling_allows_saved_replay_and_discard_but_not_new_acceptance(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call(self.request)
        self.apply()
        self.assertEqual(self.store.account.profile()["User"]["Cas"], MAX_REVISION)
        dump = list(self.db.iterdump())
        self.apply()
        self.assertEqual(list(self.db.iterdump()), dump)
        self.call(self.request, sequence=193)
        self.reject({"ItemId": 70, "Apply": True}, APPLY, 194)
        before = self.store.account.profile()
        self.apply(False, 194)
        self.assertEqual(self.store.account.profile(), before)

    def test_generation_receipt_failure_rolls_back_replacing_previous_proposal(self):
        self.call(self.request)
        self.db.execute(
            "CREATE TRIGGER reject_relic BEFORE INSERT ON relic_option_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request, sequence=193)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_acceptance_receipt_failure_rolls_back_profile_resources_and_pending_removal(self):
        self.call(self.request)
        self.db.execute(
            "CREATE TRIGGER reject_relic BEFORE INSERT ON relic_option_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply()
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_selected_group_needs_unlocked_existing_slots_but_other_group_locks_are_retained(self):
        profile = self.store.account.profile()
        for row in self.target(profile)["RelicOptions"]:
            if row["OptionSource"] == 2:
                row["Locked"] = True
        self.save_profile(profile)
        self.reject(self.request)
        self.call(dict(self.request, OptionType=1))
        profile = self.store.account.profile()
        self.target(profile)["RelicOptions"] = [
            r for r in self.target(profile)["RelicOptions"] if r["OptionSource"] == 2
        ]
        self.save_profile(profile)
        self.relic_catalog["relics"]["701"]["1"] = []
        self.write_relic_catalog()
        self.reject(dict(self.request, OptionType=1), sequence=193)
