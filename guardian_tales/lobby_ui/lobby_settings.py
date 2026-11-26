# SPDX-License-Identifier: Apache-2.0
"""Read the applied game mode selections for the local lobby notice."""

import hashlib
import logging
import re
import sqlite3

from guardian_tales.modes.expedition import expedition, expedition_levels
from guardian_tales.modes.guild import guild_war, guild_war_static, punchking, punchking_static
from guardian_tales.modes.kamazone import kamazone, kamazone_practice
from guardian_tales.modes.orbital import orbital_boards, orbital_levels
from guardian_tales.modes.orbital.orbital import LAST_SELECTABLE_FLOOR
from guardian_tales.modes.tetis import tetis_map_trial, tetis_progress
from guardian_tales.panel_common.labels import english_labels
from guardian_tales.web_panel.dka.sprites import FRAMES as SLIME_FRAMES
from guardian_tales.web_panel.kamazone.season_art import SEASONS as SEASON_ART
from guardian_tales.web_panel.raid import adapter as raid


def card(summary, caption="", details=(), **extra):
    return dict(summary=summary, caption=caption, details=list(details), **extra)


def raid_card(refs):
    state = raid.state(refs)
    season = state["active"]
    kind = "Custom lineup" if state["custom"] else "Original lineup"
    if not state["prepared"]:
        kind = "Catalog default"
    bosses = [
        [(slot["boss"] or f"Stage {slot['stage']}").title(), (slot["element"] or "").title()]
        for slot in season["bosses"]
    ]
    return card(
        f"Season {season['id']}",
        kind,
        bosses,
        hp=f"{season['hpPerBar']:,} HP per bar",
        portraits=[state["bossPortraits"].get(slot["boss"]) for slot in season["bosses"]],
    )


def dka_card(refs):
    saved = punchking_static.load_selection(refs)
    if not saved:
        return card("No practice rotation")
    variant = next(
        v for v in punchking.load_catalog(refs)["variants"] if v["id"] == saved["variant"]
    )
    days = []
    elements = {"None": "Basic", "Darkness": "Dark", "Ice": "Water", "Nebula": "Space"}
    for day in variant["days"]:
        element = elements.get(day["element"], day["element"])
        slime = "Void Slime" if element == "Space" else f"{element} Slime"
        weakness = {"Down": "Downed", "Poison": "Injured", "Aerial": "Airborne"}.get(
            day["weak_point"], day["weak_point"]
        )
        days.append((element.lower(), slime, weakness))
    number = saved["day"]
    element, slime, _ = days[number - 1]
    return card(
        f"Rotation {variant['id']} · Day {number}",
        f"Season {variant['season_id']} · {slime}",
        [(f"Day {i}", f"{name} · {weakness}") for i, (_, name, weakness) in enumerate(days, 1)],
        selectedDay=number,
        slimeElements=[key if key in SLIME_FRAMES else None for key, _, _ in days],
        sprite=f"/dka/slimes/{element}.png" if element in SLIME_FRAMES else None,
    )


def kama_card(refs):
    status = kamazone.status(refs)
    ident = status["selected_season_id"]
    if ident is None:
        return card("Original calendar")
    archived = status["old_active"]
    seasons = status["old_seasons"] if archived else status["seasons"]
    season = next((s for s in seasons if s["season_id"] == ident), {})
    name = season.get("name", f"Season {ident}")
    art = SEASON_ART.get(season.get("name_key")) if not archived else None
    phase = status["calendar_phase"].replace("-", " ").capitalize()
    window = status["local_period"]
    details = [
        (key, window[k][:10] + " UTC")
        for key, k in (("Opens", "From"), ("Ends", "To"), ("Rewards until", "RewardUntil"))
    ]
    if status["menu_active_now"]:
        source = refs.read_bytes("static_data_get.bin")
        if kamazone.playable_season(source, ident):
            benefits = kamazone_practice.effective(refs, source, ident)["benefits"]
            catalog = kamazone_practice.catalog(source, ident)
            used = kamazone_practice.allocated_points(catalog, benefits)
            details.append(("Benefit points allocated", f"{used:,} / {kamazone_practice.BUDGET:,}"))
            selected = [(catalog[int(k)], v) for k, v in sorted(benefits.items()) if v]
            if selected:
                keys = {row["Name"] for row, _ in selected if row.get("Name")}
                labels = english_labels(refs, kamazone_practice.source_hash(source), keys)
                for row, value in selected:
                    title = labels.get(row.get("Name")) or f"Benefit {row['Id']}"
                    details.append((title, f"Level {value} / {row['MaxLevel']}"))
    return card(
        f"{'Old season' if archived else 'Season'} {ident}",
        f"{name} · {phase}",
        details,
        backdrop=f"/kamazone/seasons/{art.hero}.png" if art else None,
    )


def expedition_card(refs):
    if not expedition.enabled(refs):
        return card("Trial disabled")
    stages = expedition_levels.level_settings(refs)["stages"]
    edited = [s for s in stages if s["overridden"]]
    if not edited:
        return card("Original enemy levels", f"Solo trial · {len(stages)} stages")
    levels = [s["enemy_level"] for s in edited]
    low, high = min(levels), max(levels)
    count = (
        f"All {len(stages)} stages"
        if len(edited) == len(stages)
        else f"{len(edited)} of {len(stages)} stages"
    )
    details = []
    for s in edited:
        key = s["name"] or ""
        match = re.fullmatch(r"expedition_battle_chosenone_(\d+)_(.+)", key)
        name = (
            f"Area {match[1]} · {match[2].replace('_', ' ').title()}"
            if match
            else key.removeprefix("expedition_").replace("_", " ").title()
        )
        details.append(
            (f"{name} ({s['stage_id']})", f"Lv. {s['original_level']} → {s['enemy_level']}")
        )
    return card(
        f"Enemy level {low}" if low == high else f"Enemy levels {low}–{high}", count, details
    )


def war_card(refs):
    saved = guild_war.selection_status(guild_war_static.load_selection(refs))
    if not saved["enabled"]:
        return card("Practice disabled")
    phase, icon = {
        "coop-offense": ("Cooperative attack", "attack"),
        "coop-defense": ("Cooperative defense", "defense"),
        "multi-offense": ("Fortress siege", "outpost"),
        "multi-defense": ("Fortress defense", "fortress"),
    }[saved["phase_name"]]
    details = [("Basic course", "Skipped" if saved["skip_basic_requirement"] else "Required")]
    if saved["phase_name"].startswith("multi-"):
        details.append(
            (
                "Round",
                {"auto": "Automatic", "prep": "Preparation", "combat": "Combat"}[
                    saved["round_mode"]
                ],
            )
        )
        details.append(
            ("Castle", str(saved["local_attack_castle"] or saved["local_defense_castle"] or "None"))
        )
    return card(phase, f"Season {saved['season_id']}", details, sprite=f"/guild-war/{icon}.png")


def orbital_card(refs, db):
    settings = orbital_levels.settings(refs)
    level, boards = settings["level"], settings["boards"]
    row = (
        db.execute(
            "SELECT json_extract(profile, '$.UserProgress.TowerInfinity.Floor') FROM local_account WHERE id=1"
        ).fetchone()
        if db is not None
        else None
    )
    floor = abs(row[0]) + 1 if row and type(row[0]) is int else None
    summary = (
        f"Next floor {floor}"
        if floor and floor <= LAST_SELECTABLE_FLOOR
        else "Tower complete" if floor else "Orbital floors"
    )
    caption = f"Enemy level {level}" if level is not None else "Original enemy levels"
    if boards:
        caption += f" · {len(boards)} edited"
    details = []
    for key in sorted(boards, key=int):
        board = boards[key]
        units = board["units"]
        description = f"Level {board['level'] or level or 'original'}"
        if units is not None:
            placements = [
                f"Cell {u['position']}: #{u['enemy']}"
                + (f" (elite {u['elite']})" if u.get("elite") else "")
                for u in units
            ]
            description += " · " + (", ".join(placements) or "Empty formation")
        details.append((f"Floor {key}", description))
    extra = {}
    if floor and floor <= LAST_SELECTABLE_FLOOR:
        catalog = orbital_boards.catalog(refs.read_bytes("static_data_get.bin"), refs.directory)
        stock = catalog["floors"][floor]
        custom = boards.get(str(floor), {})
        units = custom.get("units")
        if units is None:
            units = stock["units"]
        enemies = {e["id"]: e["name"] for e in catalog["enemies"]}
        formation = []
        for unit in sorted(units, key=lambda u: u["position"]):
            elite = unit.get("elite", stock["originalElites"].get(unit.get("origin")))
            name = enemies.get(unit["enemy"]) or f"#{unit['enemy']}"
            if elite:
                name += f" · {catalog['eliteNames'].get(elite) or f'Elite #{elite}'}"
            formation.append((f"Cell {unit['position']}", name))
        extra["currentFloor"] = {
            "level": custom.get("level") or level or stock["level"],
            "units": formation,
        }
    if floor and floor >= 1001:
        extra.update(
            backdrop="/orbital-lift/scenery/mars-bg.webp",
            sprite="/orbital-lift/scenery/ic_tower1000_clear_00.webp",
        )
    return card(summary, caption, details, **extra)


def tetis_card(refs, db):
    catalog = tetis_progress.load_catalog(refs)
    season = catalog.current
    trial, _ = tetis_map_trial.selection(refs)
    if db is None:
        return card(f"Season {season}", "Map trial on" if trial else "Original maps")
    view = tetis_progress.editor_view(db, catalog)
    loadout = view["loadout"]
    current = next(s for s in view["seasons"] if s["id"] == season)
    details = [("Season 1 map trial", "Enabled" if trial else "Off")]
    selected = {}
    for label, field, options in (
        ("Guardian spell", "spellId", "spells"),
        ("Artifact", "artifactId", "artifacts"),
    ):
        item = next((i for i in loadout[options] if i["id"] == loadout[field]), None)
        selected[label] = item
    nodes = [(s["id"], n) for s in view["seasons"] for n in s["nodes"] if n["points"]]
    keys = {n["name"] for _, n in nodes} | {i["name"] for i in selected.values() if i}
    labels = (
        english_labels(
            refs, hashlib.sha256(refs.read_bytes("static_data_get.bin")).hexdigest(), keys
        )
        if keys
        else {}
    )
    details.extend(
        (label, labels.get(i["name"], f"#{i['id']}") if i else "None")
        for label, i in selected.items()
    )
    for s in view["seasons"]:
        details.append(
            (f"Season {s['id']}", f"Floor {s['clearedFloor']} cleared · Tactic level {s['level']}")
        )
    details.extend(
        (f"S{s} · {labels.get(n['name'], 'Specialty #' + str(n['id']))}", f"{n['points']} points")
        for s, n in nodes
    )
    floor = current["clearedFloor"]
    return card(
        f"Season {season}",
        (f"Floor {floor} cleared" if floor else "No floors cleared")
        + f" · Tactic Lv. {current['level']}"
        + (" · Map trial" if trial else ""),
        details,
    )


def report(refs, db):
    modes = (
        ("Guild Raid", raid_card),
        ("Dungeon Kingdom Arena", dka_card),
        ("Kama-ZONE", kama_card),
        ("Expedition", expedition_card),
        ("Guild Wars", war_card),
        ("Orbital Lift", lambda refs: orbital_card(refs, db)),
        ("Tetis", lambda refs: tetis_card(refs, db)),
    )
    cards = []
    for title, read in modes:
        try:
            values = read(refs)
        except (ValueError, KeyError, OSError, StopIteration, sqlite3.Error):
            logging.getLogger(__name__).warning(
                "Could not read lobby settings for %s", title, exc_info=True
            )
            values = card("Settings unavailable")
        cards.append({"name": title, **values})
    return cards
