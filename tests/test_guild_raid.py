# SPDX-License-Identifier: Apache-2.0
"""Fresh raid content selection preserves the account and unrelated modes."""

import base64
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
    BATTLE_STATUS,
    BOSS_RECORDS,
    CATALOG,
    ENTRY_ROUTE,
    GUILD_RANKINGS,
    LATEST_RECORDS,
    MEMBER_RANKINGS,
    MEMBER_RECORDS,
    SELECTION,
    UPDATE_STATUS,
    load_catalog,
    main,
    select_season,
    selected_season,
)
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.raid_static import compress, digest
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


def synthetic_static(catalog):
    raid = {"Seasons": [], "Boss": [], "BossDetails": []}
    dates = []
    for season in catalog["seasons"]:
        date_id = 5400000 + season["season_id"]
        raid["Seasons"].append(
            {
                "Id": season["season_id"],
                "SeasonDateId": date_id,
                "BossSet": season["boss_set"],
                "RoundSet": season["round_set"],
            }
        )
        for boss in season["bosses"]:
            raid["Boss"].append(
                {"SetId": season["boss_set"], "Slot": boss["slot"], "Id": boss["id"]}
            )
            raid["BossDetails"].append({"Id": boss["id"], "StageId": boss["stage_id"]})
        dates.append(
            {
                "Id": date_id,
                "From": {
                    "KakaoGlobal": season["period"]["from"],
                    "KakaoKorea": "2019-01-01T00:00:00Z",
                },
                "To": {"KakaoGlobal": season["period"]["to"], "KakaoKorea": "2019-01-08T00:00:00Z"},
                "RewardUntil": {"KakaoGlobal": "2020-01-14T00:00:00Z"},
            }
        )
    dates.append(
        {
            "Id": 99,
            "From": {"KakaoGlobal": "2026-01-01T00:00:00Z"},
            "To": {"KakaoGlobal": "2027-01-01T00:00:00Z"},
        }
    )
    rows = [
        ("guildraid2", json.dumps(raid)),
        ("seasondate", json.dumps({"EventPeriod": dates})),
        ("unrelated", '{"Keep":[1,2]}'),
        ("heroes-bin", base64.b64encode(b"synthetic binary data").decode()),
        ("__checksum__", digest(b"synthetic")),
    ]
    raw = (
        "".join(
            f"{name}\n{content}\n1\n{digest(base64.b64decode(content) if name.endswith('-bin') else content.encode())}\n"
            for name, content in rows
        )
        + "\n\n\n"
    )
    return compress(raw.encode())


class GuildRaidTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.catalog = synthetic_catalog()
        self.write_catalog()
        (self.root / "static_data_get.bin").write_bytes(synthetic_static(self.catalog))
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

    def assert_rejected(self, value, route=ENTRY_ROUTE):
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(value, route)
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
        self.assertTrue((self.root / SELECTION).is_file())
        self.assertEqual(len(list(self.root.glob("guild_raid_static_*.bin"))), 1)
        self.assertFalse(list(self.root.glob(".raid-*")))

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
        original_replace = os.replace

        def fail_selection(source, destination):
            if Path(destination).name == SELECTION:
                raise OSError("synthetic selection publication failure")
            return original_replace(source, destination)

        with patch("guardian_tales.guild_raid.os.replace", side_effect=fail_selection):
            with self.assertRaises(OSError):
                select_season(self.references, 2)
        self.assertEqual((self.root / SELECTION).read_bytes(), original)
        self.assertEqual(selected_season(self.references)["season_id"], 1)
        self.assertFalse(list(self.root.glob(".raid-*")))

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
        self.assertIn("Fully close and reopen the game", out.getvalue())
        self.assertEqual(selected_season(self.references)["season_id"], 1)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["set", "3", "--reference-dir", str(self.root)])

    def test_rankings_require_authentication_exact_integer_season_and_valid_local_membership(self):
        for route in (GUILD_RANKINGS, MEMBER_RANKINGS):
            self.assert_rejected({"SeasonId": 1}, route)
        self.login()
        for route in (GUILD_RANKINGS, MEMBER_RANKINGS):
            self.assert_rejected({"SeasonId": 1}, route)
        self.install_import()
        for route in (GUILD_RANKINGS, MEMBER_RANKINGS):
            for body in (
                None,
                {},
                [],
                {"SeasonId": True},
                {"SeasonId": 0},
                {"SeasonId": -1},
                {"SeasonId": 0x80000000},
                {"SeasonId": "1"},
                {"SeasonId": 1.0},
                {"SeasonId": 3},
                {"seasonId": 1},
                {"SeasonId": 1, "Claim": True},
            ):
                with self.subTest(route=route, body=body):
                    self.assert_rejected(body, route)
        profile = self.store.account.profile()
        self.save(dict(profile, GuildMember={"UserId": 9401, "GuildId": 7}))
        for route in (GUILD_RANKINGS, MEMBER_RANKINGS):
            self.assert_rejected({"SeasonId": 1}, route)

    def test_empty_rankings_reconnect_reads_preserve_all_progress_rewards_and_selection(self):
        profile = self.install_import()
        profile["UserRaid"].update(
            Raid={"SeasonId": 1, "TotalDamage": 123, "PlayCount": 2}, SyntheticPendingReward=[4]
        )
        self.save(profile)
        select_season(self.references, 2)
        selection = (self.root / SELECTION).read_bytes()
        for reconnect in (False, True):
            self.session = BootstrapSession(self.store)
            self.login(reconnect)
            self.db.execute("PRAGMA query_only=ON")
            before = list(self.db.iterdump())
            changes = self.db.total_changes
            for season_id in (1, 2, 1):
                self.assertEqual(
                    self.call({"SeasonId": season_id}, GUILD_RANKINGS),
                    {"Rankings": [], "CutOff": {}},
                )
                self.assertEqual(
                    self.call({"SeasonId": season_id}, MEMBER_RANKINGS), {"Rankings": []}
                )
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.db.total_changes, changes)
            self.assertEqual(self.store.account.profile(), profile)
            self.assertEqual((self.root / SELECTION).read_bytes(), selection)
            self.db.execute("PRAGMA query_only=OFF")

    def test_rankings_reject_missing_and_foreign_catalogs_without_writes(self):
        self.install_import()
        self.login()
        (self.root / CATALOG).unlink()
        for route in (GUILD_RANKINGS, MEMBER_RANKINGS):
            self.assert_rejected({"SeasonId": 1}, route)
        self.write_catalog(dict(self.catalog, client={"version": "other"}))
        for route in (GUILD_RANKINGS, MEMBER_RANKINGS):
            self.assert_rejected({"SeasonId": 1}, route)

    def test_raid_menu_history_reads_require_authentication_membership_and_exact_native_requests(
        self,
    ):
        valid = (
            (UPDATE_STATUS, None),
            (BATTLE_STATUS, {"SeasonId": 1}),
            (LATEST_RECORDS, {"SeasonId": 1, "Count": 20}),
        )
        for route, body in valid:
            self.assert_rejected(body, route)
        self.login()
        for route, body in valid:
            self.assert_rejected(body, route)
        self.install_import()
        for body in ([], False, 0, {"Round": 1}, {"Claim": True}):
            self.assert_rejected(body, UPDATE_STATUS)
        for route in (BATTLE_STATUS, LATEST_RECORDS):
            for season_id in (True, 0, -1, "1", 1.0, 3, 0x80000000):
                body = {"SeasonId": season_id}
                if route == LATEST_RECORDS:
                    body["Count"] = 20
                self.assert_rejected(body, route)
            self.assert_rejected(None, route)
            self.assert_rejected({"SeasonId": 1, "Count": 20, "Claim": True}, route)
        self.assert_rejected({"SeasonId": 1, "Count": 20}, BATTLE_STATUS)
        self.assert_rejected({"SeasonId": 1}, LATEST_RECORDS)
        for count in (True, -1, "20", 20.0, 0x80000000):
            self.assert_rejected({"SeasonId": 1, "Count": count}, LATEST_RECORDS)

    def test_empty_history_accepts_known_cached_seasons_without_changing_saved_progress_or_selection(
        self,
    ):
        profile = self.install_import()
        profile["UserRaid"].update(
            Raid={"SeasonId": 2, "TotalDamage": 456, "PlayCount": 2}, SyntheticPendingReward=[5]
        )
        self.save(profile)
        select_season(self.references, 2)
        selection = (self.root / SELECTION).read_bytes()
        for reconnect in (False, True):
            self.session = BootstrapSession(self.store)
            self.login(reconnect)
            self.db.execute("PRAGMA query_only=ON")
            before = list(self.db.iterdump())
            changes = self.db.total_changes
            for season in (1, 2, 1):
                self.assertEqual(self.call({"SeasonId": season}, BATTLE_STATUS), {"Records": []})
                for count in (0, 20, 0x7FFFFFFF):
                    self.assertEqual(
                        self.call({"SeasonId": season, "Count": count}, LATEST_RECORDS),
                        {"BattleRecords": []},
                    )
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.db.total_changes, changes)
            self.assertEqual(self.store.account.profile(), profile)
            self.assertEqual((self.root / SELECTION).read_bytes(), selection)
            self.db.execute("PRAGMA query_only=OFF")

    def test_boss_status_refresh_is_native_parameterless_fresh_round_without_rewards_or_writes(
        self,
    ):
        self.install_import()
        self.login()
        self.db.execute("PRAGMA query_only=ON")
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        expected = {"FeverBossIdx": 0, "Round": 1, "RoundExp": 0}
        for body in (None, {}, None):
            self.assertEqual(self.call(body, UPDATE_STATUS), expected)
        native = parse_packet(
            encode_packet(Packet(0, b"", body_type=0, api=UPDATE_STATUS, sequence_id=31))
        )
        reply = self.session.handle(native)
        self.assertEqual(json.loads(reply.body), expected)
        self.assertEqual(reply.sequence_id, 31)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_raid_menu_missing_catalog_and_saved_progress_do_not_get_silently_reset(self):
        profile = self.install_import()
        self.login()
        self.save(dict(profile, UserRaid={"Raid": {"SeasonId": 1, "TotalDamage": 42}}))
        self.assert_rejected(None, UPDATE_STATUS)
        self.save(dict(profile, GuildMember={"UserId": 9401, "GuildId": 7}))
        self.assert_rejected({"SeasonId": 1}, BATTLE_STATUS)
        self.save(profile)
        (self.root / CATALOG).unlink()
        for route, body in (
            (UPDATE_STATUS, None),
            (BATTLE_STATUS, {"SeasonId": 1}),
            (LATEST_RECORDS, {"SeasonId": 1, "Count": 20}),
        ):
            self.assert_rejected(body, route)

        self.write_catalog(dict(self.catalog, client={"version": "other"}))
        for route, body in (
            (UPDATE_STATUS, None),
            (BATTLE_STATUS, {"SeasonId": 1}),
            (LATEST_RECORDS, {"SeasonId": 1, "Count": 20}),
        ):
            self.assert_rejected(body, route)

    def test_boss_and_member_history_require_authenticated_exact_native_integer_schemas(self):
        valid = (
            (BOSS_RECORDS, {"SeasonId": 1, "BossId": 1001}),
            (MEMBER_RECORDS, {"SeasonId": 1, "Day": 0, "UserId": 9400}),
        )
        for route, body in valid:
            self.assert_rejected(body, route)
        self.login()
        for route, body in valid:
            self.assert_rejected(body, route)
        self.install_import()
        for route, body in valid:
            self.assert_rejected(None, route)
            self.assert_rejected(dict(body, Count=20), route)
            self.assert_rejected(dict(body, Claim=True), route)
            for key in body:
                missing = dict(body)
                del missing[key]
                self.assert_rejected(missing, route)
                for value in (True, -1, "1", 1.0, 0x80000000):
                    self.assert_rejected(dict(body, **{key: value}), route)

    def test_boss_and_member_history_validate_season_boss_membership_and_owned_user(self):
        profile = self.install_import()
        self.login()
        for body in (
            {"SeasonId": 3, "BossId": 1001},
            {"SeasonId": 1, "BossId": 0},
            {"SeasonId": 1, "BossId": 9999},
            {"SeasonId": 1, "BossId": 2001},
        ):
            self.assert_rejected(body, BOSS_RECORDS)
        self.assert_rejected({"SeasonId": 1, "Day": 0, "UserId": 9401}, MEMBER_RECORDS)
        self.assert_rejected({"SeasonId": 3, "Day": 0, "UserId": 9400}, MEMBER_RECORDS)
        self.save(dict(profile, GuildMember={"UserId": 9401, "GuildId": 7}))
        self.assert_rejected({"SeasonId": 1, "BossId": 1001}, BOSS_RECORDS)
        self.save(profile)
        (self.root / CATALOG).unlink()
        for route, body in (
            (BOSS_RECORDS, {"SeasonId": 1, "BossId": 1001}),
            (MEMBER_RECORDS, {"SeasonId": 1, "Day": 0, "UserId": 9400}),
        ):
            self.assert_rejected(body, route)

    def test_empty_boss_and_member_history_preserves_all_saved_progress_and_selection_across_reconnect(
        self,
    ):
        profile = self.install_import()
        profile["UserRaid"].update(
            Raid={"SeasonId": 2, "TotalDamage": 987, "PlayCount": 1}, SyntheticPendingReward=[6]
        )
        self.save(profile)
        select_season(self.references, 2)
        selection = (self.root / SELECTION).read_bytes()
        for reconnect in (False, True):
            self.session = BootstrapSession(self.store)
            self.login(reconnect)
            self.db.execute("PRAGMA query_only=ON")
            before = list(self.db.iterdump())
            changes = self.db.total_changes
            for season in self.catalog["seasons"]:
                for boss in season["bosses"]:
                    self.assertEqual(
                        self.call(
                            {"SeasonId": season["season_id"], "BossId": boss["id"]}, BOSS_RECORDS
                        ),
                        {"BattleRecords": []},
                    )
                for day in (0, 6, 0x7FFFFFFF):
                    self.assertEqual(
                        self.call(
                            {"SeasonId": season["season_id"], "Day": day, "UserId": 9400},
                            MEMBER_RECORDS,
                        ),
                        {"BattleRecords": []},
                    )
            self.assertEqual(self.db.total_changes, changes)
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.store.account.profile(), profile)
            self.assertEqual((self.root / SELECTION).read_bytes(), selection)
            self.db.execute("PRAGMA query_only=OFF")
