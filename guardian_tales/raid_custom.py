# SPDX-License-Identifier: Apache-2.0
"""Build a local Raid boss set from the pinned client's encounters."""

import json
from itertools import count

from .assets import ResourceLibrary

BOSS_STAGES = {
    "altered mad panda mk-3": 810010021,
    "ancient demon": 810010007,
    "arachne": 810010033,
    "carmen": 810010032,
    "cyborg erina": 810010005,
    "empire knight": 810010029,
    "fairy": 810010012,
    "founder elphaba": 810010018,
    "furious desert bull worm": 810010027,
    "furious minotaur": 810010016,
    "goblin chief": 810010010,
    "grand admiral marina": 810010019,
    "invader commander": 810010008,
    "invader director": 810010028,
    "invader terrorist": 810010030,
    "lava slime king": 810010001,
    "little jerry volt": 810010031,
    "minister duncan": 810010025,
    "nine-tailed fox garam": 810010024,
    "returned harvester": 810010026,
    "sandmonster": 810010002,
    "shadow beast": 810010006,
    "snowman general gast": 810010014,
    "viper clan leader": 810010004,
}
# UI label, character enum, and suffix in the stock Raid v2 monster names.
ELEMENTS = {
    "basic": ("None", "none"),
    "dark": ("Darkness", "dark"),
    "earth": ("Earth", "earth"),
    "fire": ("Fire", "fire"),
    "light": ("Light", "light"),
    "water": ("Ice", "ice"),
}


def parse_lineup(text):
    entries = [" ".join(entry.lower().split()).rpartition(" ") for entry in text.split(",")]
    if len(entries) != 4:
        raise ValueError("Enter four comma-separated boss and element pairs")
    lineup = []
    for boss, _, element in entries:
        if boss not in BOSS_STAGES:
            raise ValueError(f"Unknown Raid boss {boss or element!r}")
        if element not in ELEMENTS:
            raise ValueError(f"Unknown element {element!r}. Choose from {', '.join(ELEMENTS)}")
        lineup.append((boss, element))
    if len(set(lineup)) != 4:
        raise ValueError("Each slot must have a distinct boss and element combination")
    return lineup


def use_local_presentation(raid, season_row, reference_dir):
    pack = reference_dir.parent
    if not (pack / "manifest.json").is_file():
        return
    library = ResourceLibrary([pack / "resources" / "files"])
    candidates = sorted(
        raid["Seasons"], key=lambda row: (row is season_row, row["Id"]), reverse=True
    )
    for candidate in candidates:
        banner = available_locales(candidate.get("Banner"), library)
        background = available_locales(candidate.get("Background"), library)
        if banner and background:
            season_row["Banner"] = json.dumps(banner)
            season_row["Background"] = json.dumps(background)
            for key in ("BackgroundPosition", *(f"ButtonPosition{i}" for i in range(1, 5))):
                if key in candidate:
                    season_row[key] = candidate[key]
            return
    raise ValueError("The local content pack has no complete Raid banner and background")


def available_locales(encoded, library):
    urls = json.loads(encoded) if encoded else {}
    available = {locale: url for locale, url in urls.items() if library.lookup(url)}
    if not available:
        return None
    fallback = available.get("enUS") or next(iter(available.values()))
    return {locale: available.get(locale, fallback) for locale in dict.fromkeys(("enUS", *urls))}


def build_season(raid, monsters, season, season_row, lineup):
    by_id = {monster["Id"]: monster for monster in monsters}
    by_name = {monster["Name"]: monster for monster in monsters}
    details = {detail["Id"]: detail for detail in raid["BossDetails"]}
    next_boss = count(max(details.keys() | {boss["Id"] for boss in raid["Boss"]}) + 1)
    available_monster_ids = (i for i in range(799999, 799699, -1) if i not in by_id)
    boss_set = (
        max(
            [row["SetId"] for row in raid["Boss"]]
            + [row["BossSet"] for row in raid["Seasons"] + raid.get("Seasons.Kong", [])]
        )
        + 1
    )
    season_row["BossSet"] = boss_set
    bosses = []
    for slot, (boss, element) in enumerate(lineup, 1):
        stage_id = BOSS_STAGES[boss]
        elemental_type, suffix = ELEMENTS[element]
        candidates = sorted(
            (
                detail
                for detail in details.values()
                if detail["StageId"] == stage_id and detail["MonsterId"] in by_id
            ),
            key=lambda detail: detail["Id"],
        )
        if not candidates:
            raise ValueError(f"No matching stage definition for {boss}")
        detail = next(
            (
                row
                for row in candidates
                if by_id[row["MonsterId"]].get("ElementalType") == elemental_type
            ),
            None,
        )
        if detail is None:
            base = candidates[0]
            original = by_id[base["MonsterId"]]
            sibling_name = original["Name"].rsplit("_", 1)[0] + "_" + suffix
            sibling = by_name.get(sibling_name) if "_v2_" in original["Name"] else None
            if sibling is not None and (
                sibling["Class"] != original["Class"]
                or sibling.get("ElementalType") != elemental_type
            ):
                sibling = None
            if sibling is None:
                monster_id = next(available_monster_ids, None)
                # The native name parser strips a final one-character suffix
                # when forming the localized name key.
                name = next(
                    (
                        f"{original['Name']}_{letter}"
                        for letter in "0123456789"
                        if f"{original['Name']}_{letter}" not in by_name
                    ),
                    None,
                )
                if monster_id is None or name is None:
                    raise ValueError(f"Could not allocate a local monster entry for {boss}")
                sibling = dict(original, Id=monster_id, Name=name, ElementalType=elemental_type)
                monsters.append(sibling)
                by_name[name] = sibling
            detail = dict(base, Id=next(next_boss), MonsterId=sibling["Id"])
            raid["BossDetails"].append(detail)
        raid["Boss"].append({"Id": detail["Id"], "Slot": slot, "SetId": boss_set})
        bosses.append({"id": detail["Id"], "slot": slot, "stage_id": stage_id})
    return dict(season, boss_set=boss_set, bosses=bosses)
