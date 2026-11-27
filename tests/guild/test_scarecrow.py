# SPDX-License-Identifier: Apache-2.0
"""Exercise the Guild Castle practice protocol with a synthetic imported party."""

import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from guardian_tales.modes.guild.guild_menu import SCARECROW_INDIVIDUAL, SCARECROW_RECORDS
from guardian_tales.modes.guild.scarecrow import ELEMENT_NAMES, FINISH, START
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from tests.account.test_snapshots import synthetic_snapshot


class ScarecrowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db)
        snapshot = synthetic_snapshot()
        profile = snapshot["profile"]
        user = profile["User"]
        first = user["Characters"][0]
        self.first = first["Id"]
        user["Characters"].append(dict(first, Id=22, Weapon1=None, Weapon2=None, Costume=33))
        user["ItemMiscs"] = [{"Id": 32}, {"Id": 33}, {"Id": 34}]
        user["RepresentativeCharacterId"] = self.first
        member = {
            "UserId": user["Id"],
            "GuildId": 7,
            "UserRecords": {"ScarecrowFire": 8, "JoinMessage": "saved"},
        }
        profile["GuildMember"] = member
        members = [{"Id": 22, "Weapon1": 2, "Accessory": 32}, {"Id": self.first, "Weapon1": 1}]
        group = {"Presets": [{"Id": 1600, "Characters": members}]}
        snapshot["startup_reads"]["/preset/get-presets"]["value"]["UserPartyPreset2"] = group
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        self.session = BootstrapSession(self.store)
        self.login()
        self.start = {"ScarecrowId": 0, "elementalType": "Fire", "presetId": 1600}
        self.finish = {"ScarecrowId": 0, "Damages": [17, 25]}

    def call(self, route, seq, body):
        packet = Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=seq)
        reply = self.session.handle(parse_packet(encode_packet(packet)))
        self.assertEqual(reply.sequence_id, seq)
        return json.loads(reply.body)

    def login(self, reconnect=False):
        self.call(
            "/auth/sign-in", 1, {"AuthKind": 0, "AccessToken": "test", "Reconnect": reconnect}
        )

    def test_owned_preset_party_and_utc_start_survive_reconnect(self):
        before = self.store.account.profile()
        reply = self.call(START, 4, self.start)
        visitor = reply["CastleUser"]
        self.assertEqual(
            datetime.fromisoformat(reply["ScarecrowStartTime"]).utcoffset(), timedelta(0)
        )
        self.assertEqual(visitor["Party"]["Characters"], [22, self.first])
        self.assertEqual(visitor["RepresentativeCharacterId"], 22)
        self.assertEqual([row["Id"] for row in visitor["Characters"]], [22, self.first])
        self.assertEqual(visitor["Characters"][0]["Accessory1"], 32)
        self.assertIsNone(visitor["Characters"][1]["Weapon2"])
        self.assertEqual([i["Id"] for i in visitor["ItemMiscs"]], [32, 33])
        self.assertEqual([i["Id"] for i in visitor["ItemWeapons"]], [1, 2])
        self.assertNotIn("Assets", visitor)
        self.session = BootstrapSession(self.store)
        self.login(reconnect=True)
        self.assertEqual(self.call(START, 4, self.start), reply)
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(self.call(FINISH, 5, self.finish)["OldRecord"], 8)

    def test_all_six_elements_support_the_current_party_and_preserve_other_records(self):
        before = self.store.account.profile()
        for index, name in enumerate(ELEMENT_NAMES):
            for offset, element in enumerate((1 << index, name)):
                seq = 10 + index * 4 + offset * 2
                body = dict(self.start, elementalType=element, presetId=None if offset else 0)
                party = self.call(START, seq, body)["CastleUser"]["Party"]["Characters"]
                self.assertEqual(party, before["User"]["Party"]["Characters"])
                score = 2_000_000_000 + index
                damages = [score, score] if not offset else [1]
                reply = self.call(FINISH, seq + 1, dict(self.finish, Damages=damages))
                self.assertEqual(
                    reply["OldRecord"], 2 * score if offset else 8 if index == 1 else 0
                )
                self.assertEqual(
                    reply["GuildMember"]["UserRecords"][SCARECROW_RECORDS[index]], 2 * score
                )
        scores = [2 * (2_000_000_000 + i) for i in range(6)]
        self.assertEqual(self.call(SCARECROW_INDIVIDUAL, 45, {})["MyScore"], scores)
        before["GuildMember"]["UserRecords"].update(zip(SCARECROW_RECORDS, scores))
        self.assertEqual(self.store.account.profile(), before)

    def test_conflicting_stale_and_repeated_requests_cannot_finish_another_fight(self):
        self.call(START, 4, self.start)
        for seq, body in (
            (4, dict(self.start, elementalType=8)),
            (5, dict(self.start, presetId=9999)),
        ):
            with self.assertRaises(PacketError):
                self.call(START, seq, body)
        self.call(START, 7, dict(self.start, ScarecrowId=1))
        for seq, body in ((6, dict(self.finish, ScarecrowId=1)), (8, self.finish)):
            with self.assertRaises(PacketError):
                self.call(FINISH, seq, body)
        body = dict(self.finish, ScarecrowId=1)
        self.assertEqual(self.call(FINISH, 9, body)["OldRecord"], 8)
        self.call(START, 10, self.start)
        self.call(FINISH, 11, dict(self.finish, Damages=[61]))
        self.session = BootstrapSession(self.store)
        self.login(reconnect=True)
        replay = self.call(FINISH, 9, body)
        self.assertEqual(replay["OldRecord"], 8)
        self.assertEqual(replay["GuildMember"]["UserRecords"]["ScarecrowFire"], 61)
        for seq, request in ((9, dict(body, Damages=[])), (12, self.finish)):
            with self.assertRaises(PacketError):
                self.call(FINISH, seq, request)

    def test_bad_requests_and_failed_commit_preserve_the_battle_and_save(self):
        for field, value in (
            ("ScarecrowId", -1),
            ("elementalType", 3),
            ("elementalType", True),
            ("presetId", False),
        ):
            with self.assertRaises(PacketError):
                self.call(START, 4, dict(self.start, **{field: value}))
        self.call(START, 4, self.start)
        before = self.store.account.profile()
        for damages in (True, [True], [-1], [0] * 5, [(1 << 63) - 1, 1]):
            with self.assertRaises(PacketError):
                self.call(FINISH, 5, dict(self.finish, Damages=damages))
        self.db.execute(
            "CREATE TEMP TRIGGER fail_finish BEFORE UPDATE OF finish_seq ON scarecrow_runs BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(FINISH, 5, self.finish)
        self.assertEqual(self.store.account.profile(), before)
        self.db.execute("DROP TRIGGER fail_finish")
        self.assertEqual(self.call(FINISH, 5, dict(self.finish, Damages=[]))["OldRecord"], 8)
        self.assertEqual(self.store.account.profile(), before)

    def test_both_routes_require_a_signed_in_guild_member(self):
        self.session = BootstrapSession(self.store)
        profile = self.store.account.profile()
        profile.pop("GuildMember")
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        for logged_in in (False, True):
            if logged_in:
                self.login()
            for route, body in ((START, self.start), (FINISH, self.finish)):
                with self.assertRaises(PacketError):
                    self.call(route, 4, body)
