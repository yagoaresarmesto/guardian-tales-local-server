# SPDX-License-Identifier: Apache-2.0
"""Finish Challenge ends only the local run and never grants account rewards."""

import copy
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from guardian_tales.modes.kamazone import kamazone_battle as battle
from guardian_tales.modes.kamazone import kamazone_run as run
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.runtime.protocol import PacketError
from tests.account.test_snapshots import request
from tests.content import test_kamazone_run as fixtures
from tests.content.test_kamazone import NOW


class KamazoneConcludeTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazoneRunTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.session, self.root = self.owner.session, self.owner.root
        self.path = self.root / run.STATE
        self.sequence = 9000
        self.body = {"keepingArtifactId": None}

    def call(self, route, body, sequence=None):
        self.sequence += 1
        packet = request(route, body)
        packet["sequence_id"] = self.sequence if sequence is None else sequence
        response = self.session.handle(packet)
        self.assertEqual(
            (response.packet_type, response.body_type, response.sequence_id),
            (1, 1, packet["sequence_id"]),
        )
        return json.loads(response.body)

    def entry(self):
        return self.call("/kamazonland/enter", {"IsPartial": False})["UserKamazonLand"]

    def finish(self, sequence=None):
        return self.call(run.CONCLUDE, self.body, sequence)["UserKamazonLand"]

    def opened(self):
        user = self.owner.challenge()
        self.node = self.owner.opening(user)["Id"]
        self.owner.select()
        return self.owner.call(run.START, {"NodeId": self.node})

    def combat(self):
        user = self.opened()
        user = self.owner.call(run.BATTLE, dict(NodeId=self.node, Formation=[12, 3, 19, 9]))
        self.result = dict(
            NodeId=self.node,
            Result=1,
            CharacterHps={str(i): 4321 for i in self.owner.characters},
            MonsterHps=[0]
            * len(next(n for n in user["Nodes"] if n["Id"] == self.node)["BattleMonsters"]),
        )
        return user

    def reject(self, route, body):
        before = self.path.read_bytes() if self.path.exists() else None
        with self.assertRaises(PacketError):
            self.call(route, body)
        self.assertEqual(self.path.read_bytes() if self.path.exists() else None, before)

    def assert_closed(self, before, user):
        expected = copy.deepcopy(before)
        expected["Progress"]["Concluded"] = True
        self.assertEqual(user, expected)
        state = run.load(self.session.store.references)
        self.assertFalse(state["active"] or state["stage_started"] or state["battle_started"])
        self.assertIsNone(state["pending_result"])
        self.assertEqual(self.entry(), user)
        self.owner.assert_untouched()

    def test_native_finish_closes_an_open_encounter_and_reopening_retains_the_concluded_view(self):
        before = self.opened()
        response = self.call(run.CONCLUDE, self.body, 901)
        self.assertEqual(set(response), {"NewSeason", "UserKamazonLand"})
        self.assertFalse(response["NewSeason"])
        user = response["UserKamazonLand"]
        self.assert_closed(before, user)
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.assertEqual(self.entry(), user)
        self.assertEqual(self.finish(), user)
        self.assert_closed(before, user)

    def test_a_completed_boss_can_finish_without_claiming_a_clear_or_resetting_hp_and_statistics(
        self,
    ):
        self.combat()
        self.call(battle.END, self.result)
        self.call(run.START, {"NodeId": 120})
        boss = self.call(run.BATTLE, dict(NodeId=120, Formation=[12, 3, 19, 9]))["UserKamazonLand"]
        result = dict(
            self.result,
            NodeId=120,
            MonsterHps=[0]
            * len(next(n for n in boss["Nodes"] if n["Id"] == 120)["BattleMonsters"]),
        )
        before = self.call(battle.END, result)["UserKamazonLand"]
        self.assertEqual(before["Progress"]["Battle"], 2)
        self.assert_closed(before, self.finish())

    def test_finished_run_rejects_new_stage_battle_and_results_until_an_explicit_new_challenge(
        self,
    ):
        self.combat()
        self.call(battle.END, self.result)
        self.finish()
        for route, body in (
            (run.START, {"NodeId": 120}),
            (run.BATTLE, dict(NodeId=self.node, Formation=[12, 3, 19, 9])),
            (battle.END, self.result),
            (battle.CLOSE, {"NodeId": self.node}),
        ):
            self.reject(route, body)
        self.owner.assert_untouched()

    def test_recent_finish_retry_does_not_end_or_change_a_new_challenge(self):
        self.opened()
        ended = self.finish(902)
        saved = self.path.read_bytes()
        self.assertEqual(self.finish(902), ended)
        self.assertEqual(self.path.read_bytes(), saved)
        new = self.owner.challenge(1)
        self.assertFalse(new["Progress"]["Concluded"])
        self.assertEqual(
            new["Progress"],
            dict(
                Floor=1,
                CurrentNodeId=100,
                Concluded=False,
                KeepingArtifactId=None,
                CanPickArtifactAid=False,
                CanPickCurseAid=False,
            ),
        )
        self.assertNotIn("Battle", new["Progress"])
        self.assertTrue(all(hp == 10000 for hp in new["Hps"].values()))
        saved = self.path.read_bytes()
        self.assertEqual(self.finish(902), new)
        self.assertEqual(self.path.read_bytes(), saved)
        self.reject(run.CONCLUDE, self.body)
        self.owner.assert_untouched()

    def test_missing_run_starting_position_malformed_fields_and_artifact_ids_are_rejected(self):
        self.reject(run.CONCLUDE, self.body)
        self.owner.select()
        self.reject(run.CONCLUDE, self.body)
        self.owner.challenge()
        self.reject(run.CONCLUDE, self.body)
        self.owner.call(run.START, {"NodeId": self.owner.opening(self.entry())["Id"]})
        for body in (
            None,
            {},
            {"KeepingArtifactId": None},
            {"keepingArtifactId": None, "Extra": 1},
            *[{"keepingArtifactId": i} for i in (0, -1, True, 1, "1", 1.0)],
        ):
            self.reject(run.CONCLUDE, body)
        self.owner.assert_untouched()

    def test_active_combat_and_unresolved_victory_choices_cannot_be_bypassed_by_finishing(self):
        self.combat()
        self.reject(run.CONCLUDE, self.body)
        source = self.session.store.references.read_bytes("static_data_get.bin")
        state = run.load(self.session.store.references)
        nodes = copy.deepcopy(run.floor_nodes(source, 43, state["seed"]))
        next(n for n in nodes if n["Id"] == self.node)["LootArtifacts"] = [[900]]
        with patch("guardian_tales.modes.kamazone.kamazone_run.floor_nodes", return_value=nodes):
            self.call(battle.END, self.result)
            self.reject(run.CONCLUDE, self.body)
        self.owner.assert_untouched()

    def test_reported_loss_can_finish_without_healing_or_awarding_anything(self):
        self.combat()
        result = dict(self.result, Result=3, MonsterHps=[5000])
        before = self.call(battle.END, result)["UserKamazonLand"]
        self.assert_closed(before, self.finish())

    def test_authentication_expired_disabled_foreign_and_failed_publication_do_not_change_run(self):
        self.opened()
        self.session.signed_in = False
        self.reject(run.CONCLUDE, self.body)
        self.session.signed_in = True
        with patch(
            "guardian_tales.modes.kamazone.kamazone.utc_now", return_value=NOW + timedelta(days=22)
        ):
            self.reject(run.CONCLUDE, self.body)
        with patch(
            "guardian_tales.modes.kamazone.kamazone_run.atomic_write",
            side_effect=OSError("synthetic"),
        ):
            self.reject(run.CONCLUDE, self.body)
        saved = self.path.read_bytes()
        value = json.loads(saved)
        for key, other in (("user_id", 999), ("season_id", 41), ("source_sha256", "0" * 64)):
            self.path.write_text(json.dumps(dict(value, **{key: other})))
            self.reject(run.CONCLUDE, self.body)
        self.path.write_bytes(saved)
        self.owner.owner.command("disable")
        self.reject(run.CONCLUDE, self.body)
