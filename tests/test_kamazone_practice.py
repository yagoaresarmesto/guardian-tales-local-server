# SPDX-License-Identifier: Apache-2.0
"""Seasonal benefit defaults, legacy choices, original costs and budget validation."""

import copy
import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from unittest.mock import patch

from guardian_tales.__main__ import main
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.kamazone_practice import CONFIG, SAVE, allocation_file
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

    @property
    def allocation(self):
        return self.root / allocation_file(self.fixture.source, 43)

    def write_legacy(self, **overrides):
        value = dict(
            version=1,
            generation=7,
            enabled=True,
            source_sha256=hashlib.sha256(self.fixture.source).hexdigest(),
            season_id=43,
            points=500,
            unlock_benefits=[174],
            benefits={"174": 1},
            seen_operations=["synthetic-kamazone-practice:701"],
        )
        (self.root / CONFIG).write_text(json.dumps(dict(value, **overrides)))

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
        return {p.name: p.read_bytes() for p in self.root.iterdir() if p != self.allocation}

    def test_all_seasonal_unlocks_are_automatic_and_preserve_prices_and_unrelated_tables(self):
        before, files = list(self.db.iterdump()), self.files()
        original = records(decode(self.fixture.source))[1]
        current = records(decode(self.static()))[1]
        expected = copy.deepcopy(self.fixture.tables["kamazonland2"])
        for row in expected["Benefits"]:
            if row["Id"] in (174, 42):
                row.update(OpenType="None", OpenValue=0, OpenValues=None)
        self.assertEqual(json.loads(current["kamazonland2"][1]), expected)
        for name in original.keys() - {"kamazonland2", "seasondate", "__checksum__"}:
            self.assertEqual(current[name], original[name])
        checksum = current["__checksum__"][1]
        check = json.loads(
            self.session.handle(request("/static-data/check-update", {"Checksum": checksum})).body
        )
        self.assertTrue(check["UpToDate"])
        self.assertEqual((list(self.db.iterdump()), self.files()), (before, files))
        self.assertFalse(self.allocation.exists())

    def test_legacy_command_is_optional_and_cannot_override_defaults(self):
        before = self.files()
        with patch("sqlite3.connect", side_effect=AssertionError("CLI must not open databases")):
            status = self.practice("status")
            self.assertEqual(
                self.practice("enable", "--unlock-benefit", "174", "--points", "4000"), status
            )
        self.assertEqual(status["points"], 4000)
        self.assertEqual(set(status["unlocked_benefits"]), {1, 42, 174})
        self.assertFalse(status["changed"])
        self.reject("enable", "--points", "500")
        self.reject("disable")
        self.assertEqual(self.files(), before)
        self.assertFalse(self.allocation.exists())

    def test_points_and_saved_benefits_survive_new_session_without_account_writes(self):
        before, files, changes = list(self.db.iterdump()), self.files(), self.db.total_changes
        response = self.save({"174": 1, "1": 2, "42": 0})
        self.assertEqual(set(response), {"UserKamazonLand", "NewSeason"})
        self.assertFalse(response["NewSeason"])
        user = response["UserKamazonLand"]
        self.assertEqual((user["KamazonPoint"], user["KamazonPointTotal"]), (3000, 4000))
        self.assertEqual(
            user["Benefits"],
            [{"Id": 1, "Level": 2}, {"Id": 174, "Level": 1}],
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

    def test_clearing_and_replay_return_an_exact_empty_selection_and_refund_the_budget(self):
        self.save({"174": 1}, 701)
        cleared = self.save({}, 702)
        self.assertEqual(cleared["UserKamazonLand"]["Benefits"], [])
        previous = self.allocation.read_bytes()
        self.assertEqual(self.save({"174": 1}, 701), cleared)
        self.assertEqual(self.allocation.read_bytes(), previous)
        self.assertEqual(cleared["UserKamazonLand"]["KamazonPoint"], 4000)

    def test_empty_entry_does_not_fill_the_native_eight_selected_benefit_slots(self):
        user = self.entry()["UserKamazonLand"]
        self.assertEqual(user["Benefits"], [])
        self.assertEqual((user["KamazonPoint"], user["KamazonPointTotal"]), (4000, 4000))
        self.save({"174": 1})
        user = self.entry()["UserKamazonLand"]
        # Native Membership.Load inserts every row into TempBenefitLevelDict;
        # OnPlusButtonClick limits that dictionary's count, including zero rows.
        selected = {r["Id"]: r["Level"] for r in user["Benefits"]}
        self.assertEqual(selected, {174: 1})
        self.assertLess(len(selected), 8)

    def test_original_incremental_upgrade_costs_and_point_budget_are_enforced(self):
        mode = self.fixture.tables["kamazonland2"]
        mode["Benefits"][0]["Points"] = [250, 500, 3300]
        self.fixture.write_source()
        self.command("select", "--season-id", "43")
        self.save({"1": 2}, 711)
        config = self.allocation.read_bytes()
        with self.assertRaises(PacketError):
            self.save({"1": 3}, 712)
        self.assertEqual(self.allocation.read_bytes(), config)
        self.assertEqual(self.save({}, 713)["UserKamazonLand"]["KamazonPoint"], 4000)
        mode["Benefits"][0]["Points"][2] = 750
        self.fixture.write_source()
        self.command("select", "--season-id", "43")
        for sequence, level, available in ((720, 1, 3750), (721, 2, 3250), (722, 3, 2500)):
            user = self.save({"1": level}, sequence)["UserKamazonLand"]
            self.assertEqual((user["KamazonPoint"], user["KamazonPointTotal"]), (available, 4000))

    def test_eight_benefit_limit_allows_upgrading_selected_rows_but_rejects_a_ninth(self):
        mode = self.fixture.tables["kamazonland2"]
        mode["Benefits"] = [
            dict(Id=i, Name=str(i), OpenType="None", MaxLevel=2, Points=[10, 20])
            for i in range(1, 10)
        ]
        next(r for r in mode["Seasons"] if r["Id"] == 43)["Benefits"] = list(range(1, 10))
        self.fixture.write_source()
        self.command("select", "--season-id", "43")
        selected = {str(i): 1 for i in range(1, 9)}
        self.assertEqual(len(self.save(selected, 730)["UserKamazonLand"]["Benefits"]), 8)
        selected["1"] = 2
        self.save(selected, 731)
        config = self.allocation.read_bytes()
        with self.assertRaises(PacketError):
            self.save(dict(selected, **{"9": 1}), 732)
        self.assertEqual(self.allocation.read_bytes(), config)

    def test_saving_choices_does_not_change_static_revisions_or_price_overlay(self):
        before = self.static()
        self.save({"174": 1})
        self.assertEqual(self.static(), before)
        self.assertFalse(self.practice("status")["changed"])

    def test_prior_choices_and_retries_migrate_lazily_and_remain_separate_per_season(self):
        self.write_legacy()
        original = (self.root / CONFIG).read_bytes()
        initial = self.entry()["UserKamazonLand"]
        self.assertEqual((initial["KamazonPoint"], initial["KamazonPointTotal"]), (3750, 4000))
        self.assertEqual(initial["Benefits"], [{"Id": 174, "Level": 1}])
        self.assertEqual(self.save({}, 701)["UserKamazonLand"], initial)
        self.assertFalse(self.allocation.exists())
        self.assertEqual(self.save({"42": 1}, 702)["UserKamazonLand"]["KamazonPoint"], 3500)
        for season, level in ((41, 1), (42, 2)):
            self.command("select", "--season-id", str(season))
            self.assertEqual(self.entry()["UserKamazonLand"]["KamazonPoint"], 4000)
            with self.assertRaises(PacketError):
                self.save({"174": 1})
            self.save({"1": level}, 702)
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        for season, available in ((41, 3750), (43, 3500), (42, 3250)):
            self.command("select", "--season-id", str(season))
            self.assertEqual(self.entry()["UserKamazonLand"]["KamazonPoint"], available)
        self.assertEqual((self.root / CONFIG).read_bytes(), original)

    def test_switch_revises_cached_unlocks_and_disable_restores_parent_content(self):
        self.write_legacy(enabled=False)
        selected = json.loads((self.root / "kamazone_selection.json").read_bytes())
        raw = records(decode(self.fixture.source))[1]
        calendar_revision = (
            max(raw["seasondate"][2], raw["__checksum__"][2]) + selected["generation"] + 1
        )
        legacy_revision = max(raw["kamazonland2"][2], calendar_revision) + 7 + 2
        revisions = []
        for action, ident in (("select", 43), ("select", 41), ("disable", None)):
            self.command(action, *(("--season-id", str(ident)) if ident else ()))
            tables = records(decode(self.static()))[1]
            revisions.append(tables["kamazonland2"][2])
            rows = json.loads(tables["kamazonland2"][1])["Benefits"]
            self.assertEqual(rows[1]["OpenType"], "None" if ident == 43 else "SpecialEventChoice")
        self.assertGreater(revisions[0], legacy_revision)
        self.assertEqual(sorted(set(revisions)), revisions)
        self.assertEqual(
            tables["kamazonland2"][1], records(decode(self.fixture.source))[1]["kamazonland2"][1]
        )

    def test_invalid_save_shapes_foreign_benefits_and_levels_never_publish(self):
        self.save({"42": 1}, 705)
        before, config = list(self.db.iterdump()), self.allocation.read_bytes()
        for levels in (
            [],
            None,
            {"174": True},
            {"174": -1},
            {"174": 2},
            {"1": 4},
            {"999": 0},
            {"0174": 1},
            {"١٧٤": 1},
            {"x": 1},
        ):
            with self.assertRaises(PacketError):
                self.save(levels)
        self.assertEqual((list(self.db.iterdump()), self.allocation.read_bytes()), (before, config))

    def test_authentication_prologue_expiry_and_changed_content_guard_saves(self):
        self.save({}, 705)
        original = self.allocation
        config = original.read_bytes()
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
        with self.assertRaises(PacketError):
            self.save({"174": 1})
        self.command("select", "--season-id", "43")
        self.assertFalse(self.allocation.exists())
        self.assertEqual(original.read_bytes(), config)
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        with self.assertRaises(PacketError):
            self.save({"174": 1})

    def test_atomic_save_failure_leaves_the_previous_selection_and_account_intact(self):
        self.save({"42": 1}, 705)
        before, config = list(self.db.iterdump()), self.allocation.read_bytes()
        with patch(
            "guardian_tales.punchking_static.atomic_replace",
            side_effect=OSError("synthetic failure"),
        ):
            with self.assertRaises(PacketError):
                self.save({"174": 1})
        self.assertEqual((list(self.db.iterdump()), self.allocation.read_bytes()), (before, config))
        self.assertFalse(list(self.root.glob(".dka-*")))
        self.save({"174": 1})

    def test_malformed_allocations_fail_closed_without_account_writes(self):
        self.save({"174": 1}, 705)
        path = self.allocation
        original = json.loads(path.read_text())
        before = list(self.db.iterdump())
        for change in (
            {"points": True},
            {"benefits": []},
            {"benefits": {"42": 0}},
            {"benefits": {"174": 2}},
            {"seen_operations": ["x", "x"]},
            {"seen_operations": "invalid"},
        ):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(PacketError):
                self.entry()
        self.assertEqual(list(self.db.iterdump()), before)
