# SPDX-License-Identifier: Apache-2.0
"""Meteor menu contracts, season rollover and read-only account preservation."""

import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.guild_meteor import CATALOG, ROUTE
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import PacketError, encode_packet
from guardian_tales.snapshots import CLIENT
from tests.test_snapshots import request, synthetic_snapshot


class GuildMeteorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.catalog = {
            "client": CLIENT,
            "fresh_local": True,
            "seasons": [
                {"id": 7, "from": "2026-10-01T00:00:00Z"},
                {"id": 8, "from": "2026-11-19T00:00:00Z"},
            ],
        }
        self.write_catalog()
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.now = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
        clock = patch("guardian_tales.guild_meteor.utc_now", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def write_catalog(self):
        (self.root / CATALOG).write_text(json.dumps(self.catalog))

    def install(self, imported=True):
        profile = synthetic_snapshot()["profile"]
        profile["GuildMember"] = {"UserId": profile["User"]["Id"], "GuildId": 7}
        profile["UserRaid"] = {"Raid": None, "PickAxeCount": 17, "PunchKingCoins": 99}
        with self.db:
            if imported:
                self.db.execute(
                    "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                    ("0" * 64, "synthetic", "{}", "{}"),
                )
            else:
                self.db.execute("INSERT INTO prologue_selection VALUES(1,'synthetic','{}')")
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.session.handle(
            request(
                "/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False}
            )
        )
        return profile

    def call(self, value, route=ROUTE):
        return read_json_body(
            parse_packet(encode_packet(self.session.handle(request(route, value))))
        )

    def test_native_entry_collections_and_both_cache_hints_preserve_account_and_currencies(self):
        profile = self.install()
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for partial in (False, True, False):
            result = self.call({"IsPartial": partial})
            self.assertEqual(
                result["GuildRaid"],
                {"GuildId": 7, "MeteorSeasonId": 7, "MeteorStatus": [], "ExcavationStatus": {}},
            )
            self.assertEqual(result["MeteorExcavation"], [])
            self.assertEqual(result["AddedItems"], [])
            self.assertEqual(
                result["UserRaid"],
                {"UserId": profile["User"]["Id"], "MeteorSeasonId": 7, "MeteorClaimed": []},
            )
            self.assertNotIn("PickAxeCount", result["UserRaid"])
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_fresh_registered_guest_and_reconnect_roll_over_to_the_latest_started_season(self):
        profile = self.install(False)
        self.assertEqual(self.call({"IsPartial": False})["GuildRaid"]["MeteorSeasonId"], 7)
        self.now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.session.handle(
            request("/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": True})
        )
        self.assertEqual(self.call({"IsPartial": True})["GuildRaid"]["MeteorSeasonId"], 8)
        self.assertEqual(self.store.account.profile(), profile)

    def test_authentication_exact_schema_and_unimplemented_excavation_remain_guarded(self):
        with self.assertRaises(PacketError):
            self.call({"IsPartial": False})
        self.install()
        before = list(self.db.iterdump())
        for body in (
            None,
            {},
            [],
            {"isPartial": False},
            {"IsPartial": 0},
            {"IsPartial": False, "Claim": True},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body)
        for route in ("/guild-meteor/excavate", "/guild-meteor/claim-pickaxe"):
            with self.assertRaises(PacketError):
                self.call({}, route)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_missing_membership_saved_progress_and_bad_catalogs_reject_without_repair(self):
        original = self.install()
        for mutate in (
            lambda p: p.update(GuildMember=None),
            lambda p: p["GuildMember"].update(UserId=1),
            lambda p: p["UserRaid"].update(MeteorSeasonId=7),
            lambda p: p["UserRaid"].update(MeteorClaimed=[3]),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.call({"IsPartial": False})
            self.assertEqual(list(self.db.iterdump()), before)
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(original),))
        for mutate in (
            lambda c: c.update(fresh_local=False),
            lambda c: c["seasons"].append(c["seasons"][0]),
            lambda c: c["seasons"][0].update(id=True),
            lambda c: c["seasons"][0].update(**{"from": "2026-01-01"}),
        ):
            previous = self.catalog
            self.catalog = copy.deepcopy(previous)
            mutate(self.catalog)
            self.write_catalog()
            with self.assertRaises(PacketError):
                self.call({"IsPartial": False})
            self.catalog = previous
        (self.root / CATALOG).unlink()
        with self.assertRaises(PacketError):
            self.call({"IsPartial": False})
