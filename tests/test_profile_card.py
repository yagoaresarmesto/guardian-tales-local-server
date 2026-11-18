# SPDX-License-Identifier: Apache-2.0
"""Own cards and their empty friend prerequisite preserve all saved state."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from tests.test_snapshots import synthetic_snapshot

ROUTE = "/user/get-user-profile-card"
FRIEND_ROUTE = "/friend2/enter"
RECOMMEND_ROUTE = "/friend2/recommend"


class ProfileCardTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)

    def tearDown(self):
        self.db.close()

    def call(self, body, route=ROUTE):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=25)
            )
        )
        response = self.session.handle(request)
        self.assertEqual(response.sequence_id, 25)
        self.assertEqual(response.api, "")
        return read_json_body(parse_packet(encode_packet(response)))

    def login(self, reconnect=False):
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            "/auth/sign-in",
        )

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))

    def install_import(self):
        snapshot = synthetic_snapshot()
        with self.db:
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        self.save(snapshot["profile"])
        return snapshot["profile"]

    def assert_rejected_without_writes(self, body, route=ROUTE):
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, route)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_sign_in_and_exact_own_user_request_required_without_writes(self):
        self.assert_rejected_without_writes({"UserId": 1})
        self.login()
        for body in (
            None,
            {},
            [],
            1,
            {"UserId": True},
            {"UserId": "1"},
            {"UserId": 1.0},
            {"UserId": 0},
            {"UserId": -1},
            {"UserId": 0x80000000},
            {"UserId": 2},
            {"userId": 1},
            {"UserId": 1, "Claim": True},
        ):
            with self.subTest(body=body):
                self.assert_rejected_without_writes(body)

    def test_fresh_account_read_has_native_payloads_without_any_saved_changes(self):
        self.login()
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        for _ in range(2):
            reply = self.call({"UserId": 1})
            self.assertEqual(set(reply), {"UserProfileCard", "UserStickerPacks"})
            self.assertEqual(reply["UserProfileCard"]["User"], self.store.account.profile()["User"])
            self.assertEqual(reply["UserStickerPacks"], [])
            self.assertEqual(reply["UserProfileCard"]["AttachedStickers"], [])
            self.assertEqual(reply["UserProfileCard"]["Scarecrow"], [])
            self.assertIsNone(reply["UserProfileCard"]["Avatar"])
            self.assertIsNone(reply["UserProfileCard"]["SelectedBoard"])
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_imported_card_retains_entire_user_and_saved_records_without_writes(self):
        profile = self.install_import()
        profile["UserRecord"].update(ArenaTrophy=1234, ArenaRank=56, ColosseumTrophy=2345)
        profile["UserRecord"]["Misc"].update(
            ChampionArenaHighestRank=12,
            ChampionArenaHighestTrophy=3456,
            DeathMatchHighestRank=34,
            DeathMatchHighestTrophy=4567,
        )
        profile["UserProgress"]["TowerInfinity"]["Floor"] = -27
        profile["User"]["Options"]["UnrelatedSyntheticField"] = {"kept": [1, 2]}
        self.save(profile)
        self.login()
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        card = self.call({"UserId": 9400})["UserProfileCard"]
        self.assertEqual(card["User"], profile["User"])
        for key in ("ArenaTrophy", "ArenaRank", "ColosseumTrophy", "ColosseumRank"):
            self.assertEqual(card[key], profile["UserRecord"][key])
        for key in (
            "ChampionArenaHighestRank",
            "ChampionArenaHighestTrophy",
            "DeathMatchHighestRank",
            "DeathMatchHighestTrophy",
        ):
            self.assertEqual(card[key], profile["UserRecord"]["Misc"][key])
        self.assertEqual(card["TowerInfinityFloor"], -27)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.assert_rejected_without_writes({"UserId": 1})

    def test_repeated_reads_and_reconnects_reflect_later_profile_and_floor_changes(self):
        profile = self.install_import()
        self.login()
        first = self.call({"UserId": 9400})
        changed = copy.deepcopy(profile)
        changed["User"].update(Name="Updated", FrameId=7, Cas=profile["User"]["Cas"] + 1)
        changed["UserProgress"]["TowerInfinity"]["Floor"] = 28
        self.save(changed)
        for reconnect in (True, False):
            self.session = BootstrapSession(self.store)
            self.login(reconnect)
            before = list(self.db.iterdump())
            reply = self.call({"UserId": 9400})
            self.assertEqual(reply["UserProfileCard"]["User"], changed["User"])
            self.assertEqual(reply["UserProfileCard"]["TowerInfinityFloor"], 28)
            self.assertNotEqual(reply, first)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_absent_optional_records_remain_unknown_without_inventing_resources(self):
        profile = self.install_import()
        profile["UserRecord"] = {"Misc": {}}
        profile["UserProgress"]["TowerInfinity"] = {}
        self.save(profile)
        self.login()
        before = list(self.db.iterdump())
        card = self.call({"UserId": 9400})["UserProfileCard"]
        for key in (
            "ArenaRank",
            "ColosseumRank",
            "ChampionArenaHighestRank",
            "DeathMatchHighestRank",
            "TowerInfinityFloor",
            "GuildName",
            "PunchKingScore",
        ):
            self.assertIsNone(card[key])
        self.assertEqual(card["ArenaTrophy"], 0)
        self.assertFalse(card["UnlockFriend"])
        self.assertEqual(list(self.db.iterdump()), before)

    def test_reopened_import_can_be_read_with_sqlite_writes_disabled(self):
        self.install_import()
        self.login()
        first = self.call({"UserId": 9400})
        reopened = sqlite3.connect(":memory:")
        self.db.backup(reopened)
        self.db.close()
        self.db = reopened
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)
        self.login(True)
        self.db.execute("PRAGMA query_only=ON")
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        self.assertEqual(self.call({"UserId": 9400}), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_invalid_saved_native_record_types_reject_without_repairs(self):
        original = self.install_import()
        self.login()
        invalid_records = (
            ("UserRecord", None),
            ("UserRecord", {"Misc": []}),
            ("UserRecord", {"Misc": {}, "ArenaTrophy": True}),
            ("UserRecord", {"Misc": {}, "ColosseumRank": "4"}),
            ("UserRecord", {"Misc": {"DeathMatchHighestTrophy": 0x80000000}}),
            ("UserProgress", {"TowerInfinity": None}),
            ("UserProgress", {"TowerInfinity": {"Floor": False}}),
        )
        for section, value in invalid_records:
            with self.subTest(section=section, value=value):
                profile = copy.deepcopy(original)
                profile[section] = value
                self.save(profile)
                self.assert_rejected_without_writes({"UserId": 9400})

    def test_profile_customization_and_other_player_routes_remain_unsupported(self):
        self.install_import()
        self.login()
        before = list(self.db.iterdump())
        for route in ("/user/set-user-profile-card", "/user/set-profile-stickers"):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call({"UserId": 9400}, route)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assert_rejected_without_writes({"UserId": 9401})

    def test_friend_prerequisite_requires_sign_in_and_an_empty_native_body(self):
        self.assert_rejected_without_writes(None, FRIEND_ROUTE)
        self.login()
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        packet = parse_packet(
            encode_packet(Packet(0, b"", body_type=0, api=FRIEND_ROUTE, sequence_id=25))
        )
        self.assertEqual(
            json.loads(self.session.handle(packet).body),
            {"FriendInfos": {}, "IsMigrated": False},
        )
        for body in (None, {}):
            self.assertEqual(
                self.call(body, FRIEND_ROUTE), {"FriendInfos": {}, "IsMigrated": False}
            )
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        for invalid in ([], False, 0, "", {"UserId": 1}, {"Claim": True}):
            with self.subTest(body=invalid):
                self.assert_rejected_without_writes(invalid, FRIEND_ROUTE)

    def test_imported_friend_view_preserves_saved_counts_settings_and_gifts(self):
        profile = self.install_import()
        profile["UserFriend"].update(
            Enabled=True, AllowRequest=True, NumFriends=17, NumRequests=3, GiftCount=5, Cas=41
        )
        self.save(profile)
        self.login()
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        for _ in range(2):
            reply = self.call(None, FRIEND_ROUTE)
            self.assertIs(type(reply["FriendInfos"]), dict)
            self.assertEqual(reply["FriendInfos"], {})
            self.assertIs(reply["IsMigrated"], False)
            self.assertNotIn("UserFriend", reply)
            self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        for route in ("/friend2/request", "/friend2/send-gift", "/friend2/receive-gift"):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call({}, route)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_card_followed_by_friend_read_survives_reconnect_with_writes_disabled(self):
        profile = self.install_import()
        for reconnect in (False, True):
            self.session = BootstrapSession(self.store)
            self.login(reconnect)
            self.db.execute("PRAGMA query_only=ON")
            before = list(self.db.iterdump())
            changes = self.db.total_changes
            self.assertEqual(
                self.call({"UserId": 9400})["UserProfileCard"]["User"], profile["User"]
            )
            self.assertEqual(
                self.call(None, FRIEND_ROUTE), {"FriendInfos": {}, "IsMigrated": False}
            )
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.db.total_changes, changes)
            self.db.execute("PRAGMA query_only=OFF")

    def test_recommendations_require_authentication_and_exact_native_parameterless_body(self):
        self.assert_rejected_without_writes(None, RECOMMEND_ROUTE)
        self.login()
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        native = parse_packet(
            encode_packet(Packet(0, b"", body_type=0, api=RECOMMEND_ROUTE, sequence_id=25))
        )
        self.assertEqual(json.loads(self.session.handle(native).body), {"RecommendInfos": []})
        for body in (None, {}):
            self.assertEqual(self.call(body, RECOMMEND_ROUTE), {"RecommendInfos": []})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        for body in ([], False, 0, "", {"UserId": 1}, {"Count": 20}, {"Claim": True}):
            self.assert_rejected_without_writes(body, RECOMMEND_ROUTE)

    def test_empty_recommendations_preserve_saved_social_settings_counts_gifts_and_revisions(self):
        profile = self.install_import()
        profile["UserFriend"].update(
            Enabled=True,
            AllowRequest=False,
            NumFriends=17,
            NumRequests=3,
            GiftCount=5,
            Cas=42,
            SyntheticPendingGifts=[1, 2],
        )
        self.save(profile)
        self.login()
        self.db.execute("PRAGMA query_only=ON")
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        for _ in range(3):
            self.assertEqual(self.call(None, RECOMMEND_ROUTE), {"RecommendInfos": []})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_friend_entry_and_recommendations_reconnect_reads_do_not_enable_social_mutations(self):
        for imported in (False, True):
            if imported:
                self.install_import()
            for reconnect in (False, True):
                self.session = BootstrapSession(self.store)
                self.login(reconnect)
                self.db.execute("PRAGMA query_only=ON")
                before = list(self.db.iterdump())
                changes = self.db.total_changes
                self.assertEqual(
                    self.call(None, FRIEND_ROUTE), {"FriendInfos": {}, "IsMigrated": False}
                )
                self.assertEqual(self.call(None, RECOMMEND_ROUTE), {"RecommendInfos": []})
                for route in ("/friend2/request", "/friend2/send-gift", "/friend2/receive-gift"):
                    self.assert_rejected_without_writes({}, route)
                self.assertEqual(list(self.db.iterdump()), before)
                self.assertEqual(self.db.total_changes, changes)
                self.db.execute("PRAGMA query_only=OFF")
