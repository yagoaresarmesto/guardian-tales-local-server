# SPDX-License-Identifier: Apache-2.0
"""Regular Kama-ZONE routes against an explicitly supplied external content pack."""

import os
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from guardian_tales.content.reference import ReferenceData
from guardian_tales.modes.kamazone import (
    kamazone,
    kamazone_battle,
    kamazone_events,
    kamazone_run,
    kamazone_shelter,
    kamazone_shop,
)


@unittest.skipUnless(os.environ.get("GT_KAMAZONE_TEST_STATIC"), "requires matching EU static data")
class RegularChallengePlaythrough(unittest.TestCase):
    def test_all_regular_seasons_difficulties_and_floors(self):
        source = Path(os.environ["GT_KAMAZONE_TEST_STATIC"]).read_bytes()
        party = [1, 2, 3, 4]
        profile = {"User": {"Id": 1, "Characters": [{"Id": ident} for ident in party]}}
        seasons = sorted(kamazone.catalog(source))
        self.assertEqual(seasons, [41, 42, 43])
        visits = Counter()
        for season in seasons:
            for difficulty in (1, 2, 3):
                with (
                    self.subTest(season=season, difficulty=difficulty),
                    tempfile.TemporaryDirectory() as root,
                ):
                    refs = ReferenceData(root)
                    account = SimpleNamespace(references=refs, profile=lambda: profile)
                    sequence = 0

                    def call(route, body):
                        nonlocal sequence
                        sequence += 1
                        kamazone_run.handle(account, source, season, route, body, str(sequence))
                        return kamazone_run.load(refs)

                    seed = season * 100 + difficulty
                    rng = random.Random(seed)
                    with patch.object(kamazone_run.secrets, "randbits", return_value=seed):
                        state = call(kamazone_run.CHALLENGE, {"Difficulty": difficulty})
                    call(kamazone_run.SELECT, {"CharacterIds": party})
                    for floor in range(1, 9):
                        catalog = kamazone_run.catalog(source, season, floor)
                        nodes = {
                            n["Id"]: n
                            for n in kamazone_run.floor_nodes(source, season, seed, floor)
                        }
                        self.assertEqual(
                            (state["floor"], state["current_node_id"]), (floor, catalog["starting"])
                        )
                        visits["Starting"] += 1
                        while True:
                            ident = rng.choice(
                                catalog["nodes"][state["current_node_id"]]["NextNodeIds"]
                            )
                            node = nodes[ident]
                            state = call(kamazone_run.START, {"NodeId": ident})
                            kind = node["Type"]
                            visits[kind] += 1
                            if kind in kamazone_run.COMBAT:
                                call(
                                    kamazone_run.BATTLE,
                                    dict(NodeId=ident, Formation=[0, 7, 14, 24]),
                                )
                                state = call(
                                    kamazone_battle.END,
                                    dict(
                                        NodeId=ident,
                                        Result=1,
                                        CharacterHps={str(i): 10000 for i in party},
                                        MonsterHps=[0] * len(node["BattleMonsters"]),
                                    ),
                                )
                                self.assertTrue(state["battle_loot"])
                                state = call(
                                    kamazone_battle.CLOSE,
                                    dict(
                                        NodeId=ident,
                                        LootArtifactId=state["battle_loot"][0],
                                        DiscardArtifactIndex=(
                                            0 if len(state["artifacts"]) == 8 else None
                                        ),
                                    ),
                                )
                            elif kind == "Shelter":
                                state = call(
                                    kamazone_shelter.TAKE, dict(NodeId=ident, ChoiceType=1)
                                )
                            elif kind == "Shop":
                                state = call(kamazone_shop.CLOSE, dict(NodeId=ident))
                            else:
                                self.assertEqual(kind, "Special")
                                choice = state["events"][str(ident)]["choices"][0]
                                call(kamazone_events.CHOOSE, dict(NodeId=ident, ChoiceId=choice))
                                state = call(kamazone_run.START, dict(NodeId=ident))
                                self.assertEqual(state["states"][str(ident)], 9)
                                state = call(kamazone_events.CLOSE, dict(NodeId=ident))
                            if kind == "Boss":
                                break
                    ended = call(kamazone_run.CONCLUDE, {"keepingArtifactId": None})
                    self.assertFalse(ended["active"])
        self.assertEqual(set(visits), set(kamazone_run.NODE_TYPES))
        self.assertEqual(visits["Boss"], 72)
