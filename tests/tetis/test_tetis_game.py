# SPDX-License-Identifier: Apache-2.0
"""Exercise Tetis game packets and web-editor changes against the same working save."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from guardian_tales import tetis, tetis_map_trial
from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from guardian_tales.tetis_catalog import TetisCatalog
from guardian_tales.tetis_progress import edit_progress, read_progress
from tests.account.test_snapshots import request


class TetisGameTests(unittest.TestCase):
    def setUp(self):
        refs = self.enterContext(tempfile.TemporaryDirectory())
        self.db = self.enterContext(closing(sqlite3.connect(":memory:")))
        self.session = BootstrapSession(GuestStore(self.db, refs))
        self.account = self.session.store.account
        self.enterContext(patch.object(self.account, "needs_prologue", return_value=False))
        self.session.signed_in = True
        self.sequence = 0
        reward = {"ItemId": 70001, "Amount": 2}
        data = {
            "Seasons": [
                dict(Id=i, Current=i == 3, SeasonLastStage=2, SummonerSpellsUI=[1, 3])
                for i in (1, 3)
            ],
            "Floors": [
                dict(SeasonId=i, Floor=f, PointReward=100, AchieveRewards=[reward])
                for i in (1, 3)
                for f in (1, 2)
            ],
            "Constants": dict(
                MaxFloor=2,
                MaxAbilityPoint=5,
                LevelPerPoint=1,
                RecordReward=[reward],
                ArtifactLevels=[1, 101],
            ),
            "Narratives": [dict(Id=9, SeasonId=1, UnlockFloor=1)],
            "RogueChessLevel": [dict(Level=i, TotalExp=i * 100) for i in range(1, 4)],
            "AbilityCategories": [
                dict(Id=3, SeasonId=3, StepMinimumPoints=[0], UnlockConditions=[])
            ],
            "AbilityNodes": [
                dict(NodeId=101, AbilityCategoryId=3, Step=1, MaxPoints=2, SummonerSpellId=3)
            ],
            "AbilitySpecs": [],
            "SummonerSpells": [dict(Id=1, Name="starter"), dict(Id=3, Name="trained")],
            "SeasonArtifacts": [dict(Id=8, Name="gauntlet", SeasonId=3)],
        }
        self.catalog = TetisCatalog(data)
        self.enterContext(patch.object(tetis, "load_catalog", return_value=self.catalog))

    def call(self, route, body, sequence=None):
        self.sequence += 1
        packet = request(route, body)
        packet["sequence_id"] = self.sequence if sequence is None else sequence
        return json.loads(self.session.handle(packet).body)

    def battle(self, route, floor, *, won=None, season=3, sequence=None):
        info = dict(SeasonId=season, Floor=floor)
        if won is not None:
            info["IsCleared"] = won
        key = "StartStageInfo" if route == tetis.START else "EndStageInfo"
        return self.call(route, {key: info}, sequence)

    def test_recommended_counts_use_saved_current_season(self):
        from guardian_tales import lobby
        from guardian_tales.tetis_progress import save_progress
        from guardian_tales.tetis_sweep import counter

        with self.db:
            state = read_progress(self.db, self.catalog)
            state["floors"].update({"1": 2, "3": 1})
            state["sweepCounter"] = dict(counter(state, self.catalog), PlayCount=2)
            save_progress(self.db, state)
        with patch("guardian_tales.tetis_progress.load_catalog", return_value=self.catalog):
            packet = lobby.respond(request("/content-book/recommend", {}), object(), self.db)
        body = json.loads(packet.body)
        self.assertEqual((body["RogueChessFloor"], body["RogueChessSweepCount"]), (1, 2))

    def trial_source(self, original_stage="roguechess_1"):
        floors = [
            {"Id": 10001, "SeasonId": 1, "Floor": 1, "StageId": 280010011, "WavePresetIds": [30]},
            {"Id": 10002, "SeasonId": 1, "Floor": 2, "StageId": 280010011, "WavePresetIds": [31]},
        ]
        stages = [
            {"Id": ident, "Tilemap": {"Default": name}, "Event": ["RogueChess"]}
            for ident, name in (
                (280010011, "roguechess_season_1_normal"),
                (280010001, original_stage),
            )
        ]
        tables = {
            "roguechess3": json.dumps({"Floors": floors}),
            "stages": json.dumps(stages),
            "constants": '{"ChangeNickCost":300}',
            "__checksum__": "stock",
        }
        source = compress(
            "".join(f"{k}\n{v}\n12\n{digest(v.encode())}\n" for k, v in tables.items()).encode()
        )
        (self.session.store.references.directory / "static_data_get.bin").write_bytes(source)
        return source

    def test_map_trial_switches_one_floor_and_revises_client_cache_on_each_transition(self):
        refs = self.session.store.references
        original = self.trial_source()

        def fetched():
            return records(decode(self.session.handle(request("/static-data/get", {})).body))[1]

        baseline = fetched()
        self.assertEqual(json.loads(baseline["constants"][1])["ChangeNickCost"], 0)
        old_checksum = baseline["__checksum__"][1]
        self.assertEqual(tetis_map_trial.configure(refs, False)["generation"], 0)
        for generation, enabled in enumerate((True, False, True), 1):
            result = tetis_map_trial.configure(refs, enabled)
            self.assertEqual(result["generation"], generation)
            self.assertEqual(tetis_map_trial.configure(refs, enabled), result)
            new = self.call("/static-data/check-update", {"Checksum": old_checksum})
            self.assertFalse(new["UpToDate"])
            self.assertTrue(
                self.call("/static-data/check-update", {"Checksum": new["Checksum"]})["UpToDate"]
            )
            changed = fetched()
            self.assertEqual(changed["__checksum__"][1], new["Checksum"])
            old_checksum = new["Checksum"]
            self.assertEqual(changed["stages"], baseline["stages"])
            self.assertEqual(changed["constants"], baseline["constants"])
            expected = json.loads(baseline["roguechess3"][1])
            expected["Floors"][0]["StageId"] = 280010001 if enabled else 280010011
            self.assertEqual(json.loads(changed["roguechess3"][1]), expected)
            self.assertEqual(changed["roguechess3"][2], baseline["roguechess3"][2] + generation)
            if not enabled:
                self.assertEqual(changed["roguechess3"][1], baseline["roguechess3"][1])
        self.assertEqual(refs.read_bytes("static_data_get.bin"), original)

    def test_map_trial_rejects_unmatched_stage_before_publishing(self):
        refs = self.session.store.references
        self.trial_source(original_stage="different_board")
        with self.assertRaisesRegex(ValueError, "roguechess_1"):
            tetis_map_trial.configure(refs, True)
        self.assertEqual(tetis_map_trial.selection(refs), (False, 0))

    def test_entry_win_loss_replay_and_editor(self):
        roster = {"Cas": 1, "Presets": [{"Id": 1700, "Characters": [{"Id": 8}]}]}
        with self.db:
            self.db.execute(
                "INSERT INTO character_list_preset_state (id,value) VALUES (1,?)",
                (json.dumps(roster),),
            )
        entered = self.call(tetis.ENTER, {"IsPartial": False})
        self.assertEqual(
            entered["UserRogueChess"]["Presets"], {"1": {"Id": 1, "Characters": [{"Id": 8}]}}
        )
        self.assertEqual(entered["UserRogueChess"]["SeasonId"], 3)
        self.assertEqual(entered["UserRogueChess"]["SweepCounter"]["Type"], 14)
        with self.assertRaises(PacketError):
            self.battle(tetis.START, 2)
        self.battle(tetis.START, 1)
        self.assertEqual(self.battle(tetis.END, 1, won=False)["UserRogueChess"]["Floors"]["3"], 0)
        self.battle(tetis.START, 1)
        earned = self.battle(tetis.END, 1, won=True, sequence=100)
        self.assertEqual(earned["UserRogueChess"]["Floors"]["3"], 1)
        self.assertEqual(earned["AddedItems"][0]["Amount"], 2)
        with self.db:
            edit_progress(self.db, self.catalog, dict(seasonId=3, experience=140))
        old = self.battle(tetis.END, 1, won=True, sequence=100)
        self.assertEqual(old["UserRogueChess"]["SeasonData"]["Exp"], 140)
        self.assertEqual(old["User"]["Cas"], earned["User"]["Cas"])
        with self.assertRaises(PacketError):
            self.battle(tetis.END, 1, won=False, sequence=100)
        self.battle(tetis.START, 1)
        repeat = self.battle(tetis.END, 1, won=True)
        self.assertEqual(repeat["AddedItems"], [])
        self.assertEqual(repeat["UserRogueChess"]["SeasonData"]["Exp"], 140)
        self.assertEqual(self.call(tetis.RANK, {"SeasonId": 1}), {"Rankings": [], "Mine": None})

    def test_skills_kit_narrative_and_interrupted_battle(self):
        self.call(tetis.ENTER, {"IsPartial": True}, 101)
        self.battle(tetis.START, 1)
        self.call(tetis.ENTER, {"IsPartial": True}, 101)
        self.assertTrue(read_progress(self.db, self.catalog)["active"])
        self.call(tetis.ENTER, {"IsPartial": False})
        self.assertIsNone(read_progress(self.db, self.catalog)["active"])
        with self.assertRaises(PacketError):
            self.call(tetis.LOADOUT, {"SpellId": 3})
        self.call(tetis.ABILITY, {"Abilities": [3010101]})
        self.assertEqual(
            self.call(tetis.LOADOUT, {"SpellId": 3, "ArtifactId": None})["UserRogueChess"][
                "SeasonData"
            ]["SpellId"],
            3,
        )
        with self.assertRaises(PacketError):
            self.call(tetis.ABILITY, {"Abilities": [3010101, 3010101]})
        self.assertEqual(
            self.call(tetis.ABILITY, {"Abilities": []})["UserRogueChess"]["SeasonData"]["SpellId"],
            0,
        )
        with self.assertRaises(PacketError):
            self.call(tetis.REWARD, {"NarrativeIds": [9]})
        self.call(tetis.MARK, {"NarrativeIds": [9]})
        self.assertEqual(
            self.call(tetis.REWARD, {"NarrativeIds": [9]})["UserRogueChess"]["Narratives"], {"9": 1}
        )
        self.assertEqual(self.call(tetis.REWARD, {"NarrativeIds": [9]})["AddedItems"], [])

    def test_archived_floor_retains_loadout_selected_in_lobby(self):
        with self.db:
            edit_progress(
                self.db, self.catalog, {"seasonId": 1, "artifactLevels": {"8": 70}, "artifactId": 8}
            )
        self.call(tetis.ABILITY, {"Abilities": [3010101]})
        self.call(tetis.LOADOUT, {"SpellId": 3, "ArtifactId": None})
        stage = {"SeasonId": 1, "Floor": 1, "SpellId": None, "ArtifactId": None}
        started = self.call(tetis.START, {"StartStageInfo": stage}, 100)
        self.assertEqual(started["UserRogueChess"]["SeasonData"]["SpellId"], 3)
        self.assertEqual(started["UserRogueChess"]["SeasonData"]["ArtifactId"], 8)
        self.assertEqual(started["UserRogueChess"]["SeasonData"]["Artifacts"], {"8": 70})
        self.assertEqual(started["UserRogueChess"]["SeasonId"], 1)
        self.assertEqual(self.call(tetis.START, {"StartStageInfo": stage}, 100), started)
        narrative = self.call(tetis.MARK, {"NarrativeIds": [9]})["UserRogueChess"]
        self.assertEqual((narrative["SeasonId"], narrative["SeasonData"]["SpellId"]), (1, 3))
        ended = self.battle(tetis.END, 1, season=1, won=True)
        self.assertEqual(ended["UserRogueChess"]["SeasonData"]["SpellId"], 3)
        self.assertEqual(ended["UserRogueChess"]["Floors"], {"1": 1, "3": 0})
