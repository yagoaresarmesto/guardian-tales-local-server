# SPDX-License-Identifier: Apache-2.0
"""Opt-in benefits persist separately, keep points fixed and preserve game files."""

import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from unittest.mock import patch

from guardian_tales.__main__ import main
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.kamazone_practice import CONFIG, SAVE
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import decode, records
from tests import test_kamazone as fixtures
from tests.test_snapshots import request


class KamazonePracticeTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazonePreviewTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.fixture = self.owner.fixture
        self.db, self.session, self.root = self.owner.db, self.owner.session, self.fixture.root
        self.session.request_epoch = "synthetic-kamazone-practice"
        mode = self.fixture.tables["kamazonland2"]
        mode["Benefits"] = [
            dict(
                Id=1,
                Name="brawler",
                OpenType="None",
                OpenValue=0,
                OpenValues=None,
                MaxLevel=3,
                Points=[250, 500, 750],
                OptionId=100,
                OptionLevel1=500,
            ),
            dict(
                Id=174,
                Name="mall_buff_strong_body",
                OpenType="SpecialEventChoice",
                OpenValue=140801,
                OpenValues=[140801, 141201],
                MaxLevel=1,
                Points=[250],
                OptionId=999,
                OptionLevel1=2000,
            ),
            dict(
                Id=42,
                Name="locked",
                OpenType="SpecialEvent",
                OpenValue=10,
                OpenValues=[10],
                MaxLevel=1,
                Points=[500],
            ),
            dict(Id=999, Name="unrelated", Points=[750]),
        ]
        for season in mode["Seasons"]:
            season["Benefits"] = [1, 174, 42] if season["Id"] == 43 else [1]
        mode["MiniSeasons"][0]["KamazonPointLimit"] = 4000
        self.fixture.write_source()
        self.command("select", "--season-id", "43")

    def command(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            main(["kamazone", *args, "--reference-dir", str(self.root)])
        return json.loads(out.getvalue())

    def practice(self, *args):
        return self.command("practice", *args)

    def enable(self):
        return self.practice("enable", "--unlock-benefit", "174", "--points", "4000")

    def reject(self, *args):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.practice(*args)
        self.assertEqual(error.exception.code, 2)

    def entry(self):
        return json.loads(
            self.session.handle(request("/kamazonland/enter", {"IsPartial": False})).body
        )

    def static(self):
        return self.session.handle(request("/static-data/get", {})).body

    def save(self, levels, sequence=700):
        packet = request(SAVE, {"Benefits": levels})
        packet["sequence_id"] = sequence
        reply = self.session.handle(packet)
        self.assertEqual((reply.packet_type, reply.body_type, reply.sequence_id), (1, 1, sequence))
        return json.loads(reply.body)

    def files(self):
        return {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != CONFIG}

    def test_unconfigured_and_disabled_commands_keep_original_responses_and_create_no_file(self):
        before, files = list(self.db.iterdump()), self.files()
        static, entry = self.static(), self.entry()
        self.assertIsNone(self.practice("status")["configuration"])
        self.assertFalse(self.practice("disable")["changed"])
        self.assertFalse((self.root / CONFIG).exists())
        self.assertEqual((self.static(), self.entry()), (static, entry))
        self.assertEqual((list(self.db.iterdump()), self.files()), (before, files))

    def test_enable_opens_only_requested_benefit_and_zeroes_only_seasonal_prices_in_responses(self):
        before, files = list(self.db.iterdump()), self.files()
        original = records(decode(self.static()))[1]
        with patch("sqlite3.connect", side_effect=AssertionError("CLI must not open databases")):
            self.enable()
        current = records(decode(self.static()))[1]
        expected = copy.deepcopy(self.fixture.tables["kamazonland2"])
        for row in expected["Benefits"]:
            if row["Id"] in (1, 42, 174):
                row["Points"] = [0] * row["MaxLevel"]
            if row["Id"] == 174:
                row.update(OpenType="None", OpenValue=0, OpenValues=None)
        self.assertEqual(json.loads(current["kamazonland2"][1]), expected)
        for name in original.keys() - {"kamazonland2", "__checksum__"}:
            self.assertEqual(current[name], original[name], name)
        checksum = current["__checksum__"][1]
        check = json.loads(
            self.session.handle(request("/static-data/check-update", {"Checksum": checksum})).body
        )
        self.assertTrue(check["UpToDate"])
        self.assertEqual(check["Checksum"], checksum)
        self.assertEqual((list(self.db.iterdump()), self.files()), (before, files))

    def test_points_and_saved_benefits_survive_new_session_without_account_writes(self):
        self.enable()
        before, files, changes = list(self.db.iterdump()), self.files(), self.db.total_changes
        response = self.save({"174": 1, "1": 2, "42": 0})
        self.assertEqual(set(response), {"UserKamazonLand"})
        user = response["UserKamazonLand"]
        self.assertEqual((user["KamazonPoint"], user["KamazonPointTotal"]), (4000, 4000))
        self.assertEqual(
            user["Benefits"],
            [{"Id": 1, "Level": 2}, {"Id": 174, "Level": 1}, {"Id": 42, "Level": 0}],
        )
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        for _ in range(2):
            view = self.entry()["UserKamazonLand"]
            for key, value in user.items():
                self.assertEqual(view[key], value)
            self.assertEqual(view["Progress"]["Floor"], 0)
            self.assertEqual(view["KamazonTicket"], 0)
        self.assertEqual(
            (list(self.db.iterdump()), self.files(), self.db.total_changes),
            (before, files, changes),
        )

    def test_clearing_and_replay_send_zero_levels_and_never_restore_an_old_selection(self):
        self.enable()
        self.save({"174": 1}, 701)
        cleared = self.save({}, 702)
        self.assertTrue(all(r["Level"] == 0 for r in cleared["UserKamazonLand"]["Benefits"]))
        previous = (self.root / CONFIG).read_bytes()
        self.assertEqual(self.save({"174": 1}, 701), cleared)
        self.assertEqual((self.root / CONFIG).read_bytes(), previous)
        self.assertEqual(cleared["UserKamazonLand"]["KamazonPoint"], 4000)

    def test_saving_choices_does_not_change_static_revisions_or_price_overlay(self):
        self.enable()
        before = self.static()
        self.save({"174": 1})
        self.assertEqual(self.static(), before)
        self.assertFalse(self.enable()["changed"])

    def test_disable_restores_exact_parent_mode_with_new_revision_and_can_reenable_choices(self):
        original = records(decode(self.static()))[1]["kamazonland2"]
        self.enable()
        self.save({"174": 1})
        active = records(decode(self.static()))[1]["kamazonland2"]
        self.practice("disable")
        disabled = records(decode(self.static()))[1]["kamazonland2"]
        self.assertEqual(disabled[1], original[1])
        self.assertGreater(disabled[2], active[2])
        self.assertEqual(self.entry()["UserKamazonLand"]["KamazonPoint"], 0)
        with self.assertRaises(PacketError):
            self.save({"174": 1})
        self.enable()
        self.assertIn({"Id": 174, "Level": 1}, self.entry()["UserKamazonLand"]["Benefits"])

    def test_practice_is_inactive_when_another_season_is_selected(self):
        self.enable()
        self.command("select", "--season-id", "41")
        self.assertEqual(self.entry()["UserKamazonLand"]["KamazonPoint"], 0)
        self.assertEqual(
            json.loads(records(decode(self.static()))[1]["kamazonland2"][1]),
            self.fixture.tables["kamazonland2"],
        )
        with self.assertRaises(PacketError):
            self.save({"174": 1})
        self.command("select", "--season-id", "43")
        self.assertEqual(self.entry()["UserKamazonLand"]["KamazonPoint"], 4000)

    def test_invalid_cli_points_unlocks_and_stale_selection_never_publish(self):
        before = self.files()
        for args in (
            ("enable", "--points", "4001"),
            ("enable", "--points", "0"),
            ("enable", "--unlock-benefit", "999"),
            ("status", "--points", "1"),
        ):
            self.reject(*args)
        self.assertFalse((self.root / CONFIG).exists())
        self.assertEqual(self.files(), before)
        self.command("select", "--season-id", "41")
        self.reject("enable", "--unlock-benefit", "174")
        self.fixture.tables["untouched"]["value"].append(4)
        self.fixture.write_source()
        self.reject("enable")
        self.assertFalse((self.root / CONFIG).exists())

    def test_invalid_save_shapes_locked_benefits_and_levels_never_publish(self):
        with self.assertRaises(PacketError):
            self.save({"174": 1})
        self.enable()
        before, config = list(self.db.iterdump()), (self.root / CONFIG).read_bytes()
        for levels in (
            [],
            None,
            {"174": True},
            {"174": -1},
            {"174": 2},
            {"1": 4},
            {"42": 1},
            {"999": 0},
            {"0174": 1},
            {"١٧٤": 1},
            {"x": 1},
        ):
            with self.assertRaises(PacketError):
                self.save(levels)
        self.assertEqual(
            (list(self.db.iterdump()), (self.root / CONFIG).read_bytes()), (before, config)
        )

    def test_authentication_prologue_expiry_and_changed_content_guard_saves(self):
        self.enable()
        config = (self.root / CONFIG).read_bytes()
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.save({"174": 1})
        self.session.signed_in = True
        with patch(
            "guardian_tales.kamazone.utc_now", return_value=fixtures.NOW + timedelta(days=22)
        ):
            with self.assertRaises(PacketError):
                self.save({"174": 1})
        self.fixture.tables["untouched"]["value"].append(4)
        self.fixture.write_source()
        self.command("select", "--season-id", "43")
        with self.assertRaises(PacketError):
            self.save({"174": 1})
        self.assertEqual((self.root / CONFIG).read_bytes(), config)
        self.practice("disable")
        self.static()
        self.enable()
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        with self.assertRaises(PacketError):
            self.save({"174": 1})

    def test_atomic_save_failure_leaves_the_previous_selection_and_account_intact(self):
        self.enable()
        before, config = list(self.db.iterdump()), (self.root / CONFIG).read_bytes()
        with patch(
            "guardian_tales.punchking_static.atomic_replace",
            side_effect=OSError("synthetic failure"),
        ):
            with self.assertRaises(PacketError):
                self.save({"174": 1})
        self.assertEqual(
            (list(self.db.iterdump()), (self.root / CONFIG).read_bytes()), (before, config)
        )
        self.assertFalse(list(self.root.glob(".dka-*")))
        self.save({"174": 1})

    def test_malformed_practice_files_fail_closed_without_account_writes(self):
        self.enable()
        path = self.root / CONFIG
        original = json.loads(path.read_text())
        before = list(self.db.iterdump())
        for change in (
            {"points": True},
            {"generation": 0},
            {"points": 4001},
            {"unlock_benefits": [174, 174]},
            {"benefits": {"174": 2}},
            {"seen_operations": ["x", "x"]},
            {"source_sha256": "0" * 64},
        ):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(PacketError):
                self.entry()
        self.assertEqual(list(self.db.iterdump()), before)
