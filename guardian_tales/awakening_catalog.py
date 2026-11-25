# SPDX-License-Identifier: Apache-2.0
"""Resolve the selected hero's awakening layout, gates, connections and stone prices."""

import json
from dataclasses import dataclass
from functools import lru_cache

from .raid_static import decode, records
from .village import integer


@dataclass(frozen=True)
class Node:
    rank: int
    breaks: int
    center: bool
    neighbors: frozenset
    gold: int
    stones: tuple


@dataclass(frozen=True)
class Tree:
    nodes: tuple
    circles: tuple
    edges: tuple

    def visible(self, rank, breaks):
        visible = {
            i for i, node in enumerate(self.nodes) if node.rank <= rank and node.breaks <= breaks
        }
        for circle in self.circles:
            if not circle <= visible:
                visible.difference_update(circle)
        for endpoints, path in self.edges:
            if not endpoints <= visible:
                visible.difference_update(path)
        return visible

    def unlock(self, indices, opened, rank, breaks):
        visible = self.visible(rank, breaks)
        if not set(indices) <= visible:
            raise ValueError("The selected nodes are unavailable on this hero's current tree")
        pending = dict.fromkeys(i for i in indices if i not in opened)
        # Auto Awakening can send a center and its surrounding nodes in the same batch.
        while pending:
            before = len(pending)
            for i in tuple(pending):
                node = self.nodes[i]
                if 1 <= i <= 6 and opened.isdisjoint(range(1, 7)):
                    allowed = True
                elif node.center:
                    allowed = node.neighbors <= opened
                else:
                    allowed = not node.neighbors.isdisjoint(opened)
                if allowed:
                    opened.add(i)
                    del pending[i]
            if len(pending) == before:
                raise ValueError("Open the connected awakening nodes first")


def build_tree(config, packed_nodes, layout, drawing, prices):
    if not 1 <= len(packed_nodes) <= 1000 or len(layout) != len(packed_nodes):
        raise ValueError("Invalid awakening layout")
    special = iter(config["SpecialNodes"])
    nodes = []
    for index, (packed, slot) in enumerate(zip(packed_nodes, layout)):
        # The five trailing decimal digits encode rank, limit breaks and a three-digit index.
        if packed % 1000 != index or slot["NodeIndex"] != index:
            raise ValueError("Invalid awakening node index")
        resource = packed // 100_000
        origin = None
        if packed // 1_000_000_000 == 2:
            resource += next(special)
            origin = config["OriginId"]
        price = prices.get((origin, resource)) or prices.get((None, resource))
        if price is None:
            raise ValueError("Missing awakening price for this hero")
        nodes.append(
            Node(
                packed // 10_000 % 10,
                packed // 1000 % 10,
                slot["NodeType"] == 2,
                frozenset(slot["ConnectedNodes"]),
                *price,
            )
        )
    circles = tuple(frozenset(c["AttachedNodes"]) for c in drawing["Circles"])
    edges = tuple(
        (frozenset(e["ConnectedNodes"]), frozenset(e["ContainedEdgeNodes"]))
        for e in drawing["Edges"]
    )
    return Tree(tuple(nodes), circles, edges)


@lru_cache(maxsize=2)
def catalog(body):
    tables = records(decode(body))[1]

    def read(name):
        return json.loads(tables[name][1])

    try:
        prices = {}
        for row in read("awakeningnodedata")["ResourcesToOpenNode"]:
            key = (row.get("OriginId"), row["Id"])
            gold = row["Gold"]
            stones = []
            for i in range(1, 5):
                item, amount = row[f"Item{i}"], row[f"Item{i}Amount"]
                if not integer(amount) or (amount and not integer(item, minimum=1)):
                    raise ValueError("Invalid awakening material cost")
                if amount:
                    stones.append((item, amount))
            if key in prices or not integer(gold):
                raise ValueError("Invalid awakening node price")
            prices[key] = (gold, tuple(stones))
        layouts, drawings, definitions = (
            read("awakeningnodelayout"),
            read("awakeningnodelayout_client"),
            read("awakeningtreenodes"),
        )
        trees = {}
        for config in read("charactertreeconfig"):
            name = config["TreeLayoutName"]
            trees[config["OriginId"]] = build_tree(
                config,
                definitions[config["AwakeningTreeName"]],
                layouts[name],
                drawings[name],
                prices,
            )
        heroes = {
            h["Id"]: (trees[h["OriginId"]], h["Rank"])
            for h in read("heroes")
            if h.get("Playable") is True and h["OriginId"] in trees
        }
        discount = read("constants")["AccountBuffValue"]["AwakeningDc"]
        if type(discount) not in (int, float) or not 0 <= discount <= 1:
            raise ValueError("Invalid awakening gold discount")
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid hero awakening catalog") from exc
    return heroes, discount
