# SPDX-License-Identifier: Apache-2.0
"""Ordered normal-party saves use compact resources and cannot undo newer choices."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.heroes.characters import new_character
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import MAX_REVISION
from guardian_tales.teams.party_members import ROUTE
from tests.account.test_snapshots import request as packet
from tests.village.test_village_harvest import NOW, VillageFixture


class PartyMemberTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        profile = self.store.account.profile()
        profile["User"]["Characters"].extend(new_character(i, 1000 + i) for i in (2, 3, 4))
        profile["User"]["CharacterIdCounter"] = 4
        profile["User"]["Party"]["SyntheticMetadata"] = {"Keep": True}
        self.save_profile(profile)
        self.request = {"CharacterIds": [2]}

    def call(self, body=None, route=ROUTE, sequence=591, now=NOW):
        return super().call(body, route, sequence, now)

    def expected_response(self, profile):
        return {"User": {k: profile["User"][k] for k in ("Id", "Cas", "Party")}}

    def test_ordered_four_member_save_changes_only_normal_party_and_user_revision(self):
        before = self.store.account.profile()
        source = self.source.read_bytes()
        reads = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()
        expected = copy.deepcopy(before)
        expected["User"]["Party"]["Characters"] = [4, 2, 1, 3]
        expected["User"]["Cas"] += 1
        result = self.call({"CharacterIds": [4, 2, 1, 3]})
        self.assertEqual(result, self.expected_response(expected))
        self.assertLess(len(json.dumps(result).encode()), 512)
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone(), reads
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM party_preset_state").fetchone(), (0,)
        )

    def test_shorter_party_replaces_all_old_slots_and_preserves_party_metadata(self):
        self.call({"CharacterIds": [4, 2, 1, 3]})
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        expected["User"]["Party"]["Characters"] = [3]
        expected["User"]["Cas"] += 1
        self.assertEqual(
            self.call({"CharacterIds": [3]}, sequence=592), self.expected_response(expected)
        )
        self.assertEqual(self.store.account.profile(), expected)

    def test_reordering_same_members_changes_leader_and_is_not_a_canonicalized_retry(self):
        self.call({"CharacterIds": [2, 3]})
        before = self.store.account.profile()
        self.reject_without_writes({"CharacterIds": [3, 2]})
        expected = copy.deepcopy(before)
        expected["User"]["Party"]["Characters"] = [3, 2]
        expected["User"]["Cas"] += 1
        self.call({"CharacterIds": [3, 2]}, sequence=592)
        self.assertEqual(self.store.account.profile(), expected)

    def test_unchanged_party_records_identity_without_incrementing_revision_or_rewriting_profile(
        self,
    ):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        writes = self.db.total_changes
        self.assertEqual(self.call({"CharacterIds": [1]}), self.expected_response(profile))
        self.assertEqual(self.db.total_changes, writes + 1)
        self.assertEqual(self.store.account.profile(), profile)
        writes = self.db.total_changes
        self.call({"CharacterIds": [1]})
        self.assertEqual(self.db.total_changes, writes)

    def test_delayed_retry_after_reopen_returns_current_party_and_preserves_later_equipment_edits(
        self,
    ):
        self.call(self.request)
        self.call({"CharacterIds": [4, 3]}, sequence=592)
        profile = self.store.account.profile()
        profile["User"]["ItemWeapons"][0]["JewelSlots"] = [280020]
        profile["User"]["Characters"][1]["Experience"] += 37
        self.save_profile(profile)
        self.open_session(reconnect=True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), self.expected_response(profile))
        self.assertEqual(list(self.db.iterdump()), before)

    def test_malformed_unknown_duplicate_and_spec_id_batches_cannot_change_any_state(self):
        for body in (
            None,
            {},
            {"CharacterIds": None},
            {"CharacterIds": []},
            {"CharacterIds": [1, 2, 3, 4, 1]},
            {"CharacterIds": [True]},
            {"CharacterIds": [1.0]},
            {"CharacterIds": ["2"]},
            {"CharacterIds": [0]},
            {"CharacterIds": [-1]},
            {"CharacterIds": [None]},
            {"CharacterIds": [2, 2]},
            {"CharacterIds": [2, 999]},
            {"CharacterIds": [1002]},
            {"CharacterIds": [2], "PartyId": 0},
        ):
            with self.subTest(body=str(body)):
                self.reject_without_writes(body)
        for identity in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.save_party_members(self.request, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_saved_roster_party_ownership_and_revision_are_guarded(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Cas=True),
            lambda p: p["User"].update(Cas=-1),
            lambda p: p["User"].update(Cas=MAX_REVISION),
            lambda p: p["User"].update(Party=None),
            lambda p: p["User"]["Party"].update(Id=True),
            lambda p: p["User"]["Party"].update(Id=1),
            lambda p: p["User"]["Party"].update(Characters=[999]),
            lambda p: p["User"]["Party"].update(Characters=[1, 1]),
            lambda p: p["User"]["Party"].update(Characters=[None]),
            lambda p: p["User"]["Characters"].append(copy.deepcopy(p["User"]["Characters"][0])),
            lambda p: p["User"]["Characters"][0].update(Id=True),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save_profile(profile)
            self.reject_without_writes(self.request)

    def test_late_profile_or_request_failure_rolls_back_formation_revision_and_receipt(self):
        for table, action in (("local_account", "UPDATE"), ("party_member_requests", "INSERT")):
            self.db.execute(
                f"CREATE TRIGGER reject_members BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.store.account.save_party_members(self.request, "rollback")
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_members")
            self.db.commit()

    def test_packet_authentication_fresh_signin_and_unfinished_prologue(self):
        with self.assertRaises(PacketError):
            BootstrapSession(self.store).handle(packet(ROUTE, self.request))
        self.call(self.request)
        self.open_session(reconnect=False)
        self.call({"CharacterIds": [3]})
        self.assertEqual(self.store.account.profile()["User"]["Party"]["Characters"], [3])
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.references).account
            before = account.profile()
            with self.assertRaises(ValueError):
                account.save_party_members({"CharacterIds": [1]}, "unfinished")
            self.assertEqual(account.profile(), before)
