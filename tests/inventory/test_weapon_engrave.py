# SPDX-License-Identifier: Apache-2.0
"""First engraving preserves materials and coexists with existing free equipment changes."""

import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.items import inventory_item
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import MAX_REVISION, current_village
from guardian_tales.weapon_engrave import ROUTE
from guardian_tales.weapon_options import APPLY, CHANGE
from tests.village.test_village_harvest import NOW, VillageFixture


class WeaponEngraveTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.engrave_catalog = {
            "client": CLIENT,
            "free": True,
            "min_experience": 1000,
            "required_limit_breaks": 5,
            "engrave_coef": 2,
            "max_ceiling": 5,
            "weapons": {
                "101": {
                    "origin_rarity": 4,
                    "options": [{"OptionId": 1001, "Level": n} for n in (15, 12, 9, 6, 3)],
                },
                "102": {"origin_rarity": 3, "options": [{"OptionId": 1002, "Level": 3}]},
            },
            "hammers": {"501": 4, "502": 3},
        }
        self.engrave_path = self.references / "weapon_engrave_mock_catalog.json"
        self.write_engrave_catalog()
        profile = self.store.account.profile()
        self.target(profile).update(
            Locked=True,
            Experience=1000,
            LimitBreaks=5,
            EngraveCeiling=0,
            EngraveOptions=None,
            Options=[dict(OptionId=901, Level=4, Locked=False, OptionSource=0)],
        )
        for inventory_id, spec in ((50, 501), (51, 502), (60, 601)):
            hammer = inventory_item(inventory_id, spec)
            hammer["Amount"] = 10
            profile["User"]["ItemStackables"].append(hammer)
        profile["User"]["ItemIdCounter"] = 60
        self.asset(profile, 70001).update(Amount=0, Spent=-42)
        self.save_profile(profile)
        self.request = {"TargetWeaponId": 1, "MaterialWeaponId": 50}
        self.draw = patch("guardian_tales.weapon_engrave.randbelow", return_value=0).start()
        self.addCleanup(patch.stopall)

    def write_engrave_catalog(self):
        self.engrave_path.write_text(json.dumps(self.engrave_catalog))

    def call(self, body=None, route=ROUTE, sequence=161, now=NOW):
        return super().call(body, route, sequence, now)

    def target(self, profile):
        return profile["User"]["ItemWeapons"][0]

    def write_other_catalogs(self):
        catalog = {
            "client": CLIENT,
            "free": True,
            "level_total_exps": [i * 100 for i in range(1, 31)],
            "weapons": {"101": 4},
            "hammer_exp": {"601": 100},
            "limit_break_coef": 1,
            "max_limit_breaks": 5,
            "myth_coef": 2,
        }
        (self.references / "weapon_enhance_debug_catalog.json").write_text(json.dumps(catalog))
        (self.references / "weapon_option_mock_catalog.json").write_text(
            json.dumps(
                {
                    "client": CLIENT,
                    "free": True,
                    "weapons": {"101": {"901": [2, 5]}},
                }
            )
        )
        profile = self.store.account.profile()
        profile["User"]["Unlocked"]["MaxLevel"]["Weapon"] = 8
        self.save_profile(profile)

    def test_first_engraving_changes_only_random_option_ceiling_and_revision_with_no_cost(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.target(expected).update(
            EngraveOptions=[{"OptionId": 1001, "Level": 15}], EngraveCeiling=1
        )
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
        self.assertEqual(self.draw.call_count, 1)

    def test_last_public_tier_is_valid_and_new_request_cannot_reengrave_or_spend_material(self):
        self.draw.return_value = 4
        self.call(self.request)
        self.assertEqual(
            self.target(self.store.account.profile())["EngraveOptions"],
            [{"OptionId": 1001, "Level": 3}],
        )
        dump = list(self.db.iterdump())
        with self.assertRaises(ValueError):
            self.store.account.engrave_weapon(self.request, "new-on-engraved")
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_material_rarity_matches_origin_including_evolved_target(self):
        profile = self.store.account.profile()
        self.target(profile)["ItemId"] = 102
        self.save_profile(profile)
        self.reject_without_writes(self.request)
        self.call(dict(self.request, MaterialWeaponId=51))
        self.assertEqual(
            self.target(self.store.account.profile())["EngraveOptions"],
            [{"OptionId": 1002, "Level": 3}],
        )

    def test_late_retry_preserves_later_options_and_experience_without_catalog_or_hammers(self):
        self.call(self.request)
        profile = self.store.account.profile()
        self.target(profile)["Experience"] = 9999
        self.target(profile)["Options"][0]["Level"] = 5
        profile["User"]["ItemStackables"] = []
        self.save_profile(profile)
        self.engrave_path.unlink()
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(self.draw.call_count, 1)
        self.reject_without_writes(dict(self.request, MaterialWeaponId=51))

    def test_reopening_reconnect_and_new_login_keep_saved_engraving_and_receipt(self):
        response = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), response)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.open_session(False)
        self.reject_without_writes(self.request)
        self.assertEqual(self.target(self.store.account.profile())["EngraveCeiling"], 1)

    def test_material_ownership_quantity_rarity_lock_and_saved_state_guards(self):
        for material in (999, 1, 2, 51, 60):
            self.reject_without_writes(dict(self.request, MaterialWeaponId=material))
        original = self.store.account.profile()
        for field, value in (
            ("Amount", 0),
            ("Amount", True),
            ("Locked", True),
            ("Experience", 1),
            ("LimitBreaks", True),
            ("ItemId", 999),
        ):
            profile = copy.deepcopy(original)
            profile["User"]["ItemStackables"][0][field] = value
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        original["User"]["ItemStackables"].append(dict(original["User"]["ItemStackables"][0]))
        self.save_profile(original)
        self.reject_without_writes(self.request)

    def test_target_eligibility_ownership_existing_engraving_and_malformed_state_guards(self):
        for target in (999, 50):
            self.reject_without_writes(dict(self.request, TargetWeaponId=target))
        original = self.store.account.profile()
        for field, value in (
            ("Id", True),
            ("ItemId", 999),
            ("Amount", 2),
            ("Experience", 999),
            ("Experience", True),
            ("LimitBreaks", 4),
            ("LimitBreaks", 6),
            ("EngraveCeiling", 1),
            ("EngraveCeiling", False),
            ("EngraveOptions", [{}]),
            ("Locked", 0),
        ):
            profile = copy.deepcopy(original)
            self.target(profile)[field] = value
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        original["User"]["ItemWeapons"].append(dict(self.target(original)))
        self.save_profile(original)
        self.reject_without_writes(self.request)

    def test_exact_schema_identity_authentication_and_completed_prologue_required(self):
        for body in (
            None,
            {},
            [],
            {"TargetWeaponId": 1},
            dict(self.request, TargetWeaponId=True),
            dict(self.request, MaterialWeaponId=False),
            dict(self.request, Extra=0),
        ):
            self.reject_without_writes(body)
        for operation in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.engrave_weapon(self.request, operation)
        with sqlite3.connect(":memory:") as db:
            fresh = AccountStore(db, self.references)
            dump = list(db.iterdump())
            with self.assertRaises(ValueError):
                fresh.engrave_weapon(self.request, "too-early")
            self.assertEqual(list(db.iterdump()), dump)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes(self.request)

    def test_explicit_matching_free_catalog_and_valid_option_tiers_required(self):
        original = copy.deepcopy(self.engrave_catalog)
        for key, value in (
            ("client", {}),
            ("free", False),
            ("free", 1),
            ("min_experience", True),
            ("required_limit_breaks", 0),
            ("engrave_coef", False),
            ("max_ceiling", 0),
            ("weapons", {}),
            ("hammers", {"501": 5}),
            ("hammers", {"101": 4}),
            ("weapons", {"0101": original["weapons"]["101"]}),
            ("weapons", {"101": {"origin_rarity": 4, "options": [{"OptionId": True, "Level": 3}]}}),
            (
                "weapons",
                {"101": {"origin_rarity": 4, "options": [{"OptionId": 1001, "Level": 3}] * 2}},
            ),
        ):
            self.engrave_catalog = dict(original, **{key: value})
            self.write_engrave_catalog()
            self.reject_without_writes(self.request)
        self.engrave_path.write_bytes(b" " * (1024 * 1024 + 1))
        self.reject_without_writes(self.request)
        self.engrave_path.unlink()
        self.reject_without_writes(self.request)

    def test_signed_revision_ceiling_blocks_new_work_but_not_saved_replay(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call(self.request)
        after = self.store.account.profile()
        self.assertEqual(after["User"]["Cas"], MAX_REVISION)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": after["User"]})
        with self.assertRaises(ValueError):
            self.store.account.engrave_weapon(self.request, "new-at-ceiling")
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_receipt_failure_rolls_back_engraving_revision_and_all_materials(self):
        self.db.execute(
            "CREATE TRIGGER reject_engrave BEFORE INSERT ON weapon_engrave_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_enhancement_after_engraving_retains_attribute_and_hammers_and_uses_added_cap(self):
        self.write_other_catalogs()
        self.call(self.request)
        before = self.store.account.profile()
        # Imported clients also retain native metadata on the engraving row.
        self.target(before)["EngraveOptions"][0].update(OptionSource=0, Locked=False)
        self.save_profile(before)
        request = {"TargetWeaponId": 1, "SourceItems": {"60": 10}, "discountBuff": False}
        self.call(request, "/item/enhance-weapon", 162)
        expected = copy.deepcopy(before)
        self.target(expected)["Experience"] = 1500
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)

    def test_normal_option_proposal_preceding_engraving_can_apply_and_replay_after_it(self):
        self.write_other_catalogs()
        with patch("guardian_tales.weapon_options.randbelow", return_value=0):
            self.call({"ItemId": 1}, CHANGE, 163)
        self.call(self.request)
        before = self.store.account.profile()
        self.call({"ItemId": 1, "Apply": True}, APPLY, 164)
        expected = copy.deepcopy(before)
        self.target(expected)["Options"][0]["Level"] = 2
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_invalid_saved_engraving_rejects_followup_experience_and_option_changes(self):
        self.write_other_catalogs()
        self.call(self.request)
        original = self.store.account.profile()
        for field, value in (
            ("EngraveOptions", [{"OptionId": 1001, "Level": 999}]),
            ("EngraveOptions", [{"OptionId": True, "Level": 3}]),
            ("EngraveCeiling", 0),
        ):
            profile = copy.deepcopy(original)
            self.target(profile)[field] = value
            self.save_profile(profile)
            dump = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.enhance_weapon(
                    {"TargetWeaponId": 1, "SourceItems": {"60": 1}, "discountBuff": False},
                    "bad-engraved-enhance",
                )
            with self.assertRaises(ValueError):
                self.store.account.change_or_apply_weapon_options(
                    {"ItemId": 1}, "bad-engraved-options", CHANGE
                )
            self.assertEqual(list(self.db.iterdump()), dump)
