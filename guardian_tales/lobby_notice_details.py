# SPDX-License-Identifier: Apache-2.0
"""The read-only, self-contained mode guide opened by the lobby's Move button."""

import base64
from html import escape
from io import BytesIO
from pathlib import Path

from .lobby_notice_art import mode_illustration, panel_image

STYLES = Path(__file__).with_name("templates") / "lobby_details.css"
SHORT_NAMES = {"Guild Raid": "Raid", "Dungeon Kingdom Arena": "DKA"}


def image_tag(image, kind, **options):
    encoded = BytesIO()
    image.save(encoded, **options)
    mime = "jpeg" if options["format"] == "JPEG" else "png"
    data = base64.b64encode(encoded.getvalue()).decode("ascii")
    return f'<img class="{kind}" alt="" src="data:image/{mime};base64,{data}">'


def portrait(refs, path):
    if not path:
        return ""
    try:
        image = panel_image(refs, path)
    except ImportError:
        return ""
    if image is None or not (bounds := image.getbbox()):
        return ""
    image = image.crop(bounds)
    image.thumbnail((96, 96))
    return image_tag(image, "portrait", format="PNG")


def heading_art(refs, card):
    try:
        tile, illustrated = mode_illustration(refs, card)
    except ImportError:
        return ""
    return image_tag(tile.convert("RGB"), "scene", format="JPEG", quality=84) if illustrated else ""


def facts(rows):
    entries = "".join(
        f"<div><dt>{escape(key)}</dt><dd>{escape(value)}</dd></div>" for key, value in rows
    )
    return f'<dl class="facts">{entries}</dl>'


def group(title, contents):
    return f'<section class="group"><h3>{escape(title)}</h3>{contents}</section>'


def lineup(refs, card, raid):
    tiles = []
    art_keys = card.get("portraits" if raid else "slimeElements", [])
    for index, (label, value) in enumerate(card["details"]):
        key = art_keys[index] if index < len(art_keys) else None
        path = f"/raid/bosses/{key}.png" if raid else f"/dka/slimes/{key}.png"
        active = not raid and index + 1 == card.get("selectedDay")
        if raid:
            slot, name, note = f"Encounter {index + 1:02}", label, value
        else:
            name, _, note = value.partition(" · ")
            slot = label
        selected = '<span class="current">Selected</span>' if active else ""
        sprite = portrait(refs, path) if key else ""
        tiles.append(
            f'<li class="{"active" if active else ""}"><div class="slot">{escape(slot)}{selected}</div>'
            f'<div class="unit">{sprite}<div><strong>{escape(name)}</strong>'
            f'<span class="note">{escape(note)}</span></div></div></li>'
        )
    return group(
        "Boss lineup" if raid else "Weekly rotation",
        '<ol class="lineup">' + "".join(tiles) + "</ol>",
    )


def stage_groups(rows):
    areas = {}
    for label, value in rows:
        area, separator, name = label.partition(" · ")
        if not separator or not area.startswith("Area "):
            area, name = "Other stages", label
        stage, _, ident = name.rpartition(" (")
        if not stage:
            stage = name
        if stage.isdecimal():
            stage = "Stage " + stage
        ident = ident.removesuffix(")")
        areas.setdefault(area, []).append(
            f"<div><dt>{escape(stage)}<small>{escape(ident)}</small></dt><dd>{escape(value)}</dd></div>"
        )
    sections = []
    for area, entries in areas.items():
        count = len(entries)
        sections.append(
            f'<details><summary>{escape(area)}<span>{count} {"stage" if count == 1 else "stages"}</span></summary>'
            f'<dl class="facts">{"".join(entries)}</dl></details>'
        )
    return group("Stage levels", "".join(sections))


def mode_details(refs, card):
    name, rows = card["name"], card["details"]
    if name == "Orbital Lift":
        parts = []
        if floor := card.get("currentFloor"):
            enemies = floor["units"] or [("Enemies", "None")]
            parts.append(
                group(
                    "Next floor formation", facts([("Enemy level", str(floor["level"])), *enemies])
                )
            )
        if rows:
            parts.append(group("Edited floors", facts(rows)))
        return "".join(parts)
    if not rows:
        return ""
    if name in ("Guild Raid", "Dungeon Kingdom Arena"):
        return lineup(refs, card, name == "Guild Raid")
    if name == "Expedition":
        return stage_groups(rows)
    if name == "Kama-ZONE":
        calendar = group("Season calendar", facts(rows[:3]))
        return calendar + (group("Benefits", facts(rows[3:])) if len(rows) > 3 else "")
    if name == "Tetis":
        loadout, seasons, specialties = [], [], []
        for key, value in rows:
            if key.removeprefix("Season ").isdecimal():
                seasons.append((key, value))
            elif " · " in key:
                specialties.append((key, value))
            else:
                loadout.append((key, value))
        return "".join(
            group(title, facts(entries))
            for title, entries in (
                ("Loadout", loadout),
                ("Season progress", seasons),
                ("Specialties", specialties),
            )
            if entries
        )
    return group("Practice settings", facts(rows))


def detail_page(refs, cards):
    controls, labels, pages, rules = [], [], [], []
    for index, card in enumerate(cards):
        toggle, panel = f"mode-{index}", f"sheet-{index}"
        name = escape(card["name"])
        short = escape(SHORT_NAMES.get(card["name"], card["name"]))
        controls.append(
            f'<input class="switch" type="radio" id="{toggle}" name="mode" aria-label="{name}" '
            f'aria-controls="{panel}"{" checked" if index == 0 else ""}>'
        )
        labels.append(f'<label for="{toggle}">{short}</label>')
        rules.extend(
            (
                f"#{toggle}:checked ~ main #{panel} {{display:block}}",
                f'#{toggle}:checked ~ .modes [for="{toggle}"] {{background:var(--chosen);color:var(--gold);border-color:var(--gold)}}',
                f'#{toggle}:focus-visible ~ .modes [for="{toggle}"] {{outline:2px solid white;outline-offset:2px}}',
            )
        )
        caption = f'<p>{escape(card["caption"])}</p>' if card["caption"] else ""
        hp = f'<p class="hp">{escape(card["hp"])}</p>' if card.get("hp") else ""
        pages.append(
            f'<article id="{panel}" aria-labelledby="{panel}-title"><header class="hero">'
            f'{heading_art(refs, card)}<div class="hero-copy"><h2 id="{panel}-title">{name}</h2>'
            f'<strong>{escape(card["summary"])}</strong>{caption}{hp}</div></header>'
            f"{mode_details(refs, card)}</article>"
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Game mode settings</title><style>"
        + STYLES.read_text(encoding="utf-8")
        + "\n".join(rules)
        + '</style></head><body><div class="reader">'
        '<header class="mast"><h1>Game mode settings</h1></header><div class="layout">'
        + "".join(controls)
        + '<div class="modes">'
        + "".join(labels)
        + "</div><main>"
        + "".join(pages)
        + "</main></div></div></body></html>"
    ).encode()
