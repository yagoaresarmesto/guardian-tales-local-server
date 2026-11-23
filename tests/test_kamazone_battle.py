# SPDX-License-Identifier: Apache-2.0
"""Native Kama-ZONE results retain HP and settle victory silver once."""

import copy
import json
import unittest
from unittest.mock import patch

from guardian_tales import kamazone_battle as battle
from guardian_tales import kamazone_run as run
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.protocol import PacketError
from tests import test_kamazone_run as fixtures
from tests.test_snapshots import request


class KamazoneBattleTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazoneRunTests()
        self.owner.node_kind = getattr(self, "node_kind", None)
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.session, self.db, self.root = self.owner.session, self.owner.db, self.owner.root
        user = self.owner.challenge()
        self.node = self.owner.opening(user)
        self.owner.call(run.START, {"NodeId": self.node["Id"]})
        self.owner.select()
        self.initial = self.owner.call(
            run.BATTLE, dict(NodeId=self.node["Id"], Formation=[12, 3, 19, 9])
        )
        self.path = self.root / run.STATE
        self.sequence = 5000
        self.result = dict(
            NodeId=self.node["Id"],
            Result=1,
            CharacterHps={str(i): 4321 for i in self.owner.characters},
            MonsterHps=[0] * len(self.node["BattleMonsters"]),
        )
        self.closing = dict(NodeId=self.node["Id"], LootArtifactId=None, DiscardArtifactIndex=None)

    def call(self, route, body, sequence=None):
        self.sequence += 1
        packet = request(route, body)
        packet["sequence_id"] = sequence if sequence is not None else self.sequence
        reply = self.session.handle(packet)
        self.assertEqual(
            (reply.packet_type, reply.body_type, reply.sequence_id), (1, 1, packet["sequence_id"])
        )
        return json.loads(reply.body)

    def entry(self):
        return self.call("/kamazonland/enter", {"IsPartial": False})["UserKamazonLand"]

    def reopened(self):
        epoch = self.session.request_epoch
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.session.request_epoch = epoch
        return self.entry()

    def finish(self):
        return self.call(battle.END, self.result)

    def reject(self, route, body):
        before = self.path.read_bytes()
        with self.assertRaises(PacketError):
            self.call(route, body)
        self.assertEqual(self.path.read_bytes(), before)

    def assert_no_account_or_static_changes(self, user):
        for key in (
            "Benefits",
            "KamazonPoint",
            "KamazonPointTotal",
            "ClearRecords",
            "ClearRecordsInSeason",
        ):
            self.assertEqual(user[key], self.initial[key], key)
        self.owner.assert_untouched()

    def test_empty_victory_persists_and_allows_the_next_battle_without_a_close_request(self):
        response = self.finish()
        self.assertEqual(set(response), {"NewSeason", "UserKamazonLand", "ArtifactEffectResults"})
        self.assertEqual(response["ArtifactEffectResults"], [])
        ended = response["UserKamazonLand"]
        self.assertEqual(ended["Progress"]["Battle"], 1)
        self.assertEqual(next(n for n in ended["Nodes"] if n["Id"] == self.node["Id"])["State"], 11)
        self.assertEqual(
            [
                m["Hp"]
                for m in next(n for n in ended["Nodes"] if n["Id"] == self.node["Id"])[
                    "BattleMonsters"
                ]
            ],
            self.result["MonsterHps"],
        )
        for key, hp in self.result["CharacterHps"].items():
            self.assertEqual(ended["Hps"][key], hp)
        self.assertEqual(self.reopened(), ended)
        state = run.load(self.session.store.references)
        self.assertFalse(state["stage_started"] or state["battle_started"])
        self.assertIsNone(state["pending_result"])
        self.assert_no_account_or_static_changes(ended)
        self.call(run.START, {"NodeId": 120})
        next_battle = self.call(run.BATTLE, dict(NodeId=120, Formation=[12, 3, 19, 9]))[
            "UserKamazonLand"
        ]
        self.assertEqual(next_battle["Progress"]["CurrentNodeId"], 120)
        self.assertEqual(next_battle["Hps"], ended["Hps"])
        self.assertTrue(
            all(
                m["Hp"] == 10000
                for m in next(n for n in next_battle["Nodes"] if n["Id"] == 120)["BattleMonsters"]
            )
        )
        self.assert_no_account_or_static_changes(next_battle)

    def test_unresolved_loot_choices_still_block_automatic_closing_and_advancement(self):
        value = run.load(self.session.store.references)
        source = self.session.store.references.read_bytes("static_data_get.bin")
        nodes = copy.deepcopy(run.floor_nodes(source, value["season_id"], value["seed"]))
        next(n for n in nodes if n["Id"] == self.node["Id"])["LootArtifacts"] = [[900]]
        with patch("guardian_tales.kamazone_run.floor_nodes", return_value=nodes):
            ended = self.finish()["UserKamazonLand"]
            self.assertEqual(
                next(n for n in ended["Nodes"] if n["Id"] == self.node["Id"])["State"], 3
            )
            self.reject(run.START, {"NodeId": 120})
            self.reject(run.SELECT, {"CharacterIds": self.owner.characters})
            self.reject(run.BATTLE, dict(NodeId=self.node["Id"], Formation=[12, 3, 19, 9]))
            self.reject(battle.CLOSE, self.closing)
            self.assert_no_account_or_static_changes(self.entry())

    def test_existing_pending_empty_victory_resumes_without_read_writes_or_a_reset(self):
        self.finish()
        legacy = json.loads(self.path.read_bytes())
        legacy.update(pending_result=1, stage_started=True)
        legacy["states"][str(self.node["Id"])] = 3
        self.path.write_text(json.dumps(legacy))
        old = self.path.read_bytes()
        view = self.reopened()
        self.assertEqual(next(n for n in view["Nodes"] if n["Id"] == self.node["Id"])["State"], 11)
        self.assertEqual(self.path.read_bytes(), old)
        self.reject(run.START, {"NodeId": 100})
        self.reject(run.START, {"NodeId": 999})
        self.assertEqual(self.path.read_bytes(), old)
        self.call(run.SELECT, {"CharacterIds": self.owner.characters})
        self.call(run.START, {"NodeId": 120})
        current = run.load(self.session.store.references)
        self.assertEqual(current["states"][str(self.node["Id"])], 11)
        self.assertIsNone(current["pending_result"])
        self.assertEqual(
            (current["seed"], current["hps"], current["battle_count"]),
            (legacy["seed"], legacy["hps"], 1),
        )
        self.assert_no_account_or_static_changes(self.entry())

    def test_empty_victories_finalize_for_normal_elite_and_boss_node_types(self):
        for kind in run.COMBAT:
            with self.subTest(kind=kind):
                case = KamazoneBattleTests()
                self.addCleanup(case.doCleanups)
                case.node_kind = kind
                case.setUp()
                self.assertEqual(case.node["Type"], kind)
                ended = case.finish()["UserKamazonLand"]
                self.assertEqual(
                    next(n for n in ended["Nodes"] if n["Id"] == case.node["Id"])["State"], 11
                )
                amount = {"Normal": 10, "Elite": 20, "Boss": 30}[kind]
                self.assertEqual(ended["SilverCoin"], case.initial["SilverCoin"] + amount)
                self.assertEqual(case.reopened(), ended)
                for _ in range(2):
                    packet = case.call(battle.CLOSE, case.closing)
                    self.assertEqual(packet["AddedSilverCoin"], amount)
                    self.assertEqual(packet["UserKamazonLand"], ended)
                case.assert_no_account_or_static_changes(ended)

    def test_recent_results_and_close_retries_cannot_replace_a_newer_battle(self):
        self.call(battle.END, self.result, 401)
        self.call(battle.CLOSE, self.closing, 402)
        self.call(run.START, {"NodeId": 120})
        latest = self.call(run.BATTLE, dict(NodeId=120, Formation=[12, 3, 19, 9]))[
            "UserKamazonLand"
        ]
        before = self.path.read_bytes()
        self.assertEqual(self.call(battle.END, self.result, 401)["UserKamazonLand"], latest)
        self.assertEqual(self.call(battle.CLOSE, self.closing, 402)["UserKamazonLand"], latest)
        self.assertEqual(self.path.read_bytes(), before)
        self.reject(battle.END, self.result)
        self.assert_no_account_or_static_changes(latest)

    def test_same_result_with_new_sequence_does_not_count_or_apply_hp_twice(self):
        ended = self.finish()["UserKamazonLand"]
        self.assertEqual(self.finish()["UserKamazonLand"], ended)
        changed = dict(self.result, CharacterHps={str(self.owner.characters[0]): 9000})
        self.reject(battle.END, changed)
        closed = self.call(battle.CLOSE, self.closing)["UserKamazonLand"]
        self.assertEqual(self.finish()["UserKamazonLand"], closed)
        self.assertEqual(self.call(battle.CLOSE, self.closing)["UserKamazonLand"], closed)
        self.assertEqual(
            self.call(battle.CLOSE, {"NodeId": self.node["Id"]})["UserKamazonLand"], closed
        )
        self.assertEqual(closed["Progress"]["Battle"], 1)
        self.assert_no_account_or_static_changes(closed)

    def test_draw_defeat_and_timeout_preserve_enemy_hp_without_unlocking_the_next_node(self):
        for result in (2, 3, 4):
            with self.subTest(result=result):
                body = dict(
                    self.result, Result=result, MonsterHps=[5000] * len(self.node["BattleMonsters"])
                )
                ended = self.call(battle.END, body)["UserKamazonLand"]
                node = next(n for n in ended["Nodes"] if n["Id"] == self.node["Id"])
                self.assertEqual(node["State"], 5)
                self.assertEqual(ended["SilverCoin"], self.initial["SilverCoin"])
                self.assertTrue(all(m["Hp"] == 5000 for m in node["BattleMonsters"]))
                self.reject(run.START, {"NodeId": 120})
                if result != 3:
                    self.call(battle.CLOSE, self.closing)
                    self.reject(run.START, {"NodeId": 120})
                    self.call(run.START, {"NodeId": self.node["Id"]})
                self.call(run.BATTLE, dict(NodeId=self.node["Id"], Formation=[12, 3, 19, 9]))
                self.assertEqual(
                    next(n for n in self.entry()["Nodes"] if n["Id"] == self.node["Id"])["State"], 1
                )
                self.assert_no_account_or_static_changes(self.entry())
        self.assertEqual(self.entry()["Progress"]["Battle"], 3)

    def test_dead_party_hp_is_not_reset_by_reopen_or_battle_retry(self):
        body = dict(
            self.result,
            Result=3,
            CharacterHps={str(i): 0 for i in self.owner.characters},
            MonsterHps=[5000] * len(self.node["BattleMonsters"]),
        )
        ended = self.call(battle.END, body)["UserKamazonLand"]
        self.assertEqual(self.reopened(), ended)
        self.reject(run.BATTLE, dict(NodeId=self.node["Id"], Formation=[12, 3, 19, 9]))
        self.assert_no_account_or_static_changes(ended)

    def test_malformed_foreign_inconsistent_and_unstarted_results_leave_the_run_intact(self):
        for field, values in (
            ("NodeId", [0, True, 120, 999]),
            ("Result", [0, 5, True, 1.0, "1"]),
            ("CharacterHps", [None, [], {"01": 100}, {"999999": 10}]),
        ):
            for value in values:
                self.reject(battle.END, dict(self.result, **{field: value}))
        for hp in (-1, 10001, True, 1.0, "1"):
            self.reject(
                battle.END, dict(self.result, CharacterHps={str(self.owner.characters[0]): hp})
            )
        for hps in (
            None,
            {},
            [],
            [0] * (len(self.node["BattleMonsters"]) + 1),
            [1] * len(self.node["BattleMonsters"]),
            [True] * len(self.node["BattleMonsters"]),
        ):
            self.reject(battle.END, dict(self.result, MonsterHps=hps))
        self.reject(battle.CLOSE, self.closing)
        self.owner.challenge()
        self.reject(battle.END, self.result)
        self.assert_no_account_or_static_changes(self.entry())

    def test_close_rejects_a_foreign_node_and_unimplemented_artifact_choices(self):
        self.finish()
        for patch_body in (dict(NodeId=120), dict(LootArtifactId=1), dict(DiscardArtifactIndex=0)):
            self.reject(battle.CLOSE, dict(self.closing, **patch_body))
        self.assert_no_account_or_static_changes(self.entry())

    def test_failed_publication_and_unsigned_results_never_change_hp_or_clear_state(self):
        for route, body in ((battle.END, self.result), (battle.CLOSE, self.closing)):
            self.session.signed_in = False
            self.reject(route, body)
            self.session.signed_in = True
        for route, body in ((battle.END, self.result), (battle.CLOSE, self.closing)):
            with patch(
                "guardian_tales.kamazone_run.atomic_write", side_effect=OSError("synthetic")
            ):
                self.reject(route, body)
            if route == battle.END:
                self.finish()
        self.assert_no_account_or_static_changes(self.entry())

    def test_legacy_run_hp_defaults_are_read_only_and_completion_adds_them_atomically(self):
        previous = json.loads(self.path.read_bytes())
        for key in battle.defaults():
            del previous[key]
        self.path.write_text(json.dumps(previous))
        old = self.path.read_bytes()
        self.assertEqual(self.reopened(), self.initial)
        self.assertEqual(self.path.read_bytes(), old)
        self.finish()
        self.assertTrue(set(battle.defaults()) <= json.loads(self.path.read_bytes()).keys())
        self.assert_no_account_or_static_changes(self.entry())
