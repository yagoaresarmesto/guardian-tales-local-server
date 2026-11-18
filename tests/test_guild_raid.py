# SPDX-License-Identifier: Apache-2.0
"""Fresh raid content selection preserves the account and unrelated modes."""

import copy
import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.guild_raid import (
    CATALOG,
    ENTRY_ROUTE,
    SELECTION,
    load_catalog,
    main,
    select_season,
    selected_season,
)
from guardian_tales.protocol import PacketError
from guardian_tales.snapshots import CLIENT
from tests.test_snapshots import request, synthetic_snapshot


def synthetic_catalog():
    seasons = []
    for season_id in (1, 2):
        seasons.append(
            {
                "season_id": season_id,
                "boss_set": season_id,
                "round_set": 1,
                "period": {"from": "2020-01-01T00:00:00Z", "to": "2020-01-07T23:59:59Z"},
                "bosses": [
                    {"slot": n, "id": 1000 * season_id + n, "stage_id": 2000 * season_id + n}
                    for n in range(1, 5)
                ],
                "first_round": {
                    "number": 1,
                    "score": 800000,
                    "buff_level": 50,
                    "boss_hp_bar": 500000,
                },
            }
        )
    return {
        "client": dict(CLIENT),
        "fresh_local": True,
        "default_season_id": 2,
        "seasons": seasons,
        "daily_entries": 3,
        "max_retry": 5,
        "play_time_ms": 60000,
    }


class GuildRaidTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.catalog = synthetic_catalog()
        self.write_catalog()
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db, self.root)
        self.references = self.store.account.references
        self.session = BootstrapSession(self.store)

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def write_catalog(self, value=None):
        (self.root / CATALOG).write_text(
            json.dumps(self.catalog if value is None else value), encoding="utf-8"
        )

    def call(self, value, route=ENTRY_ROUTE):
        return json.loads(self.session.handle(request(route, value)).body)

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
        profile = snapshot["profile"]
        profile["GuildMember"] = {"UserId": 9400, "GuildId": 7}
        profile["UserRaid"] = {
            "Raid": None,
            "PunchKingCoins": 99,
            "PickAxeCount": 3,
            "SeasonClaimed": False,
        }
        with self.db:
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        self.save(profile)
        return profile

    def assert_rejected(self, value):
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(value)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_entry_requires_authentication_boolean_hint_prologue_and_owned_membership(self):
        self.assert_rejected({"IsPartial": False})
        self.login()
        self.assert_rejected({"IsPartial": False})
        profile = self.install_import()
        for value in (
            None,
            {},
            [],
            {"IsPartial": 0},
            {"IsPartial": "false"},
            {"IsPartial": True, "Claim": True},
        ):
            self.assert_rejected(value)
        for member in (None, {"UserId": 9401, "GuildId": 7}, {"UserId": 9400, "GuildId": 0}):
            self.save(dict(profile, GuildMember=member))
            self.assert_rejected({"IsPartial": False})

    @patch(
        "guardian_tales.guild_raid.utc_now",
        return_value=datetime(2026, 11, 18, 23, 59, tzinfo=timezone.utc),
    )
    def test_native_menu_reply_has_scalar_score_no_rewards_and_only_partial_raid_resource(
        self, _clock
    ):
        profile = self.install_import()
        self.login()
        self.db.execute("PRAGMA query_only=ON")
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        for partial in (False, True, False):
            reply = self.call({"IsPartial": partial})
            self.assertEqual(
                set(reply),
                {
                    "UserRaid",
                    "GuildRaidStatus",
                    "GuildRanking",
                    "FeverBossIdx",
                    "Round",
                    "RoundExp",
                    "AddedItems",
                },
            )
            self.assertEqual(set(reply["UserRaid"]), {"UserId", "Raid"})
            self.assertEqual(reply["UserRaid"]["UserId"], 9400)
            raid = reply["UserRaid"]["Raid"]
            self.assertEqual(raid["SeasonId"], 2)
            self.assertEqual(raid["NextReset"], "2026-11-19T00:00:00+00:00")
            self.assertEqual(raid["PlayedCharacters"], [])
            self.assertEqual(raid["TotalDamage"], 0)
            self.assertEqual(reply["GuildRaidStatus"]["SeasonId"], 2)
            self.assertIsNone(reply["GuildRanking"])
            self.assertEqual(reply["Round"], 1)
            self.assertIs(type(reply["RoundExp"]), int)
            self.assertEqual(reply["RoundExp"], 0)
            self.assertEqual(reply["AddedItems"], [])
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_live_selection_changes_next_entry_and_survives_reconnect_without_database_writes(self):
        self.install_import()
        self.login()
        before = list(self.db.iterdump())
        self.db.execute("PRAGMA query_only=ON")
        self.assertEqual(self.call({"IsPartial": False})["UserRaid"]["Raid"]["SeasonId"], 2)
        select_season(self.references, 1)
        self.assertEqual(self.call({"IsPartial": True})["UserRaid"]["Raid"]["SeasonId"], 1)
        self.assertEqual(list(self.db.iterdump()), before)
        self.db.execute("PRAGMA query_only=OFF")
        self.session = BootstrapSession(self.store)
        self.login(True)
        self.db.execute("PRAGMA query_only=ON")
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"IsPartial": False})["GuildRaidStatus"]["SeasonId"], 1)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), sorted((CATALOG, SELECTION)))

    def test_preserved_raid_progress_and_unknown_battle_operations_remain_guarded(self):
        profile = self.install_import()
        self.login()
        for saved in ({}, {"Raid": {}}, {"Raid": {"SeasonId": 1, "TotalDamage": 123}}, []):
            self.save(dict(profile, UserRaid=saved))
            if saved == {}:
                self.call({"IsPartial": False})
            else:
                self.assert_rejected({"IsPartial": False})
        self.save(profile)
        before = list(self.db.iterdump())
        for route in (
            "/guild-raid2/start-stage",
            "/guild-raid2/end-stage",
            "/guild-raid2/claim-season-rewards",
        ):
            with self.assertRaises(PacketError):
                self.call({}, route)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_missing_mismatched_and_invalid_catalogs_fail_without_account_repairs(self):
        self.install_import()
        self.login()
        (self.root / CATALOG).unlink()
        self.assert_rejected({"IsPartial": False})
        cases = []
        for key, value in (
            ("client", {}),
            ("fresh_local", False),
            ("default_season_id", 3),
            ("seasons", []),
            ("daily_entries", True),
        ):
            cases.append(dict(self.catalog, **{key: value}))
        bad = copy.deepcopy(self.catalog)
        bad["seasons"].append(bad["seasons"][0])
        cases.append(bad)
        for mutate in (
            lambda s: s["bosses"].pop(),
            lambda s: s["bosses"][0].update(slot=2),
            lambda s: s["bosses"][0].update(stage_id=True),
            lambda s: s["period"].update(to="2020-01-01"),
            lambda s: s["first_round"].update(number=True),
        ):
            bad = copy.deepcopy(self.catalog)
            mutate(bad["seasons"][0])
            cases.append(bad)
        for catalog in cases:
            self.write_catalog(catalog)
            self.assert_rejected({"IsPartial": False})

    def test_unknown_or_failed_selection_keeps_last_atomic_setting(self):
        select_season(self.references, 1)
        original = (self.root / SELECTION).read_bytes()
        for season_id in (True, 0, 3, "2"):
            with self.assertRaises(ValueError):
                select_season(self.references, season_id)
        with patch(
            "guardian_tales.guild_raid.os.replace", side_effect=OSError("synthetic failure")
        ):
            with self.assertRaises(OSError):
                select_season(self.references, 2)
        self.assertEqual((self.root / SELECTION).read_bytes(), original)
        self.assertEqual(selected_season(self.references)["season_id"], 1)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_invalid_saved_selection_is_rejected_instead_of_silently_defaulting(self):
        for value in (
            {"client": CLIENT, "season_id": 3},
            {"client": CLIENT, "season_id": True},
            {"client": {}, "season_id": 1},
            [],
        ):
            (self.root / SELECTION).write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                selected_season(self.references)
        (self.root / CATALOG).write_text(" " * (256 * 1024 + 1))
        with self.assertRaises(ValueError):
            load_catalog(self.references)

    def test_cli_lists_and_selects_only_catalogued_content(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["list", "--reference-dir", str(self.root)])
            main(["set", "1", "--reference-dir", str(self.root)])
        self.assertIn("Boss set", out.getvalue())
        self.assertIn('"selected_season_id": 1', out.getvalue())
        self.assertEqual(selected_season(self.references)["season_id"], 1)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["set", "3", "--reference-dir", str(self.root)])
