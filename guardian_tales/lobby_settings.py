# SPDX-License-Identifier: Apache-2.0
"""Read the applied game mode selections for the local lobby notice."""

import hashlib
import logging
import re
import sqlite3

from . import (
    expedition,
    expedition_levels,
    guild_war,
    guild_war_static,
    kamazone,
    kamazone_practice,
    orbital_levels,
    punchking,
    punchking_static,
    tetis_map_trial,
    tetis_progress,
)
from .orbital import LAST_SELECTABLE_FLOOR
from .panel_common.labels import english_labels
from .web_panel.raid import adapter as raid


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
    for day in variant["days"]:
        element = {"None": "Basic", "Darkness": "Dark", "Ice": "Water"}.get(
            day["element"], day["element"]
        )
        slime = "Void Slime" if element == "Nebula" else f"{element} Slime"
        weakness = {"Down": "Downed", "Poison": "Injured", "Aerial": "Airborne"}.get(
            day["weak_point"], day["weak_point"]
        )
        days.append((slime, weakness))
    number = saved["day"]
    return card(
        f"Rotation {variant['id']} · Day {number}",
        f"Season {variant['season_id']} · {days[number-1][0]}",
        [(f"Day {i}", f"{slime} · {weakness}") for i, (slime, weakness) in enumerate(days, 1)],
    )


def kama_card(refs):
    status = kamazone.status(refs)
    ident = status["selected_season_id"]
    if ident is None:
        return card("Original calendar")
    archived = status["old_active"]
    seasons = status["old_seasons"] if archived else status["seasons"]
    name = next((s["name"] for s in seasons if s["season_id"] == ident), f"Season {ident}")
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
            used = kamazone_practice.allocated_points(
                kamazone_practice.catalog(source, ident), benefits
            )
            details.append(("Benefit points allocated", f"{used:,} / {kamazone_practice.BUDGET:,}"))
            details.extend((f"Benefit {k}", f"Level {v}") for k, v in sorted(benefits.items()) if v)
    return card(f"{'Old season' if archived else 'Season'} {ident}", f"{name} · {phase}", details)


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
    phase = {
        "coop-offense": "Cooperative attack",
        "coop-defense": "Cooperative defense",
        "multi-offense": "Fortress siege",
        "multi-defense": "Fortress defense",
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
    return card(phase, f"Season {saved['season_id']}", details)


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
    return card(summary, caption, details)


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
