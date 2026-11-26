# SPDX-License-Identifier: Apache-2.0
"""Permanent rotations use their own data and runs in the existing Events client."""

import copy
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from guardian_tales import kamazone
from guardian_tales.web_panel.kamazone import adapter
from tests.content import test_kamazone_run as fixtures
from tests.content.test_kamazone import NOW


class OldKamazoneTests(unittest.TestCase):
    def setUp(self):
        self.run = fixtures.KamazoneRunTests()
        self.addCleanup(self.run.doCleanups)
        self.run.setUp()
        self.fixture = self.run.fixture
        self.refs = self.fixture.refs
        self.tables = self.fixture.tables
        event = self.tables["kamazonland2"]
        for key in ("Trials", "SpecialEvents", "SpecialEventChoices", "RandomConclusions"):
            event.setdefault(key, [])
        event["Constants"] = {"RoundPeriod": 14, "ShelterHpRecover": 0.4}
        archive = copy.deepcopy(event)
        self.tables["kamazonland"] = archive
        archive["Seasons"] = [
            {
                "Id": ident,
                "SeasonDateId": calendar,
                "MiniSeasonGroupId": 6,
                "Benefits": [1],
                "Floors": [1],
                "Artifacts": [900],
                "SpecialEvents": events,
                "MaxDifficulty": 4,
                "GachaId": 0,
            }
            for ident, calendar, events in (
                (1, 7000008, [509]),
                (2, 7000009, [605]),
                (2001, 7100001, []),
            )
        ]
        archive["MiniSeasonsNew"] = [
            {"Id": i, "MiniSeasonGroupId": 6, "KamazonPointLimit": 2000, "BanElementalTypes": []}
            for i in (602, 601)
        ]
        archive["Benefits"] = [dict(archive["Benefits"][0], OpenValue=605)]
        archive["SpecialEvents"] = [{"Id": 509}, {"Id": 605}]
        archive["Constants"] = {"RoundPeriod": 7, "ShelterHpRecover": 0.3}
        archive["Difficulty"] = [
            dict(
                Id=i * 100 + 1,
                Floor=1,
                Difficulty=i,
                NormalLevel=10 * i,
                EliteLevel=10 * i + 1,
                BossLevel=10 * i + 2,
                BottleCapReward=99,
            )
            for i in range(1, 5)
        ]
        periods = self.tables["seasondate"]["EventPeriod"]
        foreign_period = next(p for p in periods if p["Id"] == 7100033)
        for row in archive["Seasons"]:
            model = foreign_period if row["Id"] == 2001 else periods[0]
            periods.append(dict(copy.deepcopy(model), Id=row["SeasonDateId"]))
        self.fixture.write_source()
        kamazone.change_season(self.refs, 43)

    def test_preserved_global_rotations_and_text_previews_work_without_art_bundles(self):
        before = {p.name: p.read_bytes() for p in self.refs.directory.iterdir()}
        view = adapter.state(self.refs)
        self.assertEqual([s["id"] for s in view["seasons"]], [41, 42, 43])
        for season in view["seasons"]:
            self.assertTrue(season["theme"])
            self.assertFalse(season.get("image"))
        self.assertEqual(
            [(s["id"], s["name"]) for s in view["oldSeasons"]],
            [(1, "Season 1 · Reopening"), (2, "Season 2 · Cooking")],
        )
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.refs.directory.iterdir()})

    def test_web_switch_and_restore_preserve_event_dates_and_three_distinct_runs(self):
        modern = self.run.challenge(3)
        event = adapter.state(self.refs)

        def switch(action, **kwargs):
            state = adapter.state(self.refs)
            adapter.apply(self.refs, dict(action=action, revision=state["revision"], **kwargs))
            return adapter.state(self.refs)

        with patch("guardian_tales.kamazone.utc_now", return_value=NOW + timedelta(days=2)):
            old = switch("select-old", seasonId=1)
            self.assertEqual((old["seasonId"], self.run.entry()["SeasonId"]), (1, 1))
            self.assertNotEqual(event["period"], old["period"])
            with self.assertRaises(kamazone.SeasonSelectionChanged):
                adapter.apply(self.refs, dict(action="leave-old", revision=event["revision"]))
            self.assertEqual(self.run.entry()["Progress"]["Floor"], 0)
            first = self.run.challenge(4)
            self.assertEqual((first["MiniSeasonId"], first["Difficulty"]), (601, 4))
            switch("select-old", seasonId=2)
            self.assertEqual(self.run.entry()["Progress"]["Floor"], 0)
            second = self.run.challenge(2)
            switch("select-old", seasonId=1)
            self.assertEqual(self.run.entry(), first)
            restored = switch("leave-old")
            self.assertEqual((restored["seasonId"], restored["period"]), (43, event["period"]))
            self.assertEqual(self.run.entry(), modern)
            switch("select-old", seasonId=2)
            self.assertEqual(self.run.entry(), second)

    def test_client_projection_changes_the_legacy_gameplay_rows_and_reverts_them(self):
        source = self.fixture.source
        before = self.fixture.decoded()
        kamazone.change_season(self.refs, 1, old=True)
        active = self.fixture.decoded()
        projected = json.loads(active["kamazonland2"][1])
        old = next(row for row in projected["Seasons"] if row["Id"] == 1)
        self.assertEqual(
            (old["SeasonDateId"], old["MaxDifficulty"], old["SpecialEvents"]), (7000008, 4, [509])
        )
        self.assertEqual(projected["Difficulty"][-1]["BossLevel"], 42)
        self.assertEqual(projected["Constants"], {"RoundPeriod": 14, "ShelterHpRecover": 0.3})
        self.assertEqual(
            next(r for r in projected["Benefits"] if r["Id"] == 1)["OpenValues"], [605]
        )
        self.assertEqual(active["kamazonland"], before["kamazonland"])
        kamazone.change_season(self.refs, None, leave_old=True)
        after = self.fixture.decoded()
        self.assertEqual(after["kamazonland2"][1], before["kamazonland2"][1])
        self.assertLess(before["kamazonland2"][2], active["kamazonland2"][2])
        self.assertLess(active["kamazonland2"][2], after["kamazonland2"][2])
        self.assertEqual(self.refs.read_bytes("static_data_get.bin"), source)

    def test_reject_wrong_catalog_and_restore_inactive_calendar(self):
        generation = kamazone.load(self.refs)["generation"]
        for ident, old in ((2001, True), (41, True), (1, False), (True, True)):
            with self.subTest(ident=ident, old=old), self.assertRaises(ValueError):
                kamazone.change_season(self.refs, ident, old=old)
        self.assertEqual(kamazone.load(self.refs)["generation"], generation)
        kamazone.change_season(self.refs, None)
        kamazone.change_season(self.refs, 2, old=True)
        restored = kamazone.change_season(self.refs, None, leave_old=True)
        self.assertIsNone(restored["selected_season_id"])
        self.assertEqual(
            json.loads(self.fixture.decoded()["seasondate"][1]), self.tables["seasondate"]
        )
