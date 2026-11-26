# SPDX-License-Identifier: Apache-2.0
"""Live-event entry reads saved families without resetting or awarding anything."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.rewards.live_events import EVENT_MAPS, ROUTE
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.settlement.village import MAX_REVISION
from tests.account.test_snapshots import request, synthetic_snapshot


class LiveEventTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)
        self.signin = {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False}
        self.session.handle(request("/auth/sign-in", self.signin))

    def call(self, body=None):
        return read_json_body(
            parse_packet(encode_packet(self.session.handle(request(ROUTE, body))))
        )

    def save(self, profile):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.commit()

    def imported(self):
        profile = synthetic_snapshot()["profile"]
        events = profile["UserEvent"]
        events["RoadmapEvents"] = {"7": {"Id": 7, "Points": 90, "ClaimedRewardNodeIds": [12]}}
        events["BingoEvents"] = {
            "9": {"Id": 9, "Coin": 3, "Round": 1, "CellNumbers": [4, 2], "MarkedIndices": [0]}
        }
        self.db.execute(
            "INSERT INTO imported_account VALUES(1,?,?,?,?)", ("0" * 64, "synthetic", "{}", "{}")
        )
        self.save(profile)
        return profile

    def assert_read(self, profile, body=None):
        before = list(self.db.iterdump())
        writes = self.db.total_changes
        self.assertEqual(self.call(body), {"UserEvent": profile["UserEvent"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def reject(self, body=None):
        before = list(self.db.iterdump())
        writes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_fresh_null_empty_and_empty_transport_bodies_return_existing_empty_event_state(self):
        profile = self.store.account.profile()
        self.assert_read(profile)
        self.assert_read(profile, {})
        packet = parse_packet(encode_packet(Packet(0, b"", body_type=0, api=ROUTE, sequence_id=31)))
        before = self.db.total_changes
        value = read_json_body(parse_packet(encode_packet(self.session.handle(packet))))
        self.assertEqual(value, {"UserEvent": profile["UserEvent"]})
        self.assertEqual(self.db.total_changes, before)

    def test_imported_roadmap_and_bingo_are_preserved_without_rewards_or_new_records(self):
        profile = self.imported()
        profile["UserEvent"]["SyntheticMetadata"] = {"Preserve": [1, 2]}
        self.save(profile)
        self.assert_read(profile)
        self.assertEqual(self.store.account.profile(), profile)
        response = self.call()
        response["UserEvent"]["RoadmapEvents"]["7"]["Points"] = 0
        self.assertEqual(self.store.account.profile(), profile)

    def test_all_native_event_families_and_nullable_return_record_are_read_without_mutation(self):
        profile = self.store.account.profile()
        for index, name in enumerate(EVENT_MAPS, 1):
            profile["UserEvent"][name] = {str(index): {"Id": index, "Synthetic": {"Counter": 4}}}
        profile["UserEvent"]["ReturnEvent"] = {"Id": 18, "SyntheticClaimedDays": [1]}
        self.save(profile)
        self.assert_read(profile)

    def test_request_parameters_and_wrong_body_types_reject_without_writes(self):
        self.imported()
        for body in ([], [1], False, 0, "", {"Id": 1}, {"SeasonId": 7}, {"Claim": True}):
            with self.subTest(body=body):
                self.reject(body)

    def test_missing_foreign_or_invalid_parent_state_rejects_and_maximum_revision_is_readable(self):
        original = self.imported()
        for mutate in (
            lambda p: p.update(UserEvent=None),
            lambda p: p["UserEvent"].update(UserId=1),
            lambda p: p["UserEvent"].update(UserId=True),
            lambda p: p["UserEvent"].update(Cas=-1),
            lambda p: p["UserEvent"].update(Cas=True),
            lambda p: p["UserEvent"].update(Cas=MAX_REVISION + 1),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject()
        profile = copy.deepcopy(original)
        profile["UserEvent"]["Cas"] = MAX_REVISION
        del profile["UserEvent"]["LiveEvents"]
        self.save(profile)
        self.assert_read(profile)

    def test_malformed_map_and_record_identities_reject_without_repairing_saved_state(self):
        original = self.imported()
        for value in (
            None,
            [],
            {"07": {"Id": 7}},
            {"7": None},
            {"7": {"Id": True}},
            {"7": {"Id": 8}},
            {"0": {"Id": 0}},
        ):
            profile = copy.deepcopy(original)
            profile["UserEvent"]["RoadmapEvents"] = value
            self.save(profile)
            self.reject()
        profile = copy.deepcopy(original)
        profile["UserEvent"]["ReturnEvent"] = []
        self.save(profile)
        self.reject()

    def test_reopen_and_reconnect_read_current_progress_instead_of_caching_an_earlier_response(
        self,
    ):
        profile = self.imported()
        self.assert_read(profile)
        profile["UserEvent"]["RoadmapEvents"]["7"]["Points"] += 4
        profile["UserEvent"]["Cas"] += 1
        self.save(profile)
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)
        self.session.handle(request("/auth/sign-in", {**self.signin, "Reconnect": True}))
        self.assert_read(profile)

    def test_authentication_mutation_boundary_and_existing_pass_reads(self):
        with self.assertRaises(PacketError):
            BootstrapSession(self.store).handle(request(ROUTE))
        profile = self.imported()
        self.assert_read(profile)
        before = list(self.db.iterdump())
        for route in ("/live-event/claim-point-rewards", "/live-event/clear-missions"):
            with self.assertRaises(PacketError):
                self.session.handle(request(route))
        for route, section in (
            ("/guardian-pass/enter", "UserGuardianPass"),
            ("/festival-pass/enter", "UserFestivalPass"),
        ):
            value = read_json_body(parse_packet(encode_packet(self.session.handle(request(route)))))
            self.assertEqual(value, {section: profile[section]})
        self.assertEqual(list(self.db.iterdump()), before)
