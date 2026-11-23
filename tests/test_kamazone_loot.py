# SPDX-License-Identifier: Apache-2.0
"""Battle artifact choices and transactional progression between regular floors."""

import json
import unittest
from unittest.mock import patch

from guardian_tales import kamazone_battle as battle
from guardian_tales import kamazone_run as run
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.protocol import PacketError
from tests import test_kamazone_run as fixtures
from tests.test_snapshots import request


class KamazoneLootTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazoneRunTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.owner.owner.practice("disable")
        self.session = self.owner.session
        mode = self.owner.fixture.tables["kamazonland2"]
        for season in mode["Seasons"]:
            season.update(
                Floors=[1, 2],
                Artifacts=[11, 12, 13, 14, 15, 16],
                ArtifactsException=[14],
                SpecialEvents=[],
            )
        mode.update(
            SpecialEvents=[],
            SpecialEventChoices=[],
            Constants={"BattleLootWeights" + kind: [1, 2, 3, 1] for kind in run.COMBAT},
        )
        mode["Artifacts"] = [
            dict(Id=i, Kind="Curse" if i == 16 else "Normal", Rarity=i % 3, Lootable=i != 15)
            for i in range(11, 17)
        ]
        for row in mode["FloorPresets"]:
            if row["Step"] == 1:
                for kind in run.PROBABILITIES:
                    row[kind + "Prob"] = int(kind == ("Normal" if row["Id"] == 110 else "Elite"))
        mode["FloorPresets"] += [
            dict(
                row,
                Id=100 + row["Id"],
                FloorId=2,
                NextNodeIds=[i + 100 for i in row["NextNodeIds"]] if row["NextNodeIds"] else None,
            )
            for row in mode["FloorPresets"]
        ]
        mode["Difficulty"] += [dict(row, Floor=2) for row in mode["Difficulty"]]
        self.owner.fixture.write_source()
        self.owner.owner.command("select", "--season-id", "43")
        self.sequence = 14000
        self.path = self.owner.root / run.STATE
        self.db_dump = list(self.owner.db.iterdump())
        self.references = {p.name: p.read_bytes() for p in self.owner.root.iterdir()}
        self.call(run.CHALLENGE, {"Difficulty": 3})
        self.call(run.SELECT, {"CharacterIds": self.owner.characters})

    def call(self, route, body, sequence=None):
        self.sequence += 1
        packet = request(route, body)
        packet["sequence_id"] = self.sequence if sequence is None else sequence
        reply = self.session.handle(packet)
        return json.loads(reply.body)["UserKamazonLand"]

    def reopen(self):
        epoch = self.session.request_epoch
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.session.request_epoch = epoch
        return self.call("/kamazonland/enter", {"IsPartial": False})

    def fight(self, node, result=1):
        self.call(run.START, {"NodeId": node})
        user = self.call(run.BATTLE, dict(NodeId=node, Formation=[12, 3, 19, 9]))
        foes = next(n["BattleMonsters"] for n in user["Nodes"] if n["Id"] == node)
        self.outcome = dict(
            NodeId=node,
            Result=result,
            CharacterHps={str(i): 9000 for i in self.owner.characters},
            MonsterHps=[0 if result == 1 else 2500] * len(foes),
        )
        user = self.call(battle.END, self.outcome)
        return next(n for n in user["Nodes"] if n["Id"] == node)

    def reject(self, route, body):
        before = self.path.read_bytes()
        with self.assertRaises(PacketError):
            self.call(route, body)
        self.assertEqual(self.path.read_bytes(), before)

    def test_normal_and_boss_choices_advance_once_and_preserve_the_party_and_inventory(self):
        normal = self.fight(110)
        self.assertEqual(normal["State"], 5)
        (choices,) = normal["LootArtifacts"]
        self.assertEqual(set(choices), {11, 12, 13})
        user = self.reopen()
        self.assertEqual(user["Artifacts"], [])
        self.assertEqual(normal, next(n for n in user["Nodes"] if n["Id"] == 110))
        self.assertEqual(self.call(battle.END, self.outcome), user)
        self.reject(run.START, {"NodeId": 120})
        for item in (14, 15, 16, 999, True):
            self.reject(battle.CLOSE, dict(NodeId=110, LootArtifactId=item))
        self.reject(
            battle.CLOSE, dict(NodeId=110, LootArtifactId=choices[0], DiscardArtifactIndex=0)
        )
        first = self.call(battle.CLOSE, dict(NodeId=110, LootArtifactId=choices[0]))
        self.assertEqual([a["Id"] for a in first["Artifacts"]], choices[:1])
        self.assertEqual(next(n for n in first["Nodes"] if n["Id"] == 110)["State"], 11)
        self.assertEqual(self.reopen(), first)
        boss = self.fight(120)
        loot = dict(NodeId=120, LootArtifactId=boss["LootArtifacts"][0][0])
        with patch("guardian_tales.kamazone_run.atomic_write", side_effect=OSError("unavailable")):
            self.reject(battle.CLOSE, loot)
        current = self.call(battle.CLOSE, loot, 701)
        self.assertEqual(
            current["Progress"], dict(Floor=2, CurrentNodeId=200, Concluded=False, Battle=2)
        )
        self.assertEqual({n["Id"] for n in current["Nodes"]}, {200, 210, 211, 220})
        self.assertEqual(current["Hps"], first["Hps"])
        self.assertEqual(current["Formation"], first["Formation"])
        self.assertEqual(current["Characters"], first["Characters"])
        self.assertEqual(
            [a["Id"] for a in current["Artifacts"]], [choices[0], loot["LootArtifactId"]]
        )
        self.assertEqual(self.reopen(), current)
        self.assertEqual(self.call(battle.CLOSE, loot, 701), current)
        self.assertEqual(self.call(battle.CLOSE, loot), current)
        self.reject(battle.CLOSE, dict(NodeId=120))
        self.reject(run.START, dict(NodeId=110))
        self.assertEqual(self.fight(211)["Type"], "Elite")
        self.assertEqual(list(self.owner.db.iterdump()), self.db_dump)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.owner.root.iterdir() if p != self.path},
            self.references,
        )

    def test_elite_offer_allows_declining_full_inventory_or_replacing_only_the_selected_slot(self):
        self.fight(111)
        value = json.loads(self.path.read_bytes())
        value["artifacts"] = [
            dict(Id=11, Battle=2, Shelter=0, EliminateArtifact=0) for _ in range(8)
        ]
        self.path.write_text(json.dumps(value))
        saved = self.path.read_bytes()
        for index in (None, -1, 8, True):
            self.reject(
                battle.CLOSE, dict(NodeId=111, LootArtifactId=13, DiscardArtifactIndex=index)
            )
        self.reject(battle.CLOSE, dict(NodeId=111, DiscardArtifactIndex=0))
        replaced = self.call(
            battle.CLOSE, dict(NodeId=111, LootArtifactId=13, DiscardArtifactIndex=0)
        )
        self.assertEqual([a["Id"] for a in replaced["Artifacts"]], [13] + [11] * 7)
        self.path.write_bytes(saved)
        declined = self.call(battle.CLOSE, dict(NodeId=111))
        self.assertEqual(declined["Artifacts"], value["artifacts"])
        self.reject(battle.CLOSE, dict(NodeId=111, LootArtifactId=11, DiscardArtifactIndex=0))

    def test_defeat_and_timeout_offer_nothing_and_cannot_claim_a_victory(self):
        for result in (3, 4):
            lost = self.fight(110, result)
            self.assertEqual(lost["LootArtifacts"], [])
            self.reject(battle.CLOSE, dict(NodeId=110, LootArtifactId=11))
            self.call(battle.CLOSE, dict(NodeId=110))
            self.reject(run.START, dict(NodeId=120))
        self.assertTrue(self.fight(110)["LootArtifacts"])

    def test_old_active_completed_boss_can_claim_on_reopen_without_refighting(self):
        self.fight(110)
        self.call(battle.CLOSE, dict(NodeId=110))
        self.fight(120)
        state = json.loads(self.path.read_bytes())
        state.update(stage_started=False, pending_result=None)
        state["states"]["120"] = 11
        for key in ("floor", "battle_loot", "last_loot_close"):
            state.pop(key)
        self.path.write_text(json.dumps(state))
        before = self.path.read_bytes()
        user = self.reopen()
        node = next(n for n in user["Nodes"] if n["Id"] == 120)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(node["State"], 5)
        new = self.call(battle.CLOSE, dict(NodeId=120, LootArtifactId=node["LootArtifacts"][0][0]))
        self.assertEqual((new["Progress"]["Floor"], new["Progress"]["Battle"]), (2, 2))
        self.assertEqual(len(new["Artifacts"]), 1)
