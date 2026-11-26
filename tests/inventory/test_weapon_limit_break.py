# SPDX-License-Identifier: Apache-2.0
"""Free hammer limit breaks preserve inventory and persist bounded retry receipts."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.items import inventory_item
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import INT_MAX, MAX_REVISION, current_village
from guardian_tales.weapon_limit_break import ROUTE
from tests.test_village_harvest import NOW, VillageFixture


class WeaponLimitBreakTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.limit_catalog = {
            "client": CLIENT,
            "free": True,
            "weapons": {"101": 4, "102": 3},
            "hammers": {"501": 4, "502": 3},
            "max_limit_breaks": 5,
        }
        self.limit_path = self.references / "weapon_limit_break_mock_catalog.json"
        self.write_limit_catalog()
        profile = self.store.account.profile()
        self.target(profile).update(Experience=555, Locked=True, LimitBreaks=1)
        for inventory_id, spec in ((50, 501), (51, 502), (52, 501)):
            hammer = inventory_item(inventory_id, spec)
            hammer["Amount"] = 10
            profile["User"]["ItemStackables"].append(hammer)
        profile["User"]["ItemIdCounter"] = 52
        self.asset(profile, 70001).update(Amount=0, Spent=-42)
        self.save_profile(profile)
        self.request = {"TargetWeaponId": 1, "SourceItems": {"50": 2}, "discountBuff": False}

    def write_limit_catalog(self):
        self.limit_path.write_text(json.dumps(self.limit_catalog))

    def call(self, body=None, route=ROUTE, sequence=141, now=NOW):
        return super().call(body, route, sequence, now)

    def target(self, profile):
        return profile["User"]["ItemWeapons"][0]

    def test_locked_target_gains_breaks_without_gold_hammer_experience_or_other_changes(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.target(expected)["LimitBreaks"] = 3
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
                "SELECT breaks_before,breaks_after FROM weapon_limit_break_requests"
            ).fetchone(),
            (1, 3),
        )

    def test_multiple_stacks_clip_at_maximum_and_replay_at_cap_without_consumption(self):
        request = dict(self.request, SourceItems={"50": 2, "52": 10})
        before = self.store.account.profile()
        self.call(request)
        after = self.store.account.profile()
        self.assertEqual(self.target(after)["LimitBreaks"], 5)
        self.assertEqual(after["User"]["ItemStackables"], before["User"]["ItemStackables"])
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(request), {"User": after["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        with self.assertRaises(ValueError):
            self.store.account.limit_break_weapon(request, "new-at-cap")
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_discount_flag_consumes_no_buff_and_changed_retry_rejects(self):
        before = self.store.account.profile()
        request = dict(self.request, discountBuff=True)
        self.call(request)
        after = self.store.account.profile()
        self.assertEqual(after["User"]["Assets"], before["User"]["Assets"])
        self.assertEqual(after["User"]["Options"], before["User"]["Options"])
        self.assertEqual(after["User"]["ItemStackables"], before["User"]["ItemStackables"])
        self.reject_without_writes(self.request)

    def test_origin_rarity_matches_hammer_rather_than_current_evolved_rarity(self):
        profile = self.store.account.profile()
        self.target(profile)["ItemId"] = 102
        self.save_profile(profile)
        self.reject_without_writes(self.request)
        self.call(dict(self.request, SourceItems={"51": 1}))
        self.assertEqual(self.target(self.store.account.profile())["LimitBreaks"], 2)

    def test_canonical_delayed_retry_preserves_later_breaks_experience_and_removed_materials(self):
        request = dict(self.request, SourceItems={"50": 1, "52": 1})
        self.call(request)
        self.call(dict(self.request, SourceItems={"52": 1}), sequence=142)
        profile = self.store.account.profile()
        self.target(profile)["Experience"] = 777
        profile["User"]["ItemStackables"] = []
        self.save_profile(profile)
        self.limit_path.unlink()
        dump = list(self.db.iterdump())
        reordered = dict(request, SourceItems={"52": 1, "50": 1})
        self.assertEqual(self.call(reordered), {"User": profile["User"]})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.reject_without_writes(self.request)

    def test_reopening_reconnect_and_new_login_retain_receipts_and_reusable_hammers(self):
        first = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), first)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.open_session(False)
        self.call(self.request)
        after = self.store.account.profile()
        self.assertEqual(self.target(after)["LimitBreaks"], 5)
        self.assertEqual(after["User"]["ItemStackables"][0]["Amount"], 10)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM weapon_limit_break_requests").fetchone()[0], 2
        )

    def test_material_ownership_quantity_rarity_lock_and_saved_state_guards(self):
        for sources in ({"999": 1}, {"1": 1}, {"2": 1}, {"50": 11}, {"51": 1}):
            self.reject_without_writes(dict(self.request, SourceItems=sources))
        original = self.store.account.profile()
        for field, value in (
            ("Locked", True),
            ("Experience", True),
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

    def test_target_ownership_engraving_and_malformed_progress_guards(self):
        self.reject_without_writes(dict(self.request, TargetWeaponId=999))
        self.reject_without_writes(dict(self.request, TargetWeaponId=50))
        original = self.store.account.profile()
        for field, value in (
            ("Id", True),
            ("Amount", True),
            ("Amount", 2),
            ("Experience", -1),
            ("Experience", False),
            ("LimitBreaks", 5),
            ("LimitBreaks", True),
            ("LimitBreaks", -1),
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

    def test_exact_schema_identity_authentication_and_completed_prologue_required(self):
        for request in (
            None,
            {},
            [],
            dict(self.request, TargetWeaponId=True),
            dict(self.request, SourceItems={}),
            dict(self.request, SourceItems={"050": 1}),
            dict(self.request, SourceItems={"50": True}),
            dict(self.request, discountBuff=0),
            dict(self.request, Extra=0),
        ):
            self.reject_without_writes(request)
        for operation in (None, "", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.account.limit_break_weapon(self.request, operation)
        with sqlite3.connect(":memory:") as db:
            fresh = AccountStore(db, self.references)
            dump = list(db.iterdump())
            with self.assertRaises(ValueError):
                fresh.limit_break_weapon(self.request, "too-early")
            self.assertEqual(list(db.iterdump()), dump)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes(self.request)

    def test_explicit_matching_free_catalog_and_rarity_maps_required(self):
        original = copy.deepcopy(self.limit_catalog)
        for key, value in (
            ("client", {}),
            ("free", False),
            ("free", 1),
            ("weapons", {}),
            ("weapons", {"0101": 4}),
            ("weapons", {"101": True}),
            ("hammers", {"501": 5}),
            ("hammers", {"101": 4}),
            ("max_limit_breaks", 0),
            ("max_limit_breaks", True),
        ):
            self.limit_catalog = dict(original, **{key: value})
            self.write_limit_catalog()
            self.reject_without_writes(self.request)
        self.limit_path.write_bytes(b" " * (1024 * 1024 + 1))
        self.reject_without_writes(self.request)
        self.limit_path.unlink()
        self.reject_without_writes(self.request)

    def test_signed_revision_ceiling_allows_old_replay_but_blocks_new_breaks(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call(self.request)
        after = self.store.account.profile()
        self.assertEqual(after["User"]["Cas"], MAX_REVISION)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), {"User": after["User"]})
        with self.assertRaises(ValueError):
            self.store.account.limit_break_weapon(self.request, "new-overflow")
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_receipt_failure_rolls_back_breaks_revision_and_all_resources(self):
        self.db.execute(
            "CREATE TRIGGER reject_limit_break BEFORE INSERT ON weapon_limit_break_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_aggregate_hammer_count_overflow_rejects_before_clipping(self):
        profile = self.store.account.profile()
        for hammer in profile["User"]["ItemStackables"]:
            hammer["Amount"] = INT_MAX
        self.save_profile(profile)
        request = dict(self.request, SourceItems={"50": INT_MAX, "52": 1})
        self.reject_without_writes(request)
