# SPDX-License-Identifier: Apache-2.0
"""Backroom entry has native response fields and never writes the saved account."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.characters import new_character
from guardian_tales.my_room import ROUTE
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.raid_static import compress, digest
from guardian_tales.village import MAX_REVISION
from tests.test_snapshots import synthetic_snapshot


def media_items():
    return [
        {
            "Id": 501,
            "Type": "MyRoomMedia",
            "GetMethod": "Default",
            "MediaType": "Wallpaper",
            "Price": 0,
        },
        {
            "Id": 502,
            "Type": "MyRoomMedia",
            "GetMethod": "Default",
            "MediaType": "Music",
            "Price": 0,
        },
        {
            "Id": 503,
            "Type": "MyRoomMedia",
            "GetMethod": "Sell",
            "MediaType": "Wallpaper",
            "Price": 300,
        },
        {"Id": 504, "Type": "MyRoomMedia", "GetMethod": "Limit", "MediaType": "Music", "Price": 0},
        {"Id": 505, "Type": "weapon"},
    ]


class MyRoomTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.items = media_items()
        self.static = self.root / "static_data_get.bin"
        self.write_items(self.items)
        self.store = GuestStore(self.db, self.root)
        snapshot = synthetic_snapshot()
        with self.db:
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        self.save(snapshot["profile"])
        self.open_session()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def write_items(self, items):
        content = json.dumps(items).encode()
        self.static.write_bytes(
            compress(b"items\n" + content + b"\n1\n" + digest(content).encode() + b"\n")
        )

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def open_session(self):
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": True}, "/auth/sign-in"
        )

    def call(self, body, route=ROUTE):
        packet = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=1901)
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(packet))))

    def assert_read(self, body):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        source = self.static.read_bytes()
        response = self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(self.static.read_bytes(), source)
        return response

    def reject(self, body):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_full_and_partial_native_requests_supply_room_without_profile_resources(self):
        expected = {
            "UserMyRoom": {
                "Used": [501, 502],
                "Hero": None,
                "X": 0.0,
                "Y": 0.0,
                "WallPaper": 0,
                "Music": 502,
                "Favorites": [],
            },
            "NewGetItems": [],
        }
        self.assertEqual(self.assert_read({"IsPartial": False}), expected)
        self.assertEqual(self.assert_read({"IsPartial": True}), expected)
        self.assertLess(len(json.dumps(expected).encode()), 256)

    def test_read_only_sqlite_preserves_profile_all_progress_and_imported_startup_rows(self):
        self.db.execute("PRAGMA query_only=ON")
        self.assert_read({"IsPartial": False})
        self.assert_read({"IsPartial": True})

    def test_representative_and_costume_are_dynamic_client_fallbacks(self):
        profile = self.store.account.profile()
        profile["User"]["Characters"].append(new_character(19, 70019))
        for representative in (None, 0, 1, 19):
            profile["User"]["RepresentativeCharacterId"] = representative
            self.save(profile)
            self.assertIsNone(self.assert_read({"IsPartial": False})["UserMyRoom"]["Hero"])
            self.assertEqual(self.store.account.profile(), profile)

    def test_no_paid_limited_media_or_new_rewards_are_granted(self):
        profile = self.store.account.profile()
        for asset in profile["User"]["Assets"]:
            asset["Amount"] = 0
        self.save(profile)
        reply = self.assert_read({"IsPartial": False})
        self.assertEqual(reply["UserMyRoom"]["Used"], [501, 502])
        self.assertEqual(reply["NewGetItems"], [])
        self.assertEqual(self.store.account.profile(), profile)

    def test_returned_collections_are_fresh_and_do_not_pollute_future_entries(self):
        reply = self.call({"IsPartial": False})
        reply["UserMyRoom"]["Used"].append(999)
        reply["UserMyRoom"]["Favorites"].append(999)
        reply["NewGetItems"].append(999)
        current = self.assert_read({"IsPartial": True})
        self.assertEqual(current["UserMyRoom"]["Used"], [501, 502])
        self.assertEqual(current["UserMyRoom"]["Favorites"], [])
        self.assertEqual(current["NewGetItems"], [])

    def test_native_exact_boolean_body_is_required(self):
        for body in (
            None,
            {},
            [],
            True,
            {"isPartial": False},
            {"IsPartial": None},
            {"IsPartial": 0},
            {"IsPartial": "false"},
            {"IsPartial": False, "UserId": 1},
        ):
            self.reject(body)

    def test_invalid_owner_roster_and_representative_reject_without_repair(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Id=True),
            lambda p: p["User"].update(Characters=[]),
            lambda p: p["User"].update(Characters=None),
            lambda p: p["User"]["Characters"].append(copy.deepcopy(p["User"]["Characters"][0])),
            lambda p: p["User"]["Characters"][0].update(Id=True),
            lambda p: p["User"].update(RepresentativeCharacterId=True),
            lambda p: p["User"].update(RepresentativeCharacterId=99),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject({"IsPartial": False})

    def test_missing_invalid_or_ambiguous_media_catalog_cannot_modify_state(self):
        self.static.unlink()
        self.reject({"IsPartial": False})
        for items in (
            [],
            None,
            [True],
            self.items[1:],
            [self.items[0], dict(self.items[0], Id=510), *self.items[1:]],
            [dict(self.items[0], Price=300), *self.items[1:]],
            [dict(self.items[0], Price=True), *self.items[1:]],
            [dict(self.items[0], MediaType="Unknown"), *self.items[1:]],
            [dict(self.items[0], Id=True), *self.items[1:]],
        ):
            self.write_items(items)
            self.reject({"IsPartial": False})

    def test_default_ids_are_derived_from_matching_items_instead_of_fixed_constants(self):
        items = media_items()
        items[0]["Id"], items[1]["Id"] = 810001, 820001
        self.write_items(items[::-1])
        room = self.assert_read({"IsPartial": False})["UserMyRoom"]
        self.assertEqual(room["Used"], [810001, 820001])
        self.assertEqual(room["Music"], 820001)
        self.assertEqual(room["WallPaper"], 0)

    def test_reopening_retains_account_and_does_not_create_room_storage(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save(profile)
        expected = self.assert_read({"IsPartial": False})
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session()
        self.assertEqual(self.assert_read({"IsPartial": False}), expected)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertFalse(
            self.db.execute("SELECT name FROM sqlite_master WHERE name LIKE '%my_room%'").fetchall()
        )

    def test_signin_and_completed_prologue_required_and_fresh_completed_account_supported(self):
        self.session.signed_in = False
        self.reject({"IsPartial": False})
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.root).account
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.read(ROUTE, {"IsPartial": False})
            self.assertEqual(list(db.iterdump()), before)
            account.complete_prologue(
                "Initial",
                {
                    "IsMale": True,
                    "VoiceType": 0,
                    "Weapon1ItemId": 101,
                    "Weapon2ItemId": 102,
                    "BobLindaQuestGrade": 0,
                },
            )
            self.assertEqual(
                account.read(ROUTE, {"IsPartial": False})["UserMyRoom"]["Used"], [501, 502]
            )

    def test_buy_changes_rewards_and_favorites_remain_separate_unsupported_operations(self):
        before = list(self.db.iterdump())
        for route in (
            "/my-room/buy-item",
            "/my-room/changes",
            "/my-room/claim-friendship-reward",
            "/my-room/mark-favorites-music",
        ):
            with self.assertRaises(PacketError):
                self.call({}, route)
        self.assertEqual(list(self.db.iterdump()), before)
