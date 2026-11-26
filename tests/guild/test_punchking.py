# SPDX-License-Identifier: Apache-2.0
"""All arena rotation/day combinations compose with raids and preserve saved accounts."""

import base64
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.guild_raid import CATALOG as RAID_CATALOG
from guardian_tales.guild_raid import SELECTION_LOCK, select_season
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.punchking import CATALOG, END, ENTRY, RANKINGS, SELECTION, START, main
from guardian_tales.punchking_static import bootstrap_override, load_selection, select
from guardian_tales.raid_panel import RaidPanel
from guardian_tales.raid_static import compress, decode, digest, records
from guardian_tales.snapshots import CLIENT, import_snapshot
from guardian_tales.state_lock import StateLock
from tests.account.test_snapshots import synthetic_snapshot
from tests.guild.test_guild_raid import synthetic_catalog, synthetic_static


class PunchkingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
        for target in (
            "guardian_tales.punchking.utc_now",
            "guardian_tales.punchking_static.utc_now",
        ):
            clock = patch(target, return_value=self.now)
            clock.start()
            self.addCleanup(clock.stop)
        self.catalog = {"client": CLIENT, "practice_only": True, "variants": []}
        arena = {"Seasons": [], "Monsters": []}
        raid = synthetic_catalog()
        values = records(decode(synthetic_static(raid)))[1]
        content = {name: raw for name, (_, raw, _) in values.items()}
        calendar = json.loads(content["seasondate"])
        for variant in range(1, 4):
            days = []
            for day in range(7):
                row = {
                    "id": variant * 100 + day + 1,
                    "monster_id": 700000 + variant * 10 + day,
                    "stage_id": 840010001,
                    "weak_point": ("Down", "Poison", "Aerial")[(day + variant - 1) % 3],
                    "element": "Light",
                }
                days.append(row)
                arena["Monsters"].append(
                    {
                        "Id": row["id"],
                        "MonsterId": row["monster_id"],
                        "StageId": row["stage_id"],
                        "WeakPoint": row["weak_point"],
                        "ElementalType": row["element"],
                    }
                )
            self.catalog["variants"].append(
                {
                    "id": variant,
                    "season_id": variant,
                    "calendar_id": 5300000 + variant,
                    "days": days,
                }
            )
            arena["Seasons"].append(
                {"Id": variant, "SeasonId": 5300000 + variant, "Monsters": [r["id"] for r in days]}
            )
            calendar["EventPeriod"].append(
                {
                    "Id": 5300000 + variant,
                    "From": {
                        "KakaoGlobal": "2020-01-01T00:00:00Z",
                        "KakaoKorea": "2019-01-01T00:00:00Z",
                    },
                    "To": {
                        "KakaoGlobal": "2020-01-07T23:59:59Z",
                        "KakaoKorea": "2019-01-07T23:59:59Z",
                    },
                }
            )
        content["guildpunchking"] = json.dumps(arena)
        content["seasondate"] = json.dumps(calendar)
        self.source = self.root / "static_data_get.bin"
        self.source.write_bytes(
            compress(
                "".join(
                    f"{name}\n{raw}\n1\n{digest(base64.b64decode(raw) if name.endswith('-bin') else raw.encode())}\n"
                    for name, raw in content.items()
                ).encode()
            )
        )
        self.original = self.source.read_bytes()
        (self.root / CATALOG).write_text(json.dumps(self.catalog))
        (self.root / RAID_CATALOG).write_text(json.dumps(raid))
        snapshot = synthetic_snapshot()
        snapshot["profile"]["GuildMember"] = {
            "UserId": 9400,
            "GuildId": 7,
            "JoinAt": "2000-01-01T00:00:00Z",
        }
        snapshot["profile"]["User"]["SelectedPresetId"] = {
            "InfiniteTower": 401,
            "GuildRaidAndConquest": 713,
            "GuildPunchKing": 1300,
        }
        snapshot["startup_reads"]["/preset/get-presets"]["value"]["UserPartyPreset2"] = {
            "Cas": 1,
            "Presets": [
                {"Id": ident, "Order": order, "Characters": [{"Id": 1, "Weapon1": 1}]}
                for ident, order in ((401, 0), (713, 0), (1300, 0), (1301, 1))
            ],
        }
        save = self.root / "synthetic.json"
        save.write_text(json.dumps(snapshot))
        state = self.root / "state"
        import_snapshot(save, state)
        self.db = sqlite3.connect(state / "server.sqlite3")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db, self.root)
        self.refs = self.store.references
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True
        self.session.request_epoch = "arena-tests"
        self.profile = self.store.account.profile()
        select(self.refs, 1, 1)

    def call(self, route, body=None, sequence=12):
        packet = parse_packet(
            encode_packet(
                Packet(
                    0, body=json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence
                )
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(packet))))

    def reject(self, route, body, sequence=12):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(route, body, sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_all_21_variant_day_choices_match_native_seven_day_calendar_and_boss(self):
        original = records(decode(self.original))[1]
        for variant in range(1, 4):
            for day in range(1, 8):
                with self.subTest(variant=variant, day=day):
                    selection = select(self.refs, variant, day)
                    raw = records(
                        decode(bootstrap_override(self.refs, "static_data_get.bin", None))
                    )[1]
                    for name in original.keys() - {"seasondate", "__checksum__"}:
                        self.assertEqual(raw[name], original[name])
                    dates = json.loads(raw["seasondate"][1])["EventPeriod"]
                    selected = next(r for r in dates if r["Id"] == 5300000 + variant)
                    start = datetime.fromisoformat(selected["From"]["KakaoGlobal"])
                    end = datetime.fromisoformat(selected["To"]["KakaoGlobal"])
                    self.assertEqual(
                        (self.now.replace(hour=0, minute=0, second=0, microsecond=0) - start).days,
                        day - 1,
                    )
                    self.assertEqual(end - start, timedelta(days=7, seconds=-1))
                    self.assertTrue(start <= self.now <= end)
                    for row in dates:
                        if 5300001 <= row["Id"] <= 5300003 and row is not selected:
                            self.assertLess(
                                datetime.fromisoformat(row["To"]["KakaoGlobal"]), self.now
                            )
                    boss = self.catalog["variants"][variant - 1]["days"][day - 1]["id"]
                    self.assertEqual(
                        self.call(START, {"MonsterId": boss}, variant * 100 + day), {"Messages": []}
                    )
                    reply = self.call(END, {"Damage": 42, "Abandoned": False}, variant * 1000 + day)
                    self.assertEqual(reply["GuildRaid"]["PunchKingSeasonId"], variant)
                    self.assertFalse(reply["IsRenew"])
                    self.assertEqual(load_selection(self.refs), selection)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.store.account.profile(), self.profile)

    def test_panel_lists_days_and_applies_the_cli_selection_independently_of_raid(self):
        (self.root / SELECTION).unlink()
        (self.root / RAID_CATALOG).unlink()
        panel = RaidPanel(self.refs, 0)
        panel.start()
        self.addCleanup(panel.stop)
        origin = f"http://127.0.0.1:{panel.server_port}"

        def request(method, body=None, source=origin):
            connection = HTTPConnection("127.0.0.1", panel.server_port, timeout=5)
            try:
                connection.request(
                    method,
                    "/api/dka",
                    json.dumps(body) if body else None,
                    {"Origin": source, "Content-Type": "application/json"},
                )
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        code, initial = request("GET")
        self.assertEqual(code, 200)
        self.assertEqual(initial["variants"], self.catalog["variants"])
        self.assertIsNone(initial["active"])
        self.assertFalse((self.root / SELECTION).exists())
        choice = dict(variant=3, day=7, revision=initial["revision"])
        self.assertEqual(request("POST", choice, "https://example.invalid")[0], 403)
        for invalid in (
            dict(day=0),
            dict(day=8),
            dict(variant=True),
            dict(variant=4),
            dict(revision=False),
            dict(extra=1),
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(request("POST", choice | invalid)[0], 400)
        self.assertFalse((self.root / SELECTION).exists())
        with StateLock(self.root, filename=SELECTION_LOCK):
            self.assertEqual(request("POST", choice)[0], 409)
        self.assertFalse((self.root / SELECTION).exists())
        self.assertEqual(request("POST", choice), (200, {"applied": True}))
        saved = load_selection(self.refs)
        self.assertEqual((saved["variant"], saved["day"]), (3, 7))
        self.assertEqual(request("GET")[1]["revision"], saved["static_data_revision"])
        select(self.refs, 2, 4)
        self.assertEqual(
            request("POST", choice | {"revision": saved["static_data_revision"]})[0], 409
        )
        self.assertEqual(request("GET")[1]["active"], {"variant": 2, "day": 4})
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.store.account.profile(), self.profile)

    def test_entry_and_three_empty_ranking_reads_have_native_shapes_and_no_writes(self):
        before = list(self.db.iterdump())
        self.db.execute("PRAGMA query_only=ON")
        for partial in (True, False):
            reply = self.call(ENTRY, {"IsPartial": partial})
            self.assertEqual(reply["UserRaid"], {"UserId": 9400, "PunchKingSeasonId": 1})
            self.assertEqual(reply["GuildRaid"]["GuildId"], 7)
            self.assertEqual(len(reply["GuildRaid"]["PunchKingStatus"]), 7)
            self.assertEqual(
                reply["GuildRaid"]["PunchKingStatus"][0]["UserStatus"]["9400"]["PlayCount"], 0
            )
        for route in RANKINGS:
            reply = self.call(route)
            self.assertEqual(reply["Rankings"], [])
            if route != RANKINGS[1]:
                self.assertEqual((reply["MyRank"], reply["MyScore"]), (None, 0))
        self.assertEqual(list(self.db.iterdump()), before)

    def test_authentication_exact_requests_stale_boss_and_completion_bounds_reject(self):
        self.session.signed_in = False
        self.reject(ENTRY, {"IsPartial": True})
        self.session.signed_in = True
        for body in (None, {}, {"IsPartial": 1}, {"IsPartial": True, "extra": 1}):
            self.reject(ENTRY, body)
        for body in ({"MonsterId": True}, {"MonsterId": 102}, {"MonsterId": 101, "day": 1}):
            self.reject(START, body)
        for body in (
            {"Damage": -1, "Abandoned": False},
            {"Damage": 0x80000000, "Abandoned": False},
            {"Damage": 1, "Abandoned": 0},
        ):
            self.reject(END, body)
        self.reject(END, {"Damage": 1, "Abandoned": False})
        self.reject(RANKINGS[0], {"SeasonId": 1})

    def test_completion_abandonment_retries_and_reopen_preserve_account_and_later_session(self):
        start = {"MonsterId": 101}
        end = {"Damage": 999, "Abandoned": True}
        self.call(START, start, 20)
        self.session = BootstrapSession(GuestStore(self.db, self.root))
        self.session.signed_in = True
        self.session.request_epoch = "arena-tests"
        self.assertTrue(self.call(END, end, 21)["Abandoned"])
        self.call(START, start, 22)
        before = list(self.db.iterdump())
        self.call(START, start, 20)
        self.call(END, end, 21)
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject(END, {"Damage": 1, "Abandoned": False}, 21)
        self.assertFalse(self.call(END, {"Damage": 0, "Abandoned": False}, 23)["IsRenew"])
        self.assertEqual(self.store.account.profile(), self.profile)

    def test_selection_switch_fences_active_battle_and_old_request_identity(self):
        self.call(START, {"MonsterId": 101}, 20)
        select(self.refs, 2, 3)
        self.reject(END, {"Damage": 1, "Abandoned": False}, 21)
        self.reject(START, {"MonsterId": 203}, 20)
        self.call(START, {"MonsterId": 203}, 22)
        self.call(END, {"Damage": 1, "Abandoned": False}, 23)
        self.assertEqual(self.store.account.profile(), self.profile)

    def test_saved_dka_presets_can_be_selected_without_changing_other_modes_or_inventory(self):
        reply = self.call("/preset/set-selected-preset", {"PresetId": 1301}, 40)
        expected = copy.deepcopy(self.profile)
        expected["User"]["SelectedPresetId"]["GuildPunchKing"] = 1301
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(reply["User"]["SelectedPresetId"], expected["User"]["SelectedPresetId"])
        self.reject("/preset/set-selected-preset", {"PresetId": 1399}, 41)
        self.call(START, {"MonsterId": 101}, 42)

    def test_apply_create_reorder_and_delete_dka_teams_through_native_routes(self):
        route = "/preset/set-presets"
        team = {"Id": 1301, "Order": 1, "Name": "Slime team", "Characters": [{"Id": 1}]}
        apply = {"PartyPreset": team, "SetSelected": True}
        saved = self.call(route, apply, 50)
        self.assertEqual(saved["User"]["SelectedPresetId"]["GuildPunchKing"], 1301)
        self.assertEqual(saved["UserPartyPreset2"]["Cas"], 2)
        self.assertEqual(self.call(route, apply, 50), saved)
        self.assertEqual(self.call(START, {"MonsterId": 101}, 51), {"Messages": []})
        new = dict(apply, PartyPreset=dict(team, Id=1306, Order=999))
        created = self.call(route, new, 52)
        self.assertEqual(created["UserPartyPreset2"]["Presets"][-1]["Order"], 2)
        self.assertEqual(created["User"]["SelectedPresetId"]["GuildPunchKing"], 1306)
        sorted_teams = self.call(
            "/preset/reorder-preset", {"PresetType": 13, "Order": [2, 1, 0, 0, 0, 0, 0]}, 53
        )
        self.assertEqual(
            [p["Order"] for p in sorted_teams["UserPartyPreset2"]["Presets"] if p["Id"] >= 1300],
            [2, 1, 0],
        )
        deleted = self.call("/preset/delete-preset", {"PresetId": 1306}, 54)
        self.assertEqual(
            deleted["User"]["SelectedPresetId"],
            dict(self.profile["User"]["SelectedPresetId"], GuildPunchKing=0),
        )
        self.assertEqual(self.call(route, new, 52), deleted)
        self.assertEqual(
            self.call("/preset/get-presets")["UserPartyPreset2"], deleted["UserPartyPreset2"]
        )
        self.reject(route, dict(new, PartyPreset=dict(team, Id=1307, Order=999)), 55)
        self.reject(route, dict(apply, PartyPreset=dict(team, Characters=[])), 56)
        self.reject(
            route,
            dict(apply, PartyPreset=dict(team, Characters=[{"Id": 1, "Weapon1": 987654}])),
            57,
        )

    def test_first_dka_apply_accepts_a_save_without_a_previous_dka_selection(self):
        profile = self.store.account.profile()
        del profile["User"]["SelectedPresetId"]["GuildPunchKing"]
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        team = {"Id": 1306, "Order": 999, "Name": "New team", "Characters": [{"Id": 1}]}
        result = self.call("/preset/set-presets", {"PartyPreset": team, "SetSelected": True})
        self.assertEqual(
            result["User"]["SelectedPresetId"],
            dict(profile["User"]["SelectedPresetId"], GuildPunchKing=1306),
        )

    def test_daily_bootstrap_refresh_keeps_chosen_day_and_updates_checksum(self):
        selection = select(self.refs, 3, 7)
        tomorrow = self.now + timedelta(days=1)
        with (
            patch("guardian_tales.punchking_static.utc_now", return_value=tomorrow),
            patch("guardian_tales.punchking.utc_now", return_value=tomorrow),
        ):
            self.reject(ENTRY, {"IsPartial": True})
            reply = self.call(
                "/static-data/check-update", {"Checksum": selection["static_data_checksum"]}
            )
            self.assertFalse(reply["UpToDate"])
            refreshed = load_selection(self.refs)
            self.assertEqual((refreshed["variant"], refreshed["day"]), (3, 7))
            self.assertEqual(refreshed["content_date"], tomorrow.date().isoformat())
            self.assertEqual(
                self.call(ENTRY, {"IsPartial": True})["GuildRaid"]["PunchKingSeasonId"], 3
            )
        self.assertEqual(self.store.account.profile(), self.profile)

    def test_raid_selection_changes_are_composed_in_both_orders_without_overwriting_arena(self):
        select_season(self.refs, 1)
        select(self.refs, 2, 4)
        for raid_id in (1, 2):
            select_season(self.refs, raid_id)
            reply = self.call("/static-data/check-update", {"Checksum": "old"})
            self.assertFalse(reply["UpToDate"])
            prepared = records(decode(bootstrap_override(self.refs, "static_data_get.bin", None)))[
                1
            ]
            dates = json.loads(prepared["seasondate"][1])["EventPeriod"]
            self.assertEqual(
                next(r for r in dates if r["Id"] == 5400000 + raid_id)["From"]["KakaoGlobal"],
                "2000-01-01T00:00:00+00:00",
            )
            self.assertEqual(
                self.call(ENTRY, {"IsPartial": True})["GuildRaid"]["PunchKingSeasonId"], 2
            )
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_missing_corrupt_body_and_bad_catalog_do_not_change_account_or_selection(self):
        saved = load_selection(self.refs)
        body = self.root / f"guild_punchking_static_{saved['static_data_sha256']}.bin"
        body.write_bytes(b"broken")
        self.reject("/static-data/get", {})
        before = (self.root / "guild_punchking_selection.json").read_bytes()
        broken = copy.deepcopy(self.catalog)
        broken["variants"][0]["days"][0]["stage_id"] = 99
        (self.root / CATALOG).write_text(json.dumps(broken))
        with self.assertRaises(ValueError):
            select(self.refs, 1, 1)
        self.assertEqual((self.root / "guild_punchking_selection.json").read_bytes(), before)
        self.assertEqual(self.store.account.profile(), self.profile)

    def test_stage_receipt_failure_rolls_back_active_session(self):
        self.call(START, {"MonsterId": 101}, 20)
        self.db.execute(
            "CREATE TRIGGER fail_arena BEFORE INSERT ON punchking_requests BEGIN SELECT RAISE(ABORT,'synthetic'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(END, {"Damage": 1, "Abandoned": False}, 21)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_existing_uncaptured_arena_progress_and_missing_owned_team_are_guarded(self):
        for mutation in (
            lambda p: p.update(UserRaid={"PunchKingSeasonId": 1}),
            lambda p: p.update(GuildMember=None),
            lambda p: p["User"]["SelectedPresetId"].update(GuildPunchKing=0),
        ):
            p = copy.deepcopy(self.profile)
            mutation(p)
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
            self.reject(START, {"MonsterId": 101})

    def test_cli_lists_variants_selects_day_and_rejects_out_of_range_values(self):
        with redirect_stdout(io.StringIO()) as output:
            main(["list", "--reference-dir", str(self.root)])
        self.assertEqual(len(json.loads(output.getvalue())["variants"]), 3)
        with redirect_stdout(io.StringIO()) as output:
            main(["set", "3", "--day", "6", "--reference-dir", str(self.root)])
        self.assertEqual(json.loads(output.getvalue())["day"], 6)
        for variant, day in ((0, 1), (4, 1), (1, 0), (1, 8), (True, 1)):
            with self.assertRaises(ValueError):
                select(self.refs, variant, day)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["set", "4", "--reference-dir", str(self.root)])
