# SPDX-License-Identifier: Apache-2.0
"""Account material balances exposed by the installed game catalog."""

import json
import re
from collections import defaultdict

DEFAULT_ITEM_LIMIT = 100_000
ITEM_LIMITS = {"experience": 1_000_000_000, "jewel_powder": 1_000_000_000}
HERO_STONES = {
    "HeroEvolve": ("Hero Evolution Stones", "evolve_stone_", "Evolution Stone"),
    "HeroMyth": ("Hero Myth Stones", "myth_stone_", "Myth Stone"),
}
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


def item_balance_limit(spec):
    limit = ITEM_LIMITS.get(spec.get("Name"), DEFAULT_ITEM_LIMIT)
    return min(spec.get("MaxCount", limit), limit)


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
            if not hero.get("Playable"):
                continue
            for stone in (hero.get("EvolvingStoneId"), hero.get("MythStoneId")):
                if stone:
                    heroes_by_stone[stone].add(hero.get("OriginId") or hero["Id"])
    materials = []
    evolution_choices = defaultdict(list)
    for ident, spec in catalog.specs.items():
        name = spec.get("Name", "")
        group = choice = None
        extra = {}
        stone_type = spec.get("StoneType")
        if spec.get("Type") == "evolve_stone" and stone_type in HERO_STONES:
            group, prefix, suffix = HERO_STONES[stone_type]
            fallback = name.removeprefix(prefix).replace("_", " ").title()
            label = catalog.names.get(ident) or f"{fallback} {suffix}"
            origins = heroes_by_stone.get(ident, ())
            names = catalog.equipment.hero_names
            hero_names = sorted({names[origin] for origin in origins if origin in names})
            choice = " / ".join(hero_names) or label.removesuffix(" " + suffix)
            if stone_type == "HeroEvolve":
                extra = dict(catalogOnly=not origins)
                if len(origins) > 1:
                    choice = label
                    extra["searchAliases"] = hero_names
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
                limit=item_balance_limit(spec),
                **extra,
            )
        )
        if group == HERO_STONES["HeroEvolve"][0]:
            evolution_choices[choice].append(materials[-1])
    # Alternate versions can share a short hero name but use different stones.
    for variants in evolution_choices.values():
        if len(variants) > 1:
            for item in variants:
                item.setdefault("searchAliases", []).append(item["choice"])
                item["choice"] = item["label"].removesuffix(" Evolution Stone")
    return materials
