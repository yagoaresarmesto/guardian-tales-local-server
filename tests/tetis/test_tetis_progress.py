# SPDX-License-Identifier: Apache-2.0
"""Native Tetis level thresholds, repeat floors and persisted editor allocations."""

import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from guardian_tales.modes.tetis.tetis_catalog import TetisCatalog
from guardian_tales.modes.tetis.tetis_progress import (
    edit_progress,
    editor_view,
    read_progress,
    save_progress,
)
from guardian_tales.modes.tetis.tetis_sweep import counter, exchange, sweep


def catalog_data():
    return {
        "Seasons": [
            {"Id": 1, "SeasonLastStage": 2, "TitleName": "s1", "SeasonCoin": 771},
            {
                "Id": 2,
                "SeasonLastStage": 10,
                "TitleName": "s2",
                "SeasonCoin": 772,
                "Current": True,
                "SummonerSpellsUI": [1, 3],
            },
        ],
        "Floors": [
            dict(SeasonId=s, Floor=f, Id=s * 10000 + f, StageId=s * 100 + f)
            for s, n in [(1, 2), (2, 4)]
            for f in range(1, n + 1)
        ],
        "Constants": {
            "MaxFloor": 2,
            "LevelPerPoint": 1,
            "MaxAbilityPoint": 5,
            "ArtifactLevels": [1, 11, 21],
            "ArtifactDropWeight": [[1, 0], [0, 1]],
        },
        "RogueChessLevel": [{"Level": i, "TotalExp": i * 10} for i in range(1, 7)],
        "AbilityCategories": [
            {
                "Id": 4,
                "SeasonId": 2,
                "AbilityCategoryTitle": "common",
                "UnlockConditions": [],
                "StepMinimumPoints": [0, 2],
            },
            {
                "Id": 5,
                "SeasonId": 2,
                "AbilityCategoryTitle": "melee",
                "UnlockConditions": [{"Id": 4, "Amount": 3}],
                "StepMinimumPoints": [0],
            },
        ],
        "AbilitySpecs": [{"Id": 1, "Name": "ability"}],
        "SummonerSpells": [{"Id": 1, "Name": "starter"}, {"Id": 3, "Name": "spell"}],
        "SeasonArtifacts": [
            {"Id": 7, "SeasonId": 1, "Name": "past"},
            {"Id": 8, "SeasonId": 2, "Name": "current", "GradeUpLevel": [1, 15]},
        ],
        "AbilityNodes": [
            dict(
                AbilityCategoryId=4,
                NodeId=101,
                Step=1,
                AbilityId=1,
                MaxPoints=2,
                SummonerSpellId=0,
                NextNodeIds=[201],
            ),
            dict(
                AbilityCategoryId=4, NodeId=201, Step=2, AbilityId=1, MaxPoints=1, SummonerSpellId=0
            ),
            dict(
                AbilityCategoryId=5, NodeId=101, Step=1, AbilityId=0, MaxPoints=1, SummonerSpellId=3
            ),
        ],
    }


class TetisProgressTests(unittest.TestCase):
    def setUp(self):
        self.catalog = TetisCatalog(catalog_data())
        self.db = self.enterContext(closing(sqlite3.connect(":memory:")))

    def test_caps_floor_rotation_and_xp_boundaries(self):
        tree = self.catalog
        self.assertEqual([tree.level_for(v) for v in (0, 9, 10, 60)], [1, 1, 2, 6])
        self.assertEqual(tree.point_budget(60), 5)
        self.assertEqual([tree.floor_spec(2, n)["Floor"] for n in (1, 4, 5, 10)], [1, 4, 3, 4])
        for season, floor in [(1, 3), (2, 11), (2, False)]:
            with self.assertRaises(ValueError):
                tree.floor_spec(season, floor)

    def test_native_node_packing_and_skill_requirements(self):
        skills = self.catalog.validate_abilities
        self.assertEqual(
            skills(2, 40, {"40101": 2, "40201": 1, "50101": 1}), [4010102, 4020101, 5010101]
        )
        for exp, values in [
            (0, {"40101": 2}),
            (60, {"40101": 3}),
            (60, {"40201": 1}),
            (60, {"40101": 2, "50101": 1}),
            (60, {"40101": True}),
        ]:
            with self.subTest(exp=exp, values=values), self.assertRaises(ValueError):
                skills(2, exp, values)

    def test_editor_shares_game_state_and_preserves_other_seasons_on_failure(self):
        db, cat = self.db, self.catalog
        self.assertEqual(editor_view(db, cat)["seasons"][1]["clearedFloor"], 0)
        self.assertFalse(db.execute("SELECT name FROM sqlite_master").fetchall())
        with db:
            edit_progress(
                db,
                cat,
                {"seasonId": 2, "clearedFloor": 6, "experience": 40, "abilities": {"40101": 2}},
            )
            edit_progress(db, cat, {"seasonId": 1, "clearedFloor": 1})
        before = read_progress(db, cat)
        with self.assertRaises(ValueError), db:
            edit_progress(db, cat, {"seasonId": 2, "clearedFloor": 3, "experience": 0})
        self.assertEqual(before, read_progress(db, cat))
        self.assertEqual(before["seasonData"]["2"]["Abilities"], [4010102])
        before["active"] = {"floor": 7}
        with db:
            save_progress(db, before)
        with self.assertRaisesRegex(ValueError, "active Tetis"), db:
            edit_progress(db, cat, {"seasonId": 2, "experience": 50})

    def test_sweep_free_paid_reset_and_bounded_reward(self):
        cat = self.catalog
        cat.sweep_counter = {"PlayLimit": 1, "RefillLimit": 1, "RefillCost": [3]}
        cat.data["Constants"]["SeasonArtifactDropRate"] = 1
        coin = {"ItemId": 772, "Amount": 5}
        cat.data["SweepRewards"] = [
            {
                "SeasonId": 2,
                "Floor": 1,
                "PointReward": 40,
                "SweepRewards": {
                    "Candidate": {
                        "MinCount": 1,
                        "MaxCount": 1,
                        "Items": [{"Item": coin, "Probability": 1}],
                    },
                    "CandidateSet": [],
                },
            }
        ]
        now = datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc)
        state = read_progress(self.db, cat)
        state["seasonData"]["2"]["Artifacts"] = {"8": 19}
        profile = {"User": {"Assets": [{"Id": 70003, "Amount": 7, "Spent": 4}]}}
        with patch(
            "guardian_tales.modes.tetis.tetis_sweep.grant",
            side_effect=lambda account, profile, items: {"AddedItems": list(items)},
        ):
            with self.assertRaises(ValueError):
                sweep(None, profile, state, cat, 1, now)
            state["floors"]["1"] = 1
            rewards = sweep(None, profile, state, cat, 2, now)
            self.assertEqual(rewards["AddedItems"], [coin, coin])
            self.assertEqual(rewards["Exp"], 60)
            self.assertEqual(rewards["ArtifactIds"], [8, 8])
            # Both low-level drops leave the edited higher-level artifact equipped or available.
            self.assertEqual(state["seasonData"]["2"]["Artifacts"], {"8": 19})
            self.assertEqual(profile["User"]["Assets"][0], {"Id": 70003, "Amount": 4, "Spent": 7})
            with self.assertRaises(ValueError):
                sweep(None, profile, state, cat, 1, now)
            tomorrow = counter(state, cat, now + timedelta(minutes=2))
            self.assertEqual((tomorrow["PlayCount"], tomorrow["RefillCount"]), (0, 0))
            self.assertEqual(state["sweepCounter"]["PlayCount"], 1)

    def test_shared_loadout_validates_training_and_ownership_after_all_changes(self):
        cat, db = self.catalog, self.db
        with db:
            edit_progress(
                db, cat, {"seasonId": 1, "artifactLevels": {"8": 15}, "artifactId": 8, "spellId": 1}
            )
        view = editor_view(db, cat)["loadout"]
        self.assertEqual(
            (view["artifactId"], view["artifacts"][0]["level"], view["spellId"]), (8, 15, 1)
        )
        self.assertEqual([s["unlocked"] for s in view["spells"]], [True, False])
        for request in (
            {"artifactLevels": {"7": 4}},
            {"artifactLevels": {"8": 21}},
            {"artifactId": 7},
            {"spellId": 3},
            {"spellId": None},
            {"artifactLevels": {"8": True}},
            {"artifactLevels": {"08": 3}},
            {"artifactLevels": {"8": 0}, "artifactId": 8},
        ):
            with self.subTest(request=request), self.assertRaises(ValueError), db:
                edit_progress(db, cat, {"seasonId": 1, **request})
        self.assertEqual(editor_view(db, cat)["loadout"], view)
        with db:
            edit_progress(
                db,
                cat,
                {
                    "seasonId": 2,
                    "experience": 40,
                    "abilities": {"40101": 2, "40201": 1, "50101": 1},
                    "spellId": 3,
                },
            )
        state = read_progress(db, cat)
        self.assertEqual(state["seasonData"]["2"]["SpellId"], 3)
        self.assertEqual(state["seasonData"]["1"]["Artifacts"], {})
        with db:
            edit_progress(db, cat, {"seasonId": 2, "abilities": {}, "artifactLevels": {"8": 0}})
        state = read_progress(db, cat)["seasonData"]["2"]
        self.assertEqual((state["SpellId"], state["ArtifactId"], state["Artifacts"]), (0, 0, {}))

    def test_exchange_only_prior_coins_once(self):
        cat = self.catalog
        cat.data["Constants"]["SeasonCoinExchangeMagnification"] = 10
        rows = [{"Id": 771, "Amount": 13, "Spent": 9}, {"Id": 772, "Amount": 21, "Spent": 0}]
        with patch(
            "guardian_tales.modes.tetis.tetis_sweep.grant",
            side_effect=lambda account, profile, items: {"AddedItems": list(items)},
        ):
            result = exchange(None, {"User": {"Assets": rows}}, {}, cat)
            self.assertEqual(
                result,
                {"ExchangeItems": {"771": 13}, "AddedItems": [{"ItemId": 70001, "Amount": 130}]},
            )
            self.assertEqual(rows[0], {"Id": 771, "Amount": 0, "Spent": 22})
            self.assertEqual(rows[1]["Amount"], 21)
            self.assertEqual(exchange(None, {"User": {"Assets": rows}}, {}, cat)["AddedItems"], [])
