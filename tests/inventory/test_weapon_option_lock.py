# SPDX-License-Identifier: Apache-2.0
"""Free lock/unlock preserves values, resources, engraving and later choices."""

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
from guardian_tales.weapon_option_lock import ROUTE
from guardian_tales.weapon_options import APPLY, CHANGE
from tests.village.test_village_harvest import NOW, VillageFixture


class WeaponOptionLockTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        ranges = {"901": [2, 5], "902": [1, 9], "903": [4, 8]}
        self.option_catalog = {
            "client": CLIENT,
            "free": True,
            "weapons": {"101": ranges, "102": ranges},
        }
        self.option_path = self.references / "weapon_option_mock_catalog.json"
        self.option_path.write_text(json.dumps(self.option_catalog))
        profile = self.store.account.profile()
        options = [
            dict(OptionId=901, Level=4, Locked=False, OptionSource=0),
            dict(OptionId=902, Level=5, Locked=True, OptionSource=0),
            dict(OptionId=903, Level=6, Locked=False, OptionSource=0),
        ]
        for item in profile["User"]["ItemWeapons"]:
            item.update(Options=copy.deepcopy(options), Locked=True)
        stone = inventory_item(50, 501)
        stone["Amount"] = 100
        profile["User"]["ItemStackables"].append(stone)
        profile["User"]["ItemIdCounter"] = 50
        self.asset(profile, 70001).update(Amount=0, Spent=-42)
        self.save_profile(profile)
        self.request = {"ItemId": 1, "OptionIds": [901], "DoLock": True}

    def call(self, body=None, route=ROUTE, sequence=171, now=NOW):
        return super().call(body, route, sequence, now)

    def target(self, profile):
        return profile["User"]["ItemWeapons"][0]

    def reject(self, body, route=ROUTE, sequence=171):
        dump = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route, sequence)
        self.assertEqual(list(self.db.iterdump()), dump)

    def proposal(self, item=1, sequence=181):
        with patch("guardian_tales.weapon_options.randbelow", return_value=0):
            return self.call({"ItemId": item}, CHANGE, sequence)

    def test_lock_changes_only_selected_flags_and_revision_preserving_all_resources_and_seed(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.target(expected)["Options"][0]["Locked"] = True
        expected["User"]["Cas"] += 1
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        village = current_village(self.db)
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )

    def test_unlock_preserves_unselected_locks_and_all_option_values(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.target(expected)["Options"][1]["Locked"] = False
        expected["User"]["Cas"] += 1
        self.call(dict(self.request, OptionIds=[902], DoLock=False))
        self.assertEqual(self.store.account.profile(), expected)

    def test_canonical_old_retry_retains_later_unlock_and_option_values_without_catalog(self):
        request = dict(self.request, OptionIds=[901, 903])
        self.call(request)
        self.call(dict(self.request, DoLock=False), sequence=172)
        profile = self.store.account.profile()
        self.target(profile)["Options"][0]["Level"] = 5
        self.save_profile(profile)
        self.option_path.unlink()
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(dict(request, OptionIds=[903, 901])), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.reject(dict(request, DoLock=False))

    def test_reopening_reconnect_and_new_login_preserve_receipts_and_noop_revision(self):
        first = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), first)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.open_session(False)
        profile = self.store.account.profile()
        self.assertEqual(self.call(self.request), {"User": profile["User"]})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM weapon_option_lock_requests").fetchone()[0], 2
        )

    def test_noop_at_revision_ceiling_keeps_pending_proposal_and_profile_unchanged(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        self.proposal()
        pending = self.db.execute("SELECT * FROM weapon_option_proposals").fetchall()
        self.call(dict(self.request, OptionIds=[902]))
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.db.execute("SELECT * FROM weapon_option_proposals").fetchall(), pending
        )

    def test_revision_ceiling_blocks_changed_lock_but_not_saved_replay(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call(self.request)
        after = self.store.account.profile()
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": after["User"]})
        self.reject(dict(self.request, DoLock=False), sequence=172)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_changed_lock_discards_only_its_pending_proposal_and_prevents_stale_apply(self):
        self.proposal()
        self.proposal(2, 182)
        self.call(self.request)
        self.assertEqual(
            self.db.execute("SELECT item_id FROM weapon_option_proposals").fetchall(), [(2,)]
        )
        self.reject({"ItemId": 1, "Apply": True}, APPLY, 183)
        self.call({"ItemId": 2, "Apply": True}, APPLY, 184)
        self.assertTrue(self.target(self.store.account.profile())["Options"][0]["Locked"])

    def test_later_value_roll_preserves_locked_value_and_accept_changes_only_unlocked_values(self):
        self.call(self.request)
        before = self.store.account.profile()
        response = self.proposal()
        self.assertEqual(
            response["NewOptions"],
            [
                {"OptionId": 901, "Level": 4},
                {"OptionId": 902, "Level": 5},
                {"OptionId": 903, "Level": 4},
            ],
        )
        self.call({"ItemId": 1, "Apply": True}, APPLY, 182)
        expected = copy.deepcopy(before)
        self.target(expected)["Options"][2]["Level"] = 4
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)

    def test_all_locked_options_reject_reroll_until_one_is_unlocked(self):
        self.call(dict(self.request, OptionIds=[901, 902, 903]))
        self.reject({"ItemId": 1}, CHANGE, 181)
        self.call(dict(self.request, OptionIds=[903], DoLock=False), sequence=172)
        self.assertEqual(
            self.proposal()["NewOptions"],
            [
                {"OptionId": 901, "Level": 4},
                {"OptionId": 902, "Level": 5},
                {"OptionId": 903, "Level": 4},
            ],
        )

    def test_exact_schema_option_identity_authentication_and_prologue_guards(self):
        for body in (
            None,
            {},
            [],
            dict(self.request, ItemId=True),
            dict(self.request, DoLock=1),
            dict(self.request, OptionIds=[]),
            dict(self.request, OptionIds="901"),
            dict(self.request, OptionIds=[True]),
            dict(self.request, OptionIds=[901, 901]),
            dict(self.request, Extra=0),
        ):
            self.reject(body)
        for operation in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.change_weapon_option_locks(self.request, operation)
        with sqlite3.connect(":memory:") as db:
            fresh = AccountStore(db, self.references)
            dump = list(db.iterdump())
            with self.assertRaises(ValueError):
                fresh.change_weapon_option_locks(self.request, "too-early")
            self.assertEqual(list(db.iterdump()), dump)
        self.session = BootstrapSession(self.store)
        self.reject(self.request)

    def test_owned_equipment_valid_saved_options_and_matching_free_catalog_required(self):
        self.reject(dict(self.request, ItemId=999))
        self.reject(dict(self.request, ItemId=50))
        original = self.store.account.profile()
        for field, value in (("OptionSource", 1), ("Level", 100), ("Locked", 0)):
            profile = copy.deepcopy(original)
            self.target(profile)["Options"][0][field] = value
            self.save_profile(profile)
            self.reject(self.request)
        self.save_profile(original)
        self.option_catalog["free"] = False
        self.option_path.write_text(json.dumps(self.option_catalog))
        self.reject(self.request)
        self.option_path.unlink()
        self.reject(self.request)

    def test_receipt_failure_rolls_back_profile_revision_resources_and_pending_removal(self):
        self.proposal()
        self.db.execute(
            "CREATE TRIGGER reject_lock BEFORE INSERT ON weapon_option_lock_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_supported_saved_engraving_is_retained_when_locking_normal_options(self):
        catalog = {
            "client": CLIENT,
            "free": True,
            "min_experience": 1000,
            "required_limit_breaks": 5,
            "engrave_coef": 15,
            "max_ceiling": 5,
            "weapons": {"101": {"origin_rarity": 4, "options": [{"OptionId": 1001, "Level": 3}]}},
            "hammers": {"501": 4},
        }
        (self.references / "weapon_engrave_mock_catalog.json").write_text(json.dumps(catalog))
        profile = self.store.account.profile()
        self.target(profile).update(
            EngraveOptions=[{"OptionId": 1001, "Level": 3}], EngraveCeiling=1
        )
        self.save_profile(profile)
        expected = copy.deepcopy(profile)
        self.target(expected)["Options"][0]["Locked"] = True
        expected["User"]["Cas"] += 1
        self.call(self.request)
        self.assertEqual(self.store.account.profile(), expected)

    def test_mixed_valid_and_missing_option_ids_rejects_entire_change_without_partial_writes(self):
        self.reject(dict(self.request, OptionIds=[901, 999]))
        self.reject(dict(self.request, OptionIds=[901, 0]))
        self.call(self.request)
        self.reject(dict(self.request, ItemId=2))
        self.reject(dict(self.request, OptionIds=[903]))
