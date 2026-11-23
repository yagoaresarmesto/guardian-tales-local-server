# SPDX-License-Identifier: Apache-2.0
"""Local challenge entry uses preserved tiers and keeps account/benefits intact."""

import copy
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from guardian_tales import kamazone_run as run
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.protocol import PacketError
from tests import test_kamazone_practice as fixtures
from tests.test_kamazone import NOW
from tests.test_snapshots import request


class KamazoneRunTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazonePracticeTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.fixture = self.owner.fixture
        self.root, self.db, self.session = self.owner.root, self.owner.db, self.owner.session
        mode = self.fixture.tables["kamazonland2"]
        for season in mode["Seasons"]:
            season["MaxDifficulty"] = 3
        mode["Difficulty"] = [
            dict(
                Difficulty=i,
                Floor=1,
                NormalLevel=50 * i,
                EliteLevel=50 * i + 1,
                BossLevel=50 * i + 2,
            )
            for i in range(1, 4)
        ]
        mode["FloorPresets"] = [
            dict(Id=100, FloorId=1, Step=0, NextNodeIds=[110, 111]),
            *[
                dict(
                    Id=i,
                    FloorId=1,
                    Step=1,
                    NextNodeIds=[120],
                    NormalProb=0.7,
                    EliteProb=0,
                    ShelterProb=0,
                    ShopProb=0,
                    SpecialProb=0.3,
                )
                for i in (110, 111)
            ],
            dict(Id=120, FloorId=1, Step=2, NextNodeIds=None),
        ]
        mode["Monsters"] = [
            dict(Id=1, MonsterId=100002, Class="melee", Hidden=False),
            dict(Id=2, MonsterId=100003, Class="melee", Hidden=False),
            dict(Id=3, MonsterId=100004, Class="melee", Hidden=True),
        ]
        mode["BattlePresets"] = [
            dict(
                Id=i,
                GroupId=i,
                Difficulty=kind,
                Position=12,
                Monster=None,
                Class=["melee"],
                Hidden=False,
            )
            for i, kind in enumerate(run.COMBAT, 1)
        ]
        node_kind = getattr(self, "node_kind", None)
        if node_kind in run.COMBAT:
            for row in mode["FloorPresets"]:
                if row["Step"] == 1:
                    for kind in run.PROBABILITIES:
                        row[kind + "Prob"] = int(kind == node_kind)
                    if node_kind == "Boss":
                        row["NextNodeIds"] = None
            for row in mode["BattlePresets"]:
                row["Position"] = dict(Normal=12, Elite=3, Boss=19)[row["Difficulty"]]
        self.fixture.write_source()
        self.owner.command("select", "--season-id", "43")
        self.owner.enable()
        self.owner.save({"174": 1}, 900)
        self.characters = [
            r["Id"] for r in self.session.store.account.profile()["User"]["Characters"]
        ][:4]
        self.assertTrue(self.characters)
        self.sequence = 1000
        self.before = list(self.db.iterdump())
        self.changes = self.db.total_changes
        self.files = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.static = self.session.handle(request("/static-data/get", {})).body

    def call(self, route, body, sequence=None):
        self.sequence += 1
        packet = request(route, body)
        packet["sequence_id"] = sequence if sequence is not None else self.sequence
        reply = self.session.handle(packet)
        self.assertEqual(
            (reply.packet_type, reply.body_type, reply.sequence_id), (1, 1, packet["sequence_id"])
        )
        result = json.loads(reply.body)
        self.assertEqual(set(result), {"UserKamazonLand", "NewSeason"})
        return result["UserKamazonLand"]

    def entry(self):
        return self.call("/kamazonland/enter", {"IsPartial": False})

    def challenge(self, difficulty=3, sequence=None):
        return self.call(run.CHALLENGE, {"Difficulty": difficulty}, sequence)

    def select(self):
        return self.call(run.SELECT, {"CharacterIds": self.characters})

    def opening(self, user):
        return next(n for n in user["Nodes"] if n["Id"] in (110, 111) and n["Type"] in run.COMBAT)

    def assert_untouched(self):
        self.assertEqual(
            (list(self.db.iterdump()), self.db.total_changes), (self.before, self.changes)
        )
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != run.STATE}, self.files
        )
        self.assertEqual(self.session.handle(request("/static-data/get", {})).body, self.static)

    def test_all_three_tiers_generate_stable_connected_maps_without_changing_original_levels(self):
        for difficulty in (1, 2, 3):
            user = self.challenge(difficulty)
            self.assertEqual(user["Difficulty"], difficulty)
            self.assertEqual(user["Progress"], dict(Floor=1, CurrentNodeId=100, Concluded=False))
            self.assertEqual(len(user["Nodes"]), 4)
            self.assertEqual(self.opening(user)["Step"], 1)
            for node in user["Nodes"]:
                self.assertIs(type(node["BattleMonsters"]), list)
                self.assertIs(type(node["LootArtifacts"]), list)
                self.assertIs(type(node["ShopArtifacts"]), dict)
                for enemy in node["BattleMonsters"]:
                    self.assertIn(enemy["Id"], (1, 2))
                    self.assertEqual(
                        (enemy["Position"], enemy["Hp"], enemy["OptionId"]), (12, 10000, None)
                    )
            self.assertEqual((user["KamazonPoint"], user["KamazonPointTotal"]), (3750, 4000))
            self.assertEqual(user["Benefits"], [{"Id": 174, "Level": 1}])
            self.assertEqual(self.entry(), user)
        self.assert_untouched()

    def test_party_node_and_native_battle_handshake_persist_across_new_sessions_without_account_writes(
        self,
    ):
        user = self.challenge()
        node = self.opening(user)["Id"]
        user = self.select()
        self.assertEqual(user["Characters"], self.characters)
        self.assertTrue(all(hp == 10000 for hp in user["Hps"].values()))
        entered = self.call(run.START, {"NodeId": node})
        self.assertEqual(entered["Progress"]["CurrentNodeId"], node)
        formation = dict(Id=0, Positions=[12, 3, 19, 9])
        battle = self.call(run.BATTLE, dict(NodeId=node, Formation=formation["Positions"]))
        self.assertEqual(battle["Formation"], formation)
        self.assertEqual(next(n for n in battle["Nodes"] if n["Id"] == node)["State"], 1)
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.session.request_epoch = "reopened-local-run"
        self.assertEqual(self.entry(), battle)
        self.assert_untouched()

    def test_challenge_retry_never_rerolls_the_map_or_replaces_newer_difficulty(self):
        self.challenge(1, 101)
        latest = self.challenge(3, 102)
        before = (self.root / run.STATE).read_bytes()
        self.assertEqual(self.challenge(1, 101), latest)
        self.assertEqual((self.root / run.STATE).read_bytes(), before)
        self.assert_untouched()

    def test_party_can_be_selected_before_challenge_and_is_retained_on_challenge(self):
        user = self.select()
        self.assertTrue(user["Progress"]["Concluded"])
        self.assertEqual(self.challenge()["Characters"], self.characters)
        self.assert_untouched()

    def test_malformed_difficulties_and_parties_do_not_create_any_run(self):
        for route, body in [
            *[(run.CHALLENGE, {"Difficulty": i}) for i in (0, 4, -1, True, "3", 3.0)],
            (run.CHALLENGE, {"Difficulty": 3, "Extra": 1}),
            (run.SELECT, {"CharacterIds": []}),
            (run.SELECT, {"CharacterIds": self.characters * 5}),
            (run.SELECT, {"CharacterIds": [999999]}),
            (run.SELECT, {"CharacterIds": [True]}),
            (run.START, {"NodeId": 110}),
            (run.BATTLE, {"NodeId": 110, "Formation": [12, 3, 19, 9]}),
        ]:
            with self.subTest(route=route, body=body), self.assertRaises(PacketError):
                self.call(route, body)
        self.assertFalse((self.root / run.STATE).exists())
        self.assert_untouched()

    def test_battle_requires_owned_party_connected_node_and_matching_formation_handshake(self):
        user = self.challenge()
        node = self.opening(user)["Id"]
        self.select()
        for route, body in (
            (run.START, {"NodeId": 120}),
            (run.START, {"NodeId": 999}),
            (run.BATTLE, dict(NodeId=node, Formation=[12, 3, 19, 9])),
        ):
            previous = (self.root / run.STATE).read_bytes()
            with self.assertRaises(PacketError):
                self.call(route, body)
            self.assertEqual((self.root / run.STATE).read_bytes(), previous)
        self.call(run.START, {"NodeId": node})
        for route, body in (
            (run.START, {"NodeId": 120}),
            (run.BATTLE, dict(NodeId=120, Formation=[12, 3, 19, 9])),
            *[
                (run.BATTLE, dict(NodeId=node, Formation=p))
                for p in (
                    None,
                    {},
                    [],
                    {"Id": 0, "Positions": [12, 3, 19, 9]},
                    [12, 3, 19, 19],
                    [12, 3, 19],
                    [12, 3, 19, 9, 1],
                    [-1, 3, 19, 9],
                    [25, 3, 19, 9],
                    [True, 3, 19, 9],
                    [12.0, 3, 19, 9],
                    ["12", 3, 19, 9],
                )
            ],
        ):
            previous = (self.root / run.STATE).read_bytes()
            with self.assertRaises(PacketError):
                self.call(route, body)
            self.assertEqual((self.root / run.STATE).read_bytes(), previous)
        self.call(run.BATTLE, dict(NodeId=node, Formation=[12, 3, 19, 9]))
        previous = (self.root / run.STATE).read_bytes()
        with self.assertRaises(PacketError):
            self.select()
        self.assertEqual((self.root / run.STATE).read_bytes(), previous)
        self.assert_untouched()

    def test_native_position_array_returns_a_formation_model_and_preserves_newer_retries(self):
        node = self.opening(self.challenge())["Id"]
        self.call(run.START, {"NodeId": node})
        self.select()
        path = self.root / run.STATE
        value = json.loads(path.read_bytes())
        value["formation"] = dict(Id=9, Positions=[12, 3, 19, 9])
        path.write_text(json.dumps(value))
        positions = [0, 7, 14, 24]
        battle = self.call(run.BATTLE, dict(NodeId=node, Formation=positions), 310)
        expected = dict(Id=9, Positions=positions)
        self.assertEqual(battle["Formation"], expected)
        self.assertEqual(run.load(self.session.store.references)["formation"], expected)
        self.assertTrue(run.load(self.session.store.references)["battle_started"])
        self.assertEqual(battle["Characters"], self.characters)
        newer = self.call(run.BATTLE, dict(NodeId=node, Formation=[24, 19, 9, 0]), 311)
        saved = path.read_bytes()
        self.assertEqual(self.call(run.BATTLE, dict(NodeId=node, Formation=positions), 310), newer)
        self.assertEqual(path.read_bytes(), saved)
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.assertEqual(self.entry(), newer)
        self.assert_untouched()

    def test_native_node_then_party_then_battle_order_preserves_selection_and_budget(self):
        user = self.challenge()
        node = self.opening(user)["Id"]
        self.assertEqual(user["Characters"], [])
        opened = self.call(run.START, {"NodeId": node}, 710)
        self.assertEqual(opened["Characters"], [])
        self.assertEqual(opened["Progress"]["CurrentNodeId"], node)
        state = run.load(self.session.store.references)
        self.assertTrue(state["stage_started"])
        self.assertFalse(state["battle_started"])
        self.assertEqual(self.entry(), opened)
        with self.assertRaises(PacketError):
            self.call(run.BATTLE, dict(NodeId=node, Formation=[12, 3, 19, 9]))
        selected = self.select()
        self.assertEqual(self.call(run.START, {"NodeId": node}, 710), selected)
        battle = self.call(run.BATTLE, dict(NodeId=node, Formation=[12, 3, 19, 9]))
        self.assertTrue(run.load(self.session.store.references)["battle_started"])
        self.assertEqual(battle["Characters"], self.characters)
        self.assertEqual(battle["Benefits"], opened["Benefits"])
        self.assertEqual(battle["KamazonPoint"], opened["KamazonPoint"])
        self.assert_untouched()

    def test_existing_run_without_combat_phase_field_can_resume_without_read_writes(self):
        node = self.opening(self.challenge())["Id"]
        self.call(run.START, {"NodeId": node})
        path = self.root / run.STATE
        legacy = json.loads(path.read_bytes())
        del legacy["battle_started"]
        path.write_text(json.dumps(legacy))
        before = path.read_bytes()
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.session.request_epoch = "reopened-before-party"
        self.assertEqual(self.entry()["Progress"]["CurrentNodeId"], node)
        self.assertFalse(run.load(self.session.store.references)["battle_started"])
        self.assertEqual(path.read_bytes(), before)
        self.select()
        self.call(run.BATTLE, dict(NodeId=node, Formation=[12, 3, 19, 9]))
        self.assertTrue(json.loads(path.read_bytes())["battle_started"])
        self.assert_untouched()

    def test_normal_elite_and_boss_entry_uses_each_generated_nodes_actual_preset(self):
        for kind, position in (("Normal", 12), ("Elite", 3), ("Boss", 19)):
            with self.subTest(kind=kind):
                case = KamazoneRunTests()
                self.addCleanup(case.doCleanups)
                case.node_kind = kind
                case.setUp()
                user = case.challenge()
                target = case.opening(user)
                self.assertEqual(target["Type"], kind)
                opened = case.call(run.START, {"NodeId": target["Id"]})
                expected = next(n for n in opened["Nodes"] if n["Id"] == target["Id"])
                self.assertEqual(
                    (expected["Type"], expected["BattleMonsters"][0]["Position"]), (kind, position)
                )
                case.select()
                case.call(
                    run.BATTLE,
                    dict(NodeId=target["Id"], Formation=[12, 3, 19, 9]),
                )
                case.assert_untouched()

    def test_unsigned_incomplete_expired_disabled_and_source_mismatched_entry_stays_closed(self):
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.challenge()
        self.session.signed_in = True
        with patch("guardian_tales.kamazone.utc_now", return_value=NOW + timedelta(days=22)):
            with self.assertRaises(PacketError):
                self.challenge()
        self.owner.command("disable")
        with self.assertRaises(PacketError):
            self.challenge()
        self.owner.command("select", "--season-id", "43")
        self.fixture.tables["untouched"]["value"].append(4)
        self.fixture.write_source()
        with self.assertRaises(PacketError):
            self.challenge()
        self.owner.command("select", "--season-id", "43")
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        with self.assertRaises(PacketError):
            self.challenge()
        self.assertFalse((self.root / run.STATE).exists())

    def test_unrelated_owner_season_and_source_never_resume_a_foreign_run(self):
        self.challenge()
        saved = (self.root / run.STATE).read_bytes()
        original = json.loads(saved)
        for key, value in (("user_id", 999), ("season_id", 41), ("source_sha256", "0" * 64)):
            modified = dict(original, **{key: value})
            (self.root / run.STATE).write_text(json.dumps(modified))
            user = self.entry()
            self.assertTrue(user["Progress"]["Concluded"])
            self.assertEqual(user["Nodes"], [])
            self.assertEqual(json.loads((self.root / run.STATE).read_bytes()), modified)
        (self.root / run.STATE).write_bytes(saved)
        self.assertFalse(self.entry()["Progress"]["Concluded"])
        self.assert_untouched()

    def test_broken_graph_or_missing_difficulty_never_publishes_a_partial_run(self):
        original = copy.deepcopy(self.fixture.tables["kamazonland2"])
        for broken in ("difficulty", "graph", "monsters"):
            self.fixture.tables["kamazonland2"] = copy.deepcopy(original)
            mode = self.fixture.tables["kamazonland2"]
            if broken == "difficulty":
                mode["Difficulty"].pop()
            elif broken == "graph":
                mode["FloorPresets"][0]["NextNodeIds"] = [999]
            else:
                mode["Monsters"] = []
            self.fixture.write_source()
            self.owner.command("select", "--season-id", "43")
            with self.assertRaises(PacketError):
                self.challenge()
            self.assertFalse((self.root / run.STATE).exists())

    def test_map_entry_does_not_enable_unimplemented_loot_scores_shops_or_reward_routes(self):
        self.challenge()
        previous = (self.root / run.STATE).read_bytes()
        for route in (
            "choice-special-event",
            "buy-gacha",
            "infinitize",
            "claim-likeability-reward",
        ):
            with self.assertRaises(PacketError):
                self.call("/kamazonland/" + route, {})
        self.assertEqual((self.root / run.STATE).read_bytes(), previous)
        self.assert_untouched()
