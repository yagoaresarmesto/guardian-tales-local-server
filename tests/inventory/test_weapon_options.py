# SPDX-License-Identifier: Apache-2.0
"""Option proposals, apply/discard, locked values and retry preservation."""

import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.items import inventory_item
from guardian_tales.protocol import PacketError
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import MAX_REVISION, current_village
from guardian_tales.weapon_options import APPLY, CHANGE
from tests.village.test_village_harvest import NOW, VillageFixture


class WeaponOptionTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.option_catalog = {
            "client": CLIENT,
            "free": True,
            "weapons": {"101": {"901": [2, 5], "902": [1, 9], "903": [4, 8]}},
        }
        self.option_path = self.references / "weapon_option_mock_catalog.json"
        self.write_option_catalog()
        profile = self.store.account.profile()
        self.target(profile).update(
            Locked=True,
            LimitBreaks=5,
            Experience=555,
            Options=[
                dict(OptionId=901, Level=4, Locked=False, OptionSource=0),
                dict(OptionId=902, Level=5, Locked=True, OptionSource=0),
                dict(OptionId=903, Level=6, Locked=False, OptionSource=0),
            ],
        )
        stone = inventory_item(50, 501)
        stone["Amount"] = 100
        profile["User"]["ItemStackables"].append(stone)
        profile["User"]["ItemIdCounter"] = 50
        self.asset(profile, 70001).update(Amount=0, Spent=-42)
        self.save_profile(profile)
        self.request = {"ItemId": 1}
        self.random = patch("guardian_tales.weapon_options.randbelow", return_value=0).start()
        self.addCleanup(patch.stopall)

    def write_option_catalog(self):
        self.option_path.write_text(json.dumps(self.option_catalog))

    def call(self, body=None, route=CHANGE, sequence=151, now=NOW):
        return super().call(body, route, sequence, now)

    def apply(self, accept=True, sequence=152):
        return self.call({"ItemId": 1, "Apply": accept}, APPLY, sequence)

    def target(self, profile):
        return profile["User"]["ItemWeapons"][0]

    def pending(self):
        return self.db.execute("SELECT * FROM weapon_option_proposals").fetchall()

    def reject(self, body, route=CHANGE, sequence=151):
        dump = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route, sequence)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_generation_returns_native_pairs_and_preserves_entire_profile_resources_and_locks(self):
        before = self.store.account.profile()
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        village = current_village(self.db)
        response = self.call(self.request)
        self.assertEqual(
            response,
            {
                "User": before["User"],
                "NewOptions": [
                    {"OptionId": 901, "Level": 2},
                    {"OptionId": 902, "Level": 5},
                    {"OptionId": 903, "Level": 4},
                ],
            },
        )
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(self.random.call_count, 2)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(len(self.pending()), 1)

    def test_accept_changes_only_target_option_levels_and_user_revision_without_any_cost(self):
        before = self.store.account.profile()
        self.call(self.request)
        expected = copy.deepcopy(before)
        self.target(expected)["Options"][0]["Level"] = 2
        self.target(expected)["Options"][2]["Level"] = 4
        expected["User"]["Cas"] += 1
        self.assertEqual(self.apply(), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.pending(), [])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM weapon_option_requests").fetchone()[0], 2
        )

    def test_discard_leaves_profile_revision_resources_and_existing_options_unchanged(self):
        before = self.store.account.profile()
        self.call(self.request)
        self.assertEqual(self.apply(False), {"User": before["User"]})
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(self.pending(), [])
        dump = list(self.db.iterdump())
        self.assertEqual(self.apply(False), {"User": before["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_reroll_replaces_proposal_and_accepts_latest_values_without_preapplying(self):
        before = self.store.account.profile()
        first = self.call(self.request)
        self.random.side_effect = lambda n: n - 1
        second = self.call(self.request, sequence=153)
        self.assertNotEqual(first["NewOptions"], second["NewOptions"])
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(len(self.pending()), 1)
        self.apply()
        options = self.target(self.store.account.profile())["Options"]
        self.assertEqual([r["Level"] for r in options], [5, 5, 8])

    def test_old_change_retry_returns_latest_proposal_without_drawing_or_resurrecting_old_roll(
        self,
    ):
        self.call(self.request)
        self.random.side_effect = lambda n: n - 1
        latest = self.call(self.request, sequence=153)
        dump = list(self.db.iterdump())
        calls = self.random.call_count
        self.assertEqual(self.call(self.request), latest)
        self.assertEqual(self.random.call_count, calls)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.apply()
        current = self.store.account.profile()
        dump = list(self.db.iterdump())
        replay = self.call(self.request)
        self.assertEqual(replay["NewOptions"], latest["NewOptions"])
        self.assertEqual(replay["User"], current["User"])
        self.assertEqual(self.pending(), [])
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_old_apply_retry_preserves_new_pending_proposal_and_current_experience(self):
        self.call(self.request)
        self.apply()
        self.random.side_effect = lambda n: n - 1
        self.call(self.request, sequence=153)
        profile = self.store.account.profile()
        self.target(profile)["Experience"] = 999
        self.save_profile(profile)
        dump = list(self.db.iterdump())
        self.assertEqual(self.apply(), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(len(self.pending()), 1)
        self.apply(sequence=154)
        self.assertEqual(self.target(self.store.account.profile())["Experience"], 999)

    def test_reopening_reconnect_and_new_login_preserve_proposals_and_receipts(self):
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
        self.random.side_effect = lambda n: n - 1
        self.call(self.request)
        self.apply()
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM weapon_option_requests").fetchone()[0], 4
        )

    def test_prepared_proposal_can_be_applied_or_discarded_after_catalog_removal(self):
        self.call(self.request)
        self.option_path.unlink()
        self.apply()
        self.write_option_catalog()
        self.call(self.request, sequence=153)
        before = self.store.account.profile()
        self.option_path.unlink()
        self.apply(False, 154)
        self.assertEqual(self.store.account.profile(), before)

    def test_applying_merges_with_later_experience_and_limit_break_changes(self):
        self.call(self.request)
        profile = self.store.account.profile()
        self.target(profile).update(Experience=777, LimitBreaks=4)
        profile["User"]["Cas"] += 4
        self.save_profile(profile)
        self.apply()
        after = self.store.account.profile()
        self.assertEqual(self.target(after)["Experience"], 777)
        self.assertEqual(self.target(after)["LimitBreaks"], 4)
        self.assertEqual(after["User"]["Cas"], profile["User"]["Cas"] + 1)

    def test_missing_proposal_and_changed_target_options_or_spec_reject_without_writes(self):
        self.reject({"ItemId": 1, "Apply": True}, APPLY, 152)
        self.call(self.request)
        original = self.store.account.profile()
        for change in ("spec", "options"):
            profile = copy.deepcopy(original)
            if change == "spec":
                self.target(profile)["ItemId"] = 102
            else:
                self.target(profile)["Options"][0]["Level"] = 3
            self.save_profile(profile)
            self.reject({"ItemId": 1, "Apply": True}, APPLY, 152)

    def test_corrupt_proposal_cannot_change_identity_locked_values_metadata_or_bounds(self):
        self.call(self.request)
        original = json.loads(self.pending()[0][4])
        for field, value, index in (
            ("OptionId", 999, 0),
            ("Locked", True, 0),
            ("Level", 7, 1),
            ("Level", True, 0),
            ("Level", 999, 0),
            ("OptionSource", 1, 0),
        ):
            options = copy.deepcopy(original)
            options[index][field] = value
            with self.db:
                self.db.execute(
                    "UPDATE weapon_option_proposals SET after_options=?", (json.dumps(options),)
                )
            self.reject({"ItemId": 1, "Apply": True}, APPLY, 152)

    def test_target_ownership_and_unsupported_or_malformed_options_reject(self):
        self.reject({"ItemId": 999})
        self.reject({"ItemId": 50})
        original = self.store.account.profile()
        for field, value in (
            ("Id", True),
            ("ItemId", 999),
            ("Amount", 2),
            ("EngraveOptions", [{}]),
            ("Options", None),
        ):
            profile = copy.deepcopy(original)
            self.target(profile)[field] = value
            self.save_profile(profile)
            self.reject(self.request)
        for field, value in (
            ("OptionId", 999),
            ("Level", True),
            ("Level", 0),
            ("Locked", 0),
            ("OptionSource", 1),
        ):
            profile = copy.deepcopy(original)
            self.target(profile)["Options"][0][field] = value
            self.save_profile(profile)
            self.reject(self.request)
        profile = copy.deepcopy(original)
        for option in self.target(profile)["Options"]:
            option["Locked"] = True
        self.save_profile(profile)
        self.reject(self.request)
        profile = copy.deepcopy(original)
        self.target(profile)["Options"].append(dict(self.target(profile)["Options"][0]))
        self.save_profile(profile)
        self.reject(self.request)

    def test_exact_schema_identity_authentication_and_completed_prologue_guards(self):
        for body in (None, {}, [], {"ItemId": True}, {"ItemId": 1, "Apply": True}):
            self.reject(body)
        for body in (
            None,
            {},
            {"ItemId": 1},
            {"ItemId": 1, "Apply": 1},
            {"ItemId": 1, "Apply": True, "Extra": 0},
        ):
            self.reject(body, APPLY)
        for operation in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.change_or_apply_weapon_options(self.request, operation, CHANGE)
        with sqlite3.connect(":memory:") as db:
            fresh = AccountStore(db, self.references)
            dump = list(db.iterdump())
            with self.assertRaises(ValueError):
                fresh.change_or_apply_weapon_options(self.request, "too-early", CHANGE)
            self.assertEqual(list(db.iterdump()), dump)
        self.session = BootstrapSession(self.store)
        self.reject(self.request)

    def test_free_matching_catalog_and_valid_canonical_option_ranges_are_required(self):
        original = copy.deepcopy(self.option_catalog)
        for key, value in (
            ("client", {}),
            ("free", False),
            ("free", 1),
            ("weapons", {}),
            ("weapons", {"0101": {"901": [2, 5]}}),
            ("weapons", {"101": {"0901": [2, 5]}}),
            ("weapons", {"101": {"901": [True, 5]}}),
            ("weapons", {"101": {"901": [5, 2]}}),
            ("weapons", {"101": {"901": [0, 1001]}}),
        ):
            self.option_catalog = dict(original, **{key: value})
            self.write_option_catalog()
            self.reject(self.request)
        self.option_path.write_bytes(b" " * (1024 * 1024 + 1))
        self.reject(self.request)
        self.option_path.unlink()
        self.reject(self.request)

    def test_revision_ceiling_blocks_accept_but_allows_discard_and_saved_replay(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call(self.request)
        self.apply()
        self.assertEqual(self.store.account.profile()["User"]["Cas"], MAX_REVISION)
        dump = list(self.db.iterdump())
        self.apply()
        self.assertEqual(list(self.db.iterdump()), dump)
        self.call(self.request, sequence=153)
        self.reject({"ItemId": 1, "Apply": True}, APPLY, 154)
        before = self.store.account.profile()
        self.apply(False, 154)
        self.assertEqual(self.store.account.profile(), before)

    def test_generation_receipt_failure_rolls_back_replacing_an_existing_proposal(self):
        self.call(self.request)
        self.db.execute(
            "CREATE TRIGGER reject_option BEFORE INSERT ON weapon_option_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request, sequence=153)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_apply_receipt_failure_rolls_back_profile_resources_and_proposal_removal(self):
        self.call(self.request)
        self.db.execute(
            "CREATE TRIGGER reject_option BEFORE INSERT ON weapon_option_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply()
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_operation_identity_cannot_change_item_route_or_apply_choice(self):
        self.call(self.request)
        self.reject({"ItemId": 2})
        self.reject({"ItemId": 1, "Apply": True}, APPLY, 151)
        self.apply()
        self.reject({"ItemId": 1, "Apply": False}, APPLY, 152)
