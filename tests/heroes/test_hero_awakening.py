# SPDX-License-Identifier: Apache-2.0
"""Selected nodes, individual hero trees and payments persist in one transaction."""

import base64
import copy
import json
import sqlite3
import struct
import unittest

from guardian_tales.heroes.characters import new_character
from guardian_tales.heroes.hero_awakening import ROUTE
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import GOLD
from tests.village.test_village_harvest import VillageFixture


class HeroAwakeningTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        links = [
            [1, 2, 3, 4, 5, 6],
            [0, 2, 6],
            [0, 1, 3],
            [0, 2, 4],
            [0, 3, 5],
            [0, 4, 6],
            [0, 5, 1, 7],
            [6, 8],
            [7, 9],
            [8],
        ]

        def cost(key, gold, stone, count, origin=None):
            row = {"Id": key, "Gold": gold, "Item1": stone, "Item1Amount": count}
            for i in (2, 3, 4):
                row.update({f"Item{i}": -1, f"Item{i}Amount": 0})
            if origin:
                row["OriginId"] = origin
            return row

        def tree(resource):
            return [2000000000] + [
                resource * 100000 + i + (61000 if i == 9 else 0) for i in range(1, 10)
            ]

        self.tables = {
            "heroes": [
                dict(Id=spec, OriginId=origin, Rank=rank, Playable=True)
                for spec, origin, rank in ((11, 10, 6), (12, 10, 4), (21, 20, 4))
            ],
            "charactertreeconfig": [
                dict(
                    OriginId=o, TreeLayoutName="layout", AwakeningTreeName=name, SpecialNodes=[990]
                )
                for o, name in ((10, "a"), (20, "b"))
            ],
            "awakeningtreenodes": {"a": tree(10901), "b": tree(10902)},
            "awakeningnodelayout": {
                "layout": [
                    dict(NodeIndex=i, NodeType=(2 if i == 0 else 1), ConnectedNodes=adj)
                    for i, adj in enumerate(links)
                ]
            },
            "awakeningnodelayout_client": {
                "layout": {
                    "Circles": [{"AttachedNodes": list(range(7))}, {"AttachedNodes": [8, 9]}],
                    "Edges": [{"ConnectedNodes": [6, 8], "ContainedEdgeNodes": [7]}],
                }
            },
            "awakeningnodedata": {
                "ResourcesToOpenNode": [
                    cost(10901, 10, 70, 2),
                    cost(10902, 25, 71, 1),
                    cost(20990, 100, 72, 3),
                    cost(20990, 83, 72, 1, 10),
                ]
            },
            "constants": {"AccountBuffValue": {"AwakeningDc": 0.3}},
        }
        text = ""
        for key, table in self.tables.items():
            value = json.dumps(table)
            text += f"{key}\n{value}\n1\n{digest(value.encode())}\n"
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(compress(text.encode()))
        self.profile = self.store.account.profile()
        user = self.profile["User"]
        user["Characters"] = [
            dict(new_character(i, spec), LimitBreaks=1) for i, spec in enumerate((11, 12, 21), 1)
        ]
        user["TrainingSlots"] = {}
        user["Assets"] = [dict(Id=GOLD, Amount=700, Spent=-120)]
        user["ItemStackables"] = [
            dict(Id=i, ItemId=stone, Amount=amount)
            for i, (stone, amount) in enumerate(((70, 1), (70, 99), (71, 50), (72, 10)), 1)
        ]
        user["Options"] = {"AccountBuffs": {}}
        self.save_profile(self.profile)

    def awaken(self, indices, who=1, seq=51, discount=False):
        return self.call(
            dict(CharacterId=who, NodeIndices=indices, discountBuff=discount), ROUTE, sequence=seq
        )["User"]

    def test_single_then_auto_preserve_prefix_spending_other_hero_and_retry(self):
        user = self.profile["User"]
        # Saved masks may be short and retain a previous form in the prefix.
        prefix = base64.b64encode(struct.pack("<I", 10)).decode()
        user["Characters"][0]["AwakeningTree"] = prefix + "|AA=="
        self.save_profile(self.profile)
        after = self.awaken([3])
        self.assertEqual(set(after), {"Id", "Cas", "Characters", "Assets", "ItemStackables"})
        self.assertEqual(after["Characters"][0]["AwakeningTree"], prefix + "|CAA=")
        self.assertEqual(after["Assets"][0], dict(Id=GOLD, Amount=690, Spent=-110))
        self.assertEqual(after["ItemStackables"][0]["Amount"], 98)
        batch = [0, 9, 8, 7, 1, 6, 2, 4, 5, 3]
        after = self.awaken(batch, seq=52)
        self.assertEqual(after["Characters"][0]["AwakeningTree"], prefix + "|/wM=")
        self.assertEqual(after["Characters"][0]["AwakeningTreeGold"], 173)
        self.assertEqual(after["Assets"][0], dict(Id=GOLD, Amount=527, Spent=53))
        self.assertEqual([i["Amount"] for i in after["ItemStackables"]], [82, 50, 9])
        self.assertEqual(after["Characters"][1:], user["Characters"][1:])
        self.assertEqual(after["Cas"], user["Cas"] + 2)
        self.assertEqual(self.awaken([1, 3], seq=53), after)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(reconnect=True)
        self.static.unlink()
        self.assertEqual(self.awaken(batch[::-1], seq=52), after)
        self.assertEqual(self.awaken([3]), after)
        for indices, who in (([4], 1), ([3], 2)):
            with self.assertRaises(PacketError):
                self.awaken(indices, who)

    def test_same_index_uses_selected_tree_and_account_discount_only_on_gold(self):
        self.profile["User"]["Options"]["AccountBuffs"]["AwakeningDc"] = "2999-01-01T00:00:00+00:00"
        self.save_profile(self.profile)
        after = self.awaken([1, 2, 3, 4, 5, 6, 0], 3, discount=True)
        self.assertEqual(after["Characters"][2]["AwakeningTreeGold"], 6 * round(25 * 0.7) + 70)
        self.assertEqual([r["Amount"] for r in after["ItemStackables"]], [1, 99, 44, 7])
        self.assertEqual(after["Characters"][0], self.profile["User"]["Characters"][0])

    def test_visibility_connection_and_material_guards_are_atomic(self):
        for who, indices in (
            (1, [0]),
            (1, [1, 3]),
            (2, [7]),
            (2, [9]),
            (1, [10]),
            (1, [1, 1]),
            (1, [True]),
        ):
            with self.assertRaises(PacketError):
                self.awaken(indices, who)
            self.assertEqual(self.store.account.profile(), self.profile)
        with self.assertRaises(PacketError):
            self.awaken([1], discount=True)
        for change in (
            lambda u: u["Characters"][0].update(LimitBreaks=0),
            lambda u: u.update(TrainingSlots={"1": {"CharacterId": 1, "IsAwakening": True}}),
            lambda u: u["ItemStackables"][-1].update(Amount=0),
            lambda u: u["Assets"][0].update(Amount=10),
        ):
            profile = copy.deepcopy(self.profile)
            change(profile["User"])
            self.save_profile(profile)
            with self.assertRaises(PacketError):
                self.awaken(list(range(10)))
            self.assertEqual(self.store.account.profile(), profile)

    def test_failed_receipt_rolls_back_all_selected_nodes(self):
        self.db.execute(
            "CREATE TRIGGER reject_nodes BEFORE INSERT ON hero_awakening_requests BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.awaken([5, 6, 7])
        self.assertEqual(self.store.account.profile(), self.profile)
