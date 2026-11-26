# SPDX-License-Identifier: Apache-2.0
"""Free hammer enhancement changes only one equipment's experience and revision."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.items import inventory_item
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import INT_MAX, MAX_REVISION, current_village
from guardian_tales.weapon_enhance import ROUTE
from tests.test_village_harvest import NOW, VillageFixture


class WeaponEnhanceTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.enhance_catalog = {
            "client": CLIENT,
            "free": True,
            "level_total_exps": [100 * i for i in range(1, 21)],
            "weapons": {"101": 4, "102": 5},
            "hammer_exp": {"501": 25, "502": 50},
            "limit_break_coef": 1,
            "max_limit_breaks": 5,
            "myth_coef": 2,
        }
        self.enhance_path = self.references / "weapon_enhance_debug_catalog.json"
        self.write_enhance_catalog()
        profile = self.store.account.profile()
        profile["User"]["ItemWeapons"][0].update(Experience=55, Locked=True, LimitBreaks=1)
        profile["User"]["Unlocked"]["MaxLevel"]["Weapon"] = 4
        for inventory_id, spec_id in ((50, 501), (51, 502)):
            hammer = inventory_item(inventory_id, spec_id)
            hammer["Amount"] = 10
            profile["User"]["ItemStackables"].append(hammer)
        profile["User"]["ItemIdCounter"] = 51
        self.asset(profile, 70001).update(Amount=0, Spent=-42)
        self.save_profile(profile)
        self.request = {"TargetWeaponId": 1, "SourceItems": {"50": 3}, "discountBuff": False}

    def write_enhance_catalog(self):
        self.enhance_path.write_text(json.dumps(self.enhance_catalog))

    def call(self, body=None, route=ROUTE, sequence=131, now=NOW):
        return super().call(body, route, sequence, now)

    def target(self, profile):
        return profile["User"]["ItemWeapons"][0]

    def test_locked_equipped_target_gains_exact_experience_with_no_cost_or_other_profile_changes(
        self,
    ):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.target(expected)["Experience"] = 130
        expected["User"]["Cas"] += 1
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        village = current_village(self.db)
        self.assertEqual(self.call(self.request), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(
            self.db.execute(
                "SELECT experience_before,experience_after FROM weapon_enhance_requests"
            ).fetchone(),
            (55, 130),
        )

    def test_myth_and_limit_break_cap_clips_excess_experience_without_consuming_hammers(self):
        profile = self.store.account.profile()
        self.target(profile).update(ItemId=102, LimitBreaks=2, Experience=790)
        self.save_profile(profile)
        self.call(self.request)
        after = self.store.account.profile()
        self.assertEqual(self.target(after)["Experience"], 800)
        self.assertEqual(after["User"]["ItemStackables"], profile["User"]["ItemStackables"])
        self.assertEqual(self.call(self.request), {"User": after["User"]})
        with self.assertRaises(ValueError):
            self.store.account.enhance_weapon(self.request, "new-at-cap")

    def test_discount_flag_does_not_spend_gold_hammers_or_account_buffs(self):
        profile = self.store.account.profile()
        request = dict(self.request, discountBuff=True)
        self.call(request)
        after = self.store.account.profile()
        self.assertEqual(after["User"]["Assets"], profile["User"]["Assets"])
        self.assertEqual(after["User"]["ItemStackables"], profile["User"]["ItemStackables"])
        self.assertEqual(after["User"]["Options"], profile["User"]["Options"])
        self.reject_without_writes(self.request)

    def test_canonical_and_delayed_retry_keeps_later_enhancement_without_catalog(self):
        request = dict(self.request, SourceItems={"50": 2, "51": 1})
        self.call(request)
        self.call(self.request, sequence=132)
        profile = self.store.account.profile()
        self.enhance_path.unlink()
        before = list(self.db.iterdump())
        reordered = dict(request, SourceItems={"51": 1, "50": 2})
        self.assertEqual(self.call(reordered), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes(self.request)

    def test_reopening_reconnect_and_new_login_preserve_receipt_and_reuse_retained_materials(self):
        first = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.call(self.request)
        after = self.store.account.profile()
        self.assertEqual(self.target(after)["Experience"], 205)
        self.assertEqual(after["User"]["ItemStackables"][0]["Amount"], 10)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM weapon_enhance_requests").fetchone()[0], 2
        )

    def test_foreign_insufficient_locked_modified_and_ambiguous_materials_reject_without_writes(
        self,
    ):
        for sources in ({"999": 1}, {"50": 11}, {"1": 1}, {"2": 1}):
            self.reject_without_writes(dict(self.request, SourceItems=sources))
        original = self.store.account.profile()
        for field, value in (
            ("Locked", True),
            ("Experience", 1),
            ("LimitBreaks", 1),
            ("ItemId", 999),
            ("Amount", False),
        ):
            profile = copy.deepcopy(original)
            profile["User"]["ItemStackables"][0][field] = value
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        original["User"]["ItemStackables"].append(dict(original["User"]["ItemStackables"][0]))
        self.save_profile(original)
        self.reject_without_writes(self.request)

    def test_invalid_foreign_engraved_and_ambiguous_target_equipment_rejects(self):
        self.reject_without_writes(dict(self.request, TargetWeaponId=999))
        self.reject_without_writes(dict(self.request, TargetWeaponId=50))
        original = self.store.account.profile()
        for field, value in (
            ("Experience", True),
            ("Experience", -1),
            ("LimitBreaks", 6),
            ("Amount", 2),
            ("ItemId", 999),
            ("EngraveOptions", [{}]),
        ):
            profile = copy.deepcopy(original)
            self.target(profile)[field] = value
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        original["User"]["ItemWeapons"].append(dict(self.target(original)))
        self.save_profile(original)
        self.reject_without_writes(self.request)

    def test_exact_native_schema_authentication_identity_and_fresh_prologue_guard(self):
        for request in (
            None,
            {},
            [],
            dict(self.request, TargetWeaponId=True),
            dict(self.request, discountBuff=0),
            dict(self.request, SourceItems={}),
            dict(self.request, SourceItems={"050": 1}),
            dict(self.request, SourceItems={"50": True}),
            dict(self.request, Extra=0),
        ):
            self.reject_without_writes(request)
        for op in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.enhance_weapon(self.request, op)
        with sqlite3.connect(":memory:") as db:
            fresh = AccountStore(db, self.references)
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                fresh.enhance_weapon(self.request, "too-early")
            self.assertEqual(list(db.iterdump()), before)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes(self.request)

    def test_free_matching_catalog_and_valid_monotonic_tables_are_required(self):
        original = copy.deepcopy(self.enhance_catalog)
        for key, value in (
            ("client", {}),
            ("free", False),
            ("free", 1),
            ("weapons", {}),
            ("weapons", {"0101": 4}),
            ("hammer_exp", {"501": 0}),
            ("hammer_exp", {"101": 25}),
            ("level_total_exps", [100, 90]),
            ("level_total_exps", [True]),
            ("limit_break_coef", True),
        ):
            self.enhance_catalog = dict(original, **{key: value})
            self.write_enhance_catalog()
            self.reject_without_writes(self.request)
        self.enhance_path.write_text(" " * (1024 * 1024 + 1))
        self.reject_without_writes(self.request)
        self.enhance_path.unlink()
        self.reject_without_writes(self.request)

    def test_signed_64_bit_revision_ceiling_blocks_new_work_but_not_saved_replay(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call(self.request)
        profile = self.store.account.profile()
        self.assertEqual(profile["User"]["Cas"], MAX_REVISION)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        with self.assertRaises(ValueError):
            self.store.account.enhance_weapon(self.request, "new-overflow")
        self.assertEqual(list(self.db.iterdump()), before)

    def test_receipt_failure_rolls_back_experience_revision_and_every_resource(self):
        self.db.execute(
            "CREATE TRIGGER reject_enhance BEFORE INSERT ON weapon_enhance_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_saved_caps_and_aggregate_experience_overflow_reject_atomically(self):
        original = self.store.account.profile()
        for cap in (None, False, 0, 20):
            profile = copy.deepcopy(original)
            profile["User"]["Unlocked"]["MaxLevel"]["Weapon"] = cap
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        self.save_profile(original)
        self.enhance_catalog["hammer_exp"]["501"] = INT_MAX
        self.write_enhance_catalog()
        self.reject_without_writes(self.request)
