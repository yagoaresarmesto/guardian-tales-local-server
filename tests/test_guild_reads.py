# SPDX-License-Identifier: Apache-2.0
"""Offline guild notices preserve membership, pending rewards and all saved state."""

import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from tests.test_snapshots import synthetic_snapshot

ROUTE = "/guild/red-dot"


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
