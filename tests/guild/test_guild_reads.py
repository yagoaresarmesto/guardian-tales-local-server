# SPDX-License-Identifier: Apache-2.0
"""Offline guild menu prerequisites preserve membership, rewards and saved state."""

import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from tests.account.test_snapshots import synthetic_snapshot

ROUTE = "/guild/red-dot"
RAID_PREPARATION = "/guild-raid2/reset"
OWN_GUILD = "/guild/get-my-guild"
ATTENDANCE_MOCK = "/guild/claim-guild-daily-attendance"


class GuildReadTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)

    def tearDown(self):
        self.db.close()

    def call(self, body=None, route=ROUTE, native_empty=False):
        request = parse_packet(
            encode_packet(
                Packet(
                    0,
                    b"" if native_empty else json.dumps(body).encode(),
                    body_type=0 if native_empty else 1,
                    api=route,
                    sequence_id=29,
                )
            )
        )
        response = self.session.handle(request)
        self.assertEqual(response.sequence_id, 29)
        self.assertEqual(response.api, "")
        self.assertEqual(response.body_type, 1)
        return json.loads(response.body)

    def login(self, reconnect=False):
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            "/auth/sign-in",
        )

    def test_attendance_mock_empty_rewards_preserve_fresh_and_imported_state_on_retry_and_reconnect(
        self,
    ):
        for imported in (False, True):
            with self.subTest(imported=imported):
                if imported:
                    snapshot = synthetic_snapshot()
                    profile = snapshot["profile"]
                    profile["GuildMember"] = {
                        "UserId": profile["User"]["Id"],
                        "GuildId": 7,
                        "Cas": 23,
                        "AttendanceCount": 11,
                        "LastAttendanceAt": "2026-11-17T00:00:00+00:00",
                    }
                    profile["UserClaimedReward"]["SyntheticGuildReward"] = {"Pending": [3, 4]}
                    with self.db:
                        self.db.execute(
                            "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                            ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
                        )
                        self.db.execute(
                            "UPDATE local_account SET profile=?", (json.dumps(profile),)
                        )
                profile = self.store.account.profile()
                for reconnect in (False, True):
                    self.store = GuestStore(self.db)
                    self.session = BootstrapSession(self.store)
                    self.login(reconnect)
                    self.db.execute("PRAGMA query_only=ON")
                    before = list(self.db.iterdump())
                    changes = self.db.total_changes
                    for body, native in ((None, True), (None, False), ({}, False), (None, True)):
                        reply = self.call(body, ATTENDANCE_MOCK, native_empty=native)
                        self.assertEqual(reply, {"AddedItems": []})
                    self.assertEqual(self.store.account.profile(), profile)
                    self.assertEqual(list(self.db.iterdump()), before)
                    self.assertEqual(self.db.total_changes, changes)
                    self.db.execute("PRAGMA query_only=OFF")

    def test_attendance_mock_requires_authentication_and_rejects_parameters_without_writes(self):
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(route=ATTENDANCE_MOCK, native_empty=True)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.login()
        self.db.execute("PRAGMA query_only=ON")
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        for body in ([], False, 0, "", {"GuildId": 7}, {"Day": 1}, {"Claim": True}):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, ATTENDANCE_MOCK)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_authentication_and_exact_parameterless_schema_reject_without_writes(self):
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(native_empty=True)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.login()
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        for body in ([], False, 0, "", {"GuildId": 1}, {"Claim": True}, {"Raid": True}):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_fresh_and_imported_reconnect_reads_hide_notices_without_clearing_saved_rewards(self):
        for imported in (False, True):
            with self.subTest(imported=imported):
                if imported:
                    snapshot = synthetic_snapshot()
                    profile = snapshot["profile"]
                    profile["GuildMember"] = {"GuildId": 7, "SyntheticPendingReward": 23}
                    profile["UserClaimedReward"]["SyntheticGuildReward"] = {"Pending": [3, 4]}
                    with self.db:
                        self.db.execute(
                            "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                            ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
                        )
                        self.db.execute(
                            "UPDATE local_account SET profile=?", (json.dumps(profile),)
                        )
                profile = self.store.account.profile()
                for reconnect in (False, True):
                    self.session = BootstrapSession(self.store)
                    self.login(reconnect)
                    self.db.execute("PRAGMA query_only=ON")
                    before = list(self.db.iterdump())
                    changes = self.db.total_changes
                    for body, native in ((None, True), (None, False), ({}, False)):
                        reply = self.call(body, native_empty=native)
                        self.assertEqual(set(reply), {"Raid", "Meteor", "PunchKing", "GuildWar"})
                        self.assertTrue(all(value is False for value in reply.values()))
                    self.assertEqual(self.store.account.profile(), profile)
                    self.assertEqual(list(self.db.iterdump()), before)
                    self.assertEqual(self.db.total_changes, changes)
                    self.db.execute("PRAGMA query_only=OFF")

    def test_raid_preparation_requires_sign_in_and_exact_boolean_cache_hint(self):
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call({"IsPartial": False}, RAID_PREPARATION)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.login()
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        for body in (
            None,
            {},
            [],
            False,
            {"IsPartial": 0},
            {"IsPartial": "false"},
            {"IsPartial": None},
            {"isPartial": False},
            {"IsPartial": False, "Claim": True},
            {"IsPartial": True, "Reset": True},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, RAID_PREPARATION)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_raid_preparation_reconnects_skip_claim_without_resetting_any_saved_resource(self):
        for imported in (False, True):
            with self.subTest(imported=imported):
                if imported:
                    snapshot = synthetic_snapshot()
                    with self.db:
                        self.db.execute(
                            "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                            ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
                        )
                        self.db.execute(
                            "UPDATE local_account SET profile=?",
                            (json.dumps(snapshot["profile"]),),
                        )
                profile = self.store.account.profile()
                profile["GuildMember"] = {"GuildId": 7, "SyntheticPendingReward": 23}
                profile["UserRaid"] = {
                    "Raid": {"SyntheticPendingSeasonReward": 12},
                    "SeasonClaimed": False,
                    "PunchKingCoins": 456,
                    "PickAxeCount": 42,
                }
                with self.db:
                    self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
                for reconnect in (False, True):
                    self.session = BootstrapSession(self.store)
                    self.login(reconnect)
                    self.db.execute("PRAGMA query_only=ON")
                    before = list(self.db.iterdump())
                    changes = self.db.total_changes
                    for partial in (False, True, False):
                        reply = self.call({"IsPartial": partial}, RAID_PREPARATION)
                        self.assertEqual(reply, {"ClaimRaidSeasonReward": False})
                        self.assertNotIn("UserRaid", reply)
                        self.assertNotIn("AddedItems", reply)
                    self.assertEqual(self.store.account.profile(), profile)
                    self.assertEqual(list(self.db.iterdump()), before)
                    self.assertEqual(self.db.total_changes, changes)
                    self.db.execute("PRAGMA query_only=OFF")
                before = list(self.db.iterdump())
                for route in (
                    "/guild-raid2/claim-season-rewards",
                    "/guild-raid2/abandon-stage",
                ):
                    with self.subTest(route=route), self.assertRaises(PacketError):
                        self.call({}, route)
                self.assertEqual(list(self.db.iterdump()), before)

    def test_own_guild_view_preserves_member_and_exposes_only_a_named_local_placeholder(self):
        self.login()
        self.assertEqual(
            self.call(None, OWN_GUILD),
            {"Hash": 0, "Guild": None, "GuildMember": None, "GuildMembers": []},
        )
        profile = self.store.account.profile()
        member = {
            "UserId": profile["User"]["Id"],
            "GuildId": 7,
            "Name": "Saved member",
            "Cas": 9,
            "Achievement": {"Id": 1, "Points": 30, "Rewarded": [2]},
        }
        profile["GuildMember"] = member
        snapshot = synthetic_snapshot()
        with self.db:
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.db.execute("PRAGMA query_only=ON")
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        reply = self.call({"Hash": 0}, OWN_GUILD)
        self.assertEqual(reply["Guild"]["Id"], 7)
        self.assertEqual(reply["Guild"]["Name"], "Local guild")
        self.assertEqual(reply["Guild"]["MemberCount"], 1)
        self.assertEqual(reply["Guild"]["Achievement"], {"Id": 1, "Points": 30})
        self.assertEqual(reply["Guild"]["Notices"], {"Notice": [], "RepresentativeNotice": 0})
        self.assertEqual(reply["GuildMember"], member)
        self.assertEqual(reply["GuildMembers"], [member])
        self.assertEqual(reply["Applicants"], [])
        self.assertEqual(reply["DismissedMasterName"], "")
        self.assertGreater(reply["Hash"], 0)
        self.assertEqual(self.call({"Hash": reply["Hash"]}, OWN_GUILD), reply)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.db.execute("PRAGMA query_only=OFF")
        member.update(Name="Updated member", Cas=10)
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        before = list(self.db.iterdump())
        changed = self.call({"Hash": reply["Hash"]}, OWN_GUILD)
        self.assertNotEqual(changed["Hash"], reply["Hash"])
        self.assertEqual(changed["GuildMembers"], [member])
        self.assertEqual(list(self.db.iterdump()), before)

    def test_own_guild_cache_hint_and_saved_membership_validation_never_repair_or_write(self):
        self.login()
        before = list(self.db.iterdump())
        for body in (
            [],
            False,
            0,
            {"Hash": True},
            {"Hash": "0"},
            {"Hash": 0x80000000},
            {"Claim": True},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, OWN_GUILD)
        self.assertEqual(list(self.db.iterdump()), before)
        for cache_hint in (None, {}, {"Hash": None}, {"Hash": -1}, {"Hash": 0x7FFFFFFF}):
            self.assertIsNone(self.call(cache_hint, OWN_GUILD)["Guild"])
        profile = self.store.account.profile()
        for invalid in (
            [],
            {"UserId": 2, "GuildId": 7},
            {"UserId": True, "GuildId": 7},
            {"UserId": 1, "GuildId": True},
            {"UserId": 1, "GuildId": -1},
            {"UserId": 1, "GuildId": 7, "Achievement": []},
            {"UserId": 1, "GuildId": 7, "Achievement": {"Id": 1, "Points": False}},
        ):
            with self.subTest(member=invalid):
                profile["GuildMember"] = invalid
                with self.db:
                    self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
                before = list(self.db.iterdump())
                changes = self.db.total_changes
                with self.assertRaises(PacketError):
                    self.call({"Hash": None}, OWN_GUILD)
                self.assertEqual(list(self.db.iterdump()), before)
                self.assertEqual(self.db.total_changes, changes)
