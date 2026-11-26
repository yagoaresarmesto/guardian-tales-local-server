# SPDX-License-Identifier: Apache-2.0
"""Orbital progress-only victories retain every resource and replay current state."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.modes.orbital.orbital import ORBITAL_EXIT_ROUTE, end
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import MAX_REVISION, current_village
from tests.village.test_village_harvest import NOW, VillageFixture


class OrbitalCompletionTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.floor_path = self.references / "orbital_entry_catalog.json"
        self.floor_path.write_text(json.dumps({"client": CLIENT, "floors": [1, 2, 3, 4, 5]}))
        self.completion_path = self.references / "orbital_completion_catalog.json"
        self.completion_path.write_text(json.dumps({"client": CLIENT, "no_rewards": True}))
        profile = self.store.account.profile()
        profile["UserProgress"]["Cas"] = 17
        profile["UserProgress"]["TowerInfinity"] = {
            "Floor": 2,
            "Formation": {"Id": 0, "Positions": [1, 2, 3, 4]},
        }
        self.save_profile(profile)
        self.request = {"floor": 3, "isCleared": True, "damages": [1, 22, 333, 4444]}

    def call(self, body=None, route=ORBITAL_EXIT_ROUTE, sequence=201, now=NOW):
        return super().call(body, route, sequence, now)

    def reject(self, body, sequence=201):
        dump = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_next_floor_win_changes_only_progress_floor_revision_and_has_no_reward_payload(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        expected["UserProgress"]["TowerInfinity"]["Floor"] = 3
        expected["UserProgress"]["Cas"] += 1
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        village = current_village(self.db)
        self.assertEqual(
            self.call(self.request),
            {
                "UserProgress": expected["UserProgress"],
                "TowerInfinity": expected["UserProgress"]["TowerInfinity"],
            },
        )
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(current_village(self.db), village)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(
            self.db.execute(
                "SELECT floor_before,floor_after FROM orbital_completion_requests"
            ).fetchone(),
            (2, 3),
        )

    def test_lower_or_same_floor_wins_preserve_signed_progress_revision_and_resources(self):
        profile = self.store.account.profile()
        profile["UserProgress"]["TowerInfinity"]["Floor"] = -3
        profile["UserProgress"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        for floor in (1, 3):
            self.call(dict(self.request, floor=floor), sequence=201 + floor)
            self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.db.execute(
                "SELECT floor_before,floor_after FROM orbital_completion_requests"
            ).fetchall(),
            [(-3, -3), (-3, -3)],
        )

    def test_ordered_new_clears_and_late_retries_retain_current_progress_without_duplicate_writes(
        self,
    ):
        self.call(self.request)
        self.call(dict(self.request, floor=4), sequence=202)
        current = self.store.account.profile()
        dump = list(self.db.iterdump())
        self.assertEqual(
            self.call(self.request),
            {
                "UserProgress": current["UserProgress"],
                "TowerInfinity": current["UserProgress"]["TowerInfinity"],
            },
        )
        self.assertEqual(list(self.db.iterdump()), dump)
        self.reject(dict(self.request, damages=[22, 1, 333, 4444]))
        self.call(dict(self.request, floor=1), sequence=203)
        self.assertEqual(self.store.account.profile(), current)

    def test_explicit_matching_no_reward_policy_required_for_new_wins(self):
        for value in (
            {},
            {"client": {}, "no_rewards": True},
            {"client": CLIENT, "no_rewards": False},
            {"client": CLIENT, "no_rewards": 1},
            {"client": CLIENT, "no_rewards": True, "Reward": 0},
        ):
            self.completion_path.write_text(json.dumps(value))
            self.reject(self.request)
        self.completion_path.write_bytes(b" " * 4097)
        self.reject(self.request)
        self.completion_path.unlink()
        self.reject(self.request)

    def test_authentication_identity_bounded_damage_and_next_floor_guards_precede_writes(self):
        for body in (
            None,
            {},
            [],
            dict(self.request, floor=4),
            dict(self.request, floor=99),
            dict(self.request, floor=True),
            dict(self.request, isCleared=1),
            dict(self.request, damages=[True]),
            dict(self.request, damages=[-1]),
            dict(self.request, damages=[0x80000000]),
            dict(self.request, damages=[0] * 5),
        ):
            self.reject(body)
        for operation in (None, "", "x" * 201):
            dump = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                end(self.store, self.request, operation)
            self.assertEqual(list(self.db.iterdump()), dump)
        self.session = BootstrapSession(self.store)
        self.reject(self.request)

    def test_progress_revision_ceiling_allows_old_retry_and_lower_win_but_not_advancement(self):
        profile = self.store.account.profile()
        profile["UserProgress"]["Cas"] = MAX_REVISION - 1
        self.save_profile(profile)
        self.call(self.request)
        self.assertEqual(self.store.account.profile()["UserProgress"]["Cas"], MAX_REVISION)
        dump = list(self.db.iterdump())
        self.call(self.request)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.reject(dict(self.request, floor=4), sequence=202)
        self.call(dict(self.request, floor=1), sequence=203)
        original = self.store.account.profile()
        for revision in (True, -1, MAX_REVISION + 1):
            profile = copy.deepcopy(original)
            profile["UserProgress"]["Cas"] = revision
            self.save_profile(profile)
            self.reject(dict(self.request, floor=1), sequence=204)

    def test_receipt_failure_rolls_back_floor_revision_and_all_other_saved_state(self):
        self.db.execute(
            "CREATE TRIGGER reject_orbital BEFORE INSERT ON orbital_completion_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        dump = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.request)
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_reopening_reconnect_new_login_and_earlier_floors_do_not_grant_or_reset_anything(self):
        response = self.call(self.request)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), response)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.open_session(False)
        profile = self.store.account.profile()
        self.call(self.request)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM orbital_completion_requests").fetchone()[0], 2
        )

    def test_old_receipt_remains_readable_without_policy_or_floor_catalog(self):
        response = self.call(self.request)
        self.completion_path.unlink()
        self.floor_path.unlink()
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), response)
        self.assertEqual(list(self.db.iterdump()), dump)
        self.reject(dict(self.request, floor=4), sequence=202)

    def test_non_clear_exit_with_policy_remains_wholly_read_only_and_does_not_create_receipt(self):
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(dict(self.request, isCleared=False)), {})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM orbital_completion_requests").fetchone()[0], 0
        )
