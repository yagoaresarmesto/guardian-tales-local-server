# SPDX-License-Identifier: Apache-2.0
"""Account material balances exposed by the installed game catalog."""

import json
import re
from collections import defaultdict

MATERIAL_LIMIT = 100_000
GOODS = {
    "jewel_powder": "Jewel Powder",
    "herocrystal": "Hero Crystal",
    "magicmetal": "Magic Metal",
    "battle_medal": "Battle Medal",
    "coop_expedition_help_coin": "Sprout Knight Coin",
    "experience": "Experience",
    "dream_mythstone": "Dream Myth Stone",
    "dream_spiritstone": "Dream Evolution Stone",
    "starpiece": "Star Piece",
}


def season_choices(tables):
    choices = {}
    preferred = set()
    if "roguechess3" in tables:
        for row in json.loads(tables["roguechess3"][1]).get("Seasons", []):
            if "SeasonCoin" in row:
                choices[row["SeasonCoin"]] = f"Season {row['Id']}"
                if row.get("Current"):
                    preferred.add(row["SeasonCoin"])
    if "coopexpedition" in tables:
        latest = {}
        for row in json.loads(tables["coopexpedition"][1]).get("Seasons", []):
            coin = row.get("SeasonCoin", {}).get("KakaoGlobal")
            if row.get("IsEventSeason") or not coin:
                continue
            chapter = row.get("SeasonChapter", {}).get("KakaoGlobal")
            choices[coin] = f"Chapter {chapter}" if chapter else f"Season {row['SeasonId']}"
            latest[row["SeasonId"]] = coin
        if latest:
            preferred.add(latest[max(latest)])
    return choices, preferred


def account_materials(catalog, tables):
    seasons, preferred = season_choices(tables)
    heroes_by_stone = defaultdict(set)
    if "heroes" in tables:
        for hero in json.loads(tables["heroes"][1]):
            hero_name = catalog.equipment.hero_names.get(hero["Id"])
            if hero.get("Playable") and hero.get("MythStoneId") and hero_name:
                heroes_by_stone[hero["MythStoneId"]].add(hero_name)
    materials = []
    for ident, spec in catalog.specs.items():
        name = spec.get("Name", "")
        group = choice = None
        if spec.get("Type") == "evolve_stone" and spec.get("StoneType") == "HeroMyth":
            group = "Hero Myth Stones"
            fallback = name.removeprefix("myth_stone_").replace("_", " ").title()
            label = catalog.names.get(ident) or f"{fallback} Myth Stone"
            choice = " / ".join(sorted(heroes_by_stone[ident])) or label.removesuffix(" Myth Stone")
        elif spec.get("Type") != "goods":
            continue
        elif name in GOODS:
            label = GOODS[name]
        elif match := re.fullmatch(r"purple_coin_([1-9][0-9]*)", name):
            group, choice = "Purple Coins", f"World {int(match[1])}"
            label = f"{group} · {choice}"
        elif re.fullmatch(r"coop_expedition_coin_\d+(?:_\d+)?", name):
            group = "Co-op Expedition Coins"
            choice = seasons.get(ident, f"Coin #{ident}")
            label = f"{group} · {choice}"
        elif re.fullmatch(r"ic_rogue_chess_coin_\d+(?:_\d+)?", name):
            group = "Tetis Hero Coins"
            choice = seasons.get(ident, f"Coin #{ident}")
            label = f"{group} · {choice}"
        else:
            continue
        materials.append(
            dict(
                key=f"material-{ident}",
                id=ident,
                label=label,
                group=group,
                choice=choice,
                preferred=ident in preferred,
                limit=min(spec.get("MaxCount", MATERIAL_LIMIT), MATERIAL_LIMIT),
            )
        )
    return materials
