# SPDX-License-Identifier: Apache-2.0
"""Mastery spending updates one skill atomically and respects native class caps."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.settlement.mastery import MASTERY_POINTS, ROUTE
from guardian_tales.settlement.village import INT_MAX, MAX_REVISION, current_village
from tests.village.test_village_harvest import NOW, VillageFixture


class GuardianMasteryFixture(VillageFixture):
    def setUp(self):
        super().setUp()
        self.mastery_catalog = {
            "client": CLIENT,
            "portal_specs": [9001],
            "skills": {str(c * 100 + s): c for c in range(1, 5) for s in (1, 2)},
            "level_costs": [80 + 4 * i for i in range(12)],
        }
        self.mastery_path = self.references / "guardian_mastery_catalog.json"
        self.write_mastery_catalog()
        self.initial["Buildings"].append({"Id": 9, "SpecId": 9001, "Status": 2, "EndTime": NOW})
        self.save_village(self.initial)
        profile = self.store.account.profile()
        profile["User"].update(GuardianMasteryLevel=0)
        profile["User"]["Options"]["GuardianMastery"] = {
            "GuardianMasterySkill": {},
            "SkillNextResetTime": "2000-01-01T00:00:00+00:00",
        }
        self.asset(profile, MASTERY_POINTS).update(Amount=10000, Spent=-1)
        self.save_profile(profile)

    def write_mastery_catalog(self):
        self.mastery_path.write_text(json.dumps(self.mastery_catalog))

    def call(self, body=None, route=ROUTE, sequence=71, now=NOW):
        return super().call(body, route, sequence, now)

    def levels(self, profile):
        return profile["User"]["Options"]["GuardianMastery"]["GuardianMasterySkill"]

    def set_levels(self, levels):
        profile = self.store.account.profile()
        self.levels(profile).clear()
        self.levels(profile).update(levels)
        profile["User"]["GuardianMasteryLevel"] = sum(levels.values())
        self.save_profile(profile)


class GuardianMasteryTests(GuardianMasteryFixture, unittest.TestCase):
    def test_spend_changes_only_one_skill_total_asset_and_account_revision(self):
        before = self.store.account.profile()
        village = current_village(self.db)
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        expected = copy.deepcopy(before)
        self.levels(expected)["101"] = 1
        expected["User"]["GuardianMasteryLevel"] += 1
        expected["User"]["Cas"] += 1
        self.asset(expected, MASTERY_POINTS)["Amount"] -= 80
        self.asset(expected, MASTERY_POINTS)["Spent"] += 80
        self.assertEqual(self.call({"SkillId": 101}), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )

    def test_next_cost_uses_selected_skill_level_and_exact_balance_can_be_spent(self):
        self.set_levels({"101": 2, "201": 7})
        profile = self.store.account.profile()
        self.asset(profile, MASTERY_POINTS)["Amount"] = 88
        self.save_profile(profile)
        self.call({"SkillId": 101})
        saved = self.store.account.profile()
        self.assertEqual(self.asset(saved, MASTERY_POINTS)["Amount"], 0)
        self.assertEqual(self.levels(saved), {"101": 3, "201": 7})
        self.assertEqual(saved["User"]["GuardianMasteryLevel"], 10)

    def test_class_cap_blocks_concentration_and_opens_after_all_classes_advance(self):
        self.set_levels({"101": 10})
        self.reject_without_writes({"SkillId": 102})
        self.set_levels({str(c * 100 + 1): 10 for c in range(1, 5)})
        self.call({"SkillId": 102})
        self.assertEqual(self.levels(self.store.account.profile())["102"], 1)

    def test_individual_skill_max_and_aggregate_cap_are_separate(self):
        self.set_levels({str(c * 100 + 1): 12 for c in range(1, 5)})
        self.reject_without_writes({"SkillId": 101})
        self.call({"SkillId": 102})
        self.assertEqual(self.levels(self.store.account.profile())["102"], 1)

    def test_delayed_retry_returns_current_user_without_recharge_or_catalog(self):
        self.call({"SkillId": 101})
        self.call({"SkillId": 201}, sequence=72)
        self.mastery_path.unlink()
        expected = self.store.account.profile()
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"SkillId": 101}), {"User": expected["User"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes({"SkillId": 201})

    def test_reconnect_reopening_reuses_receipt_and_new_login_permits_new_spend(self):
        self.call({"SkillId": 101})
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.call({"SkillId": 101})
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.call({"SkillId": 101})
        self.assertEqual(self.levels(self.store.account.profile())["101"], 2)

    def test_authentication_and_exact_integer_request_schema(self):
        for body in (
            None,
            {},
            [],
            {"SkillId": True},
            {"SkillId": "101"},
            {"SkillId": 0},
            {"SkillId": 999},
            {"SkillId": 101, "Amount": 100000000},
        ):
            self.reject_without_writes(body)
        self.session = BootstrapSession(self.store)
        self.reject_without_writes({"SkillId": 101})

    def test_missing_or_unopened_upgraded_camp_and_wrong_owner_reject(self):
        for field, value in (("SpecId", 9999), ("Status", 0), ("Status", True)):
            village = copy.deepcopy(self.initial)
            village["Buildings"][-1][field] = value
            self.save_village(village)
            self.reject_without_writes({"SkillId": 101})
        village = copy.deepcopy(self.initial)
        village["UserId"] += 1
        self.save_village(village)
        self.reject_without_writes({"SkillId": 101})
        village = copy.deepcopy(self.initial)
        village["Buildings"].append(dict(village["Buildings"][-1], Id=10))
        self.save_village(village)
        self.reject_without_writes({"SkillId": 101})

    def test_invalid_saved_levels_and_mismatching_total_reject(self):
        original = self.store.account.profile()
        for levels in (None, {"999": 1}, {"0101": 1}, {"101": True}, {"101": -1}, {"101": 13}):
            profile = copy.deepcopy(original)
            profile["User"]["Options"]["GuardianMastery"]["GuardianMasterySkill"] = levels
            self.save_profile(profile)
            self.reject_without_writes({"SkillId": 101})
        original["User"]["GuardianMasteryLevel"] = 1
        self.save_profile(original)
        self.reject_without_writes({"SkillId": 101})

    def test_insufficient_invalid_or_ambiguous_asset_rejects_without_spending(self):
        original = self.store.account.profile()
        for field, value in (
            ("Amount", 79),
            ("Amount", True),
            ("Spent", INT_MAX - 79),
            ("Spent", "bad"),
        ):
            profile = copy.deepcopy(original)
            self.asset(profile, MASTERY_POINTS)[field] = value
            self.save_profile(profile)
            self.reject_without_writes({"SkillId": 101})
        for duplicate in (False, True):
            profile = copy.deepcopy(original)
            asset = self.asset(profile, MASTERY_POINTS)
            if duplicate:
                profile["User"]["Assets"].append(dict(asset))
            else:
                profile["User"]["Assets"].remove(asset)
            self.save_profile(profile)
            self.reject_without_writes({"SkillId": 101})

    def test_revision_limit_rejects_but_replay_at_limit_does_not_write(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call({"SkillId": 101})
        before = list(self.db.iterdump())
        self.call({"SkillId": 101})
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes({"SkillId": 201})
        with self.assertRaises(ValueError):
            self.store.account.upgrade_guardian_mastery({"SkillId": 201}, "new-operation")
        self.assertEqual(list(self.db.iterdump()), before)

    def test_catalog_requires_matching_client_canonical_skills_classes_and_positive_costs(self):
        original = copy.deepcopy(self.mastery_catalog)
        for key, value in (
            ("client", {}),
            ("portal_specs", [True]),
            ("skills", {"101": 1}),
            ("skills", dict(original["skills"], **{"0101": 1})),
            ("skills", dict(original["skills"], **{"101": True})),
            ("level_costs", [0]),
            ("level_costs", [True]),
            ("level_costs", []),
        ):
            self.mastery_catalog = dict(original, **{key: value})
            self.write_mastery_catalog()
            self.reject_without_writes({"SkillId": 101})
        self.mastery_path.write_text(" " * 65537)
        self.reject_without_writes({"SkillId": 101})
        self.mastery_path.unlink()
        self.reject_without_writes({"SkillId": 101})

    def test_receipt_failure_rolls_back_profile_debit_and_level(self):
        self.db.execute(
            "CREATE TRIGGER reject_mastery BEFORE INSERT ON mastery_level_requests "
            "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call({"SkillId": 101})
        self.assertEqual(list(self.db.iterdump()), before)
