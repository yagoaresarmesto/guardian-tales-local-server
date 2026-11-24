# SPDX-License-Identifier: Apache-2.0
"""Tetis floor, level and skill-tree rules shared by the game and web panel."""

import json
from bisect import bisect_right
from collections import Counter, defaultdict
from functools import lru_cache

from .raid_static import decode, records
from .village import integer


class TetisCatalog:
    def __init__(self, data, sweep_counter=None):
        self.data = data
        self.sweep_counter = sweep_counter
        self.seasons = {r["Id"]: r for r in data["Seasons"]}
        self.current = next((k for k, v in self.seasons.items() if v.get("Current")), None)
        self.floors = {i: {} for i in self.seasons}
        for row in data["Floors"]:
            self.floors[row["SeasonId"]][row["Floor"]] = row
        levels = sorted(data["RogueChessLevel"], key=lambda r: r["Level"])
        totals = [r["TotalExp"] for r in levels]
        if (
            not self.seasons
            or not levels
            or any(r["Level"] != i for i, r in enumerate(levels, 1))
            or any(a >= b for a, b in zip([0] + totals, totals))
        ):
            raise ValueError("Invalid Tetis season or experience catalog.")
        self.level_starts = [0] + totals[:-1]
        self.max_experience = totals[-1]
        self.max_points = data["Constants"]["MaxAbilityPoint"]
        self.level_per_point = data["Constants"]["LevelPerPoint"]
        if not integer(self.level_per_point, minimum=1):
            raise ValueError("Invalid Tetis skill point interval.")
        self.categories = {row["Id"]: row for row in data["AbilityCategories"]}
        self.nodes = {i: {} for i in self.seasons}
        self.parents = defaultdict(list)
        self.ability_names = {row["Id"]: row["Name"] for row in data["AbilitySpecs"]}
        self.spell_names = {row["Id"]: row["Name"] for row in data["SummonerSpells"]}
        for node in data["AbilityNodes"]:
            category = node["AbilityCategoryId"]
            ident = category * 10000 + node["NodeId"]
            season = self.categories[category]["SeasonId"]
            self.nodes[season][ident] = node
            for target in node.get("NextNodeIds") or []:
                self.parents[category * 10000 + target].append(ident)

    def level_for(self, experience):
        return bisect_right(self.level_starts, experience)

    def point_budget(self, experience):
        return min(self.level_for(experience) // self.level_per_point, self.max_points)

    def max_floor(self, season_id):
        limit = self.seasons[season_id]["SeasonLastStage"]
        if season_id != self.current:
            return min(limit, self.data["Constants"]["MaxFloor"])
        return limit

    def floor_spec(self, season_id, floor_num):
        if season_id not in self.seasons or not integer(
            floor_num, maximum=self.max_floor(season_id), minimum=1
        ):
            raise ValueError("Unknown Tetis season or floor.")
        floors = self.floors[season_id]
        if floor_num > len(floors):
            standard = self.data["Constants"]["MaxFloor"]
            cycle = len(floors) - standard
            floor_num = standard + 1 + (floor_num - standard - 1) % cycle if cycle > 0 else standard
        return floors[floor_num]

    @staticmethod
    def unpacked(abilities):
        return {value // 100: value % 100 for value in abilities}

    def validate_abilities(self, season_id, experience, abilities):
        """Validate a reachable allocation, then pack it the way the client saves it."""
        nodes = self.nodes[season_id]
        if not isinstance(abilities, dict) or len(abilities) > len(nodes):
            raise ValueError("Invalid Tetis skill allocation.")
        points = {}
        for key, value in abilities.items():
            if not str(key).isascii() or not str(key).isdecimal() or len(str(key)) > 8:
                raise ValueError("Unknown Tetis skill.")
            ident = int(key)
            if str(ident) != str(key) or ident not in nodes or ident in points:
                raise ValueError("Unknown or repeated Tetis skill.")
            if not integer(value, maximum=nodes[ident]["MaxPoints"]):
                raise ValueError(f"Invalid points for Tetis skill {ident}.")
            points[ident] = value
        if sum(points.values()) > self.point_budget(experience):
            raise ValueError("The Tetis skill allocation exceeds this level's point budget.")
        totals = Counter()
        for ident, value in points.items():
            totals[nodes[ident]["AbilityCategoryId"]] += value
        for ident, value in points.items():
            if not value:
                continue
            node = nodes[ident]
            category = self.categories[node["AbilityCategoryId"]]
            if any(totals[g["Id"]] < g["Amount"] for g in category["UnlockConditions"]):
                raise ValueError(f"Unlock the skill category before allocating to {ident}.")
            earlier_points = sum(
                p
                for n, p in points.items()
                if nodes[n]["AbilityCategoryId"] == category["Id"]
                and nodes[n]["Step"] < node["Step"]
            )
            if earlier_points < category["StepMinimumPoints"][node["Step"] - 1]:
                raise ValueError(
                    f"Invest more points in earlier tiers before allocating to {ident}."
                )
            if any(points.get(p, 0) < nodes[p]["MaxPoints"] for p in self.parents.get(ident, [])):
                raise ValueError(f"Complete the preceding skill before allocating to {ident}.")
        return sorted(ident * 100 + value for ident, value in points.items() if value)

    def describe_node(self, ident, node, points):
        category = self.categories[node["AbilityCategoryId"]]
        spell = node.get("SummonerSpellId")
        return {
            "id": ident,
            "name": self.spell_names[spell] if spell else self.ability_names[node["AbilityId"]],
            "category": category["Id"],
            "categoryName": category["AbilityCategoryTitle"],
            "step": node["Step"],
            "requiredPoints": category["StepMinimumPoints"][node["Step"] - 1],
            "requiredCategories": [
                {"id": row["Id"], "points": row["Amount"]} for row in category["UnlockConditions"]
            ],
            "requiresNodes": self.parents.get(ident, []),
            "maxPoints": node["MaxPoints"],
            "points": points.get(ident, 0),
        }


def catalog(tables):
    if "roguechess3" not in tables:
        raise ValueError("The supplied client data does not contain Tetis (roguechess3).")
    counters = json.loads(tables["counter"][1])["PlayCounter"] if "counter" in tables else []
    return TetisCatalog(
        json.loads(tables["roguechess3"][1]), next((r for r in counters if r["Id"] == 14), None)
    )


@lru_cache(maxsize=2)
def _catalog_from_file(path, modified, size):
    return catalog(records(decode(path.read_bytes()))[1])


def load_catalog(references):
    path = references.directory / "static_data_get.bin"
    stamp = path.stat()
    return _catalog_from_file(path, stamp.st_mtime_ns, stamp.st_size)
