# SPDX-License-Identifier: Apache-2.0
"""Battle artifact choices and transactional progression between regular floors."""

import json
import unittest
from unittest.mock import patch

from guardian_tales import kamazone_battle as battle
from guardian_tales import kamazone_run as run
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.protocol import PacketError
from tests.account.test_snapshots import request
from tests.content import test_kamazone_run as fixtures


class KamazoneLootTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazoneRunTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
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
        mode["Constants"]["ShelterHpRecover"] = 0.4
        mode["Artifacts"] = [
            dict(Id=i, Kind="Curse" if i == 16 else "Normal", Rarity=i % 3, Lootable=i != 15)
            for i in range(11, 17)
        ]
        mode["Artifacts"][0].update(EffectType="CoinBonus", EffectValue=[10])
        mode["Artifacts"][-1].update(EffectType="LoseCoinNodeClear", EffectValue=[10])
        mode["Benefits"].append(
            dict(
                Id=23,
                MaxLevel=2,
                OpenType="None",
                Points=[50, 50],
                EffectType="CoinBonusBattle",
                EffectValue1=[0, 40, 80],
                EffectValue2=[0, 50, 90],
            )
        )
        for season in mode["Seasons"]:
            season["Benefits"].append(23)
            season["ArtifactsCurse"] = [16]
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
        self.packet = json.loads(reply.body)
        return self.packet["UserKamazonLand"]

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
        self.assertEqual(user["SilverCoin"], 0)
        first = self.call(battle.CLOSE, dict(NodeId=110, LootArtifactId=11))
        self.assertEqual((self.packet["AddedSilverCoin"], first["SilverCoin"]), (10, 10))
        self.assertEqual([a["Id"] for a in first["Artifacts"]], [11])
        self.assertEqual(next(n for n in first["Nodes"] if n["Id"] == 110)["State"], 11)
        self.assertEqual(self.reopen(), first)
        boss = self.fight(120)
        loot = dict(NodeId=120, LootArtifactId=boss["LootArtifacts"][0][0])
        with patch("guardian_tales.kamazone_run.atomic_write", side_effect=OSError("unavailable")):
            self.reject(battle.CLOSE, loot)
        current = self.call(battle.CLOSE, loot, 701)
        self.assertEqual(
            current["Progress"],
            dict(
                Floor=2,
                CurrentNodeId=200,
                Concluded=False,
                Battle=2,
                KeepingArtifactId=None,
                CanPickArtifactAid=False,
                CanPickCurseAid=False,
            ),
        )
        self.assertEqual({n["Id"] for n in current["Nodes"]}, {200, 210, 211, 220})
        self.assertEqual(current["Hps"], first["Hps"])
        self.assertEqual(current["Formation"], first["Formation"])
        self.assertEqual(current["Characters"], first["Characters"])
        self.assertEqual([a["Id"] for a in current["Artifacts"]], [11, loot["LootArtifactId"]])
        self.assertEqual(self.reopen(), current)
        self.assertEqual(current["SilverCoin"], 50)
        self.assertEqual(self.call(battle.CLOSE, loot, 701), current)
        self.assertEqual(self.packet["AddedSilverCoin"], 40)
        self.assertEqual(self.call(battle.CLOSE, loot), current)
        self.assertEqual(self.packet["AddedSilverCoin"], 40)
        self.reject(battle.CLOSE, dict(NodeId=120))
        self.reject(run.START, dict(NodeId=110))
        self.assertEqual(self.fight(211)["Type"], "Elite")
        self.assertEqual(list(self.owner.db.iterdump()), self.db_dump)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.owner.root.iterdir() if p != self.path},
            self.references,
        )

    def test_empty_boss_offer_pays_and_advances_even_if_the_client_skips_close(self):
        self.fight(110)
        self.call(battle.CLOSE, dict(NodeId=110))
        with patch("guardian_tales.kamazone_loot.offer", return_value=[]):
            self.call(run.START, {"NodeId": 120})
            user = self.call(run.BATTLE, dict(NodeId=120, Formation=[12, 3, 19, 9]))
            boss = next(row for row in user["Nodes"] if row["Id"] == 120)
            user = self.call(
                battle.END,
                dict(
                    NodeId=120,
                    Result=1,
                    CharacterHps={},
                    MonsterHps=[0] * len(boss["BattleMonsters"]),
                ),
            )
            self.assertEqual((user["Progress"]["Floor"], user["SilverCoin"]), (2, 40))
            self.assertEqual(self.call(battle.CLOSE, dict(NodeId=120)), user)
            self.assertEqual(self.packet["AddedSilverCoin"], 30)

    def test_selected_bounty_level_adds_the_matching_tier_bonus_once(self):
        self.owner.owner.save({"23": 2})
        self.fight(111)
        user = self.call(battle.CLOSE, dict(NodeId=111))
        self.assertEqual((self.packet["AddedSilverCoin"], user["SilverCoin"]), (70, 70))
        self.fight(120)
        user = self.call(battle.CLOSE, dict(NodeId=120))
        self.assertEqual((self.packet["AddedSilverCoin"], user["SilverCoin"]), (120, 190))
        self.assertEqual(self.reopen(), user)

    def test_elite_offer_allows_declining_full_inventory_or_replacing_only_the_selected_slot(self):
        self.fight(111)
        value = json.loads(self.path.read_bytes())
        value["artifacts"] = [
            dict(Id=11, Battle=2, Shelter=0, EliminateArtifact=0) for _ in range(8)
        ]
        value["curses"] = [16]
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
        self.assertEqual((self.packet["AddedSilverCoin"], replaced["SilverCoin"]), (100, 90))
        self.path.write_bytes(saved)
        declined = self.call(battle.CLOSE, dict(NodeId=111))
        self.assertEqual(declined["Artifacts"], value["artifacts"])
        self.assertEqual(declined["SilverCoin"], 90)
        self.reject(battle.CLOSE, dict(NodeId=111, LootArtifactId=11, DiscardArtifactIndex=0))

    def test_defeat_and_timeout_offer_nothing_and_cannot_claim_a_victory(self):
        for result in (3, 4):
            lost = self.fight(110, result)
            self.assertEqual(lost["LootArtifacts"], [])
            self.reject(battle.CLOSE, dict(NodeId=110, LootArtifactId=11))
            self.assertEqual(self.call(battle.CLOSE, dict(NodeId=110))["SilverCoin"], 0)
            self.assertNotIn("AddedSilverCoin", self.packet)
            self.reject(run.START, dict(NodeId=120))
        self.assertTrue(self.fight(110)["LootArtifacts"])

    def test_old_active_completed_boss_can_claim_on_reopen_without_refighting(self):
        self.fight(110)
        self.call(battle.CLOSE, dict(NodeId=110))
        self.fight(120)
        state = json.loads(self.path.read_bytes())
        state.update(stage_started=False, pending_result=None)
        state["states"]["120"] = 11
        for key in ("floor", "battle_loot", "last_loot_close", "last_battle_silver"):
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
