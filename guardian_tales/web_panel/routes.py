# SPDX-License-Identifier: Apache-2.0
"""Public panel modes and their explicitly served resources."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from html import escape
from pathlib import Path
from string import Template

from ..guild_raid import RaidSelectionChanged
from ..punchking_static import ArenaSelectionChanged
from ..reference import ReferenceData
from .artwork import BOSSES, ELEMENT_FRAMES, UI
from .dka import adapter as dka
from .dka import sprites
from .raid import adapter as raid

ROOT = Path(__file__).parent
CSS = "text/css; charset=utf-8"
JS = "text/javascript; charset=utf-8"


@dataclass(frozen=True)
class Mode:
    slug: str
    path: str
    label: str
    title: str
    state: Callable[[ReferenceData], dict]
    apply: Callable[[ReferenceData, dict], None]
    conflict: type[ValueError]


MODES = (
    Mode("raid", "/", "Raid", "Guild Raid", raid.state, raid.apply, RaidSelectionChanged),
    Mode(
        "dka", "/dka", "DKA", "Dungeon Kingdom Arena", dka.state, dka.apply, ArenaSelectionChanged
    ),
)
PAGES = {mode.path: mode for mode in MODES}
API = {f"/api/{mode.slug}": mode for mode in MODES}
FILES = {"/panel.css": (ROOT / "shared/panel.css", CSS), "/panel.js": (ROOT / "shared/ui.js", JS)}
for mode in MODES:
    for suffix, mime in (("css", CSS), ("js", JS)):
        FILES[f"/{mode.slug}.{suffix}"] = (ROOT / mode.slug / f"panel.{suffix}", mime)
MEDIA = {
    "/map.png": (lambda refs: raid.map_image(refs).read_bytes(), "image/png"),
    "/arena.jpg": (lambda refs: dka.arena_image(refs).read_bytes(), "image/jpeg"),
    **{
        f"/dka/slimes/{element}.png": (partial(BOSSES.read, frame=frame), "image/png")
        for element, frame in sprites.FRAMES.items()
    },
    **{
        f"/elements/{element}.png": (partial(UI.read, frame=frame), "image/png")
        for element, frame in ELEMENT_FRAMES.items()
    },
}


def media_resource(path):
    if path in MEDIA:
        return MEDIA[path]
    # Only the frame name varies. The local bosses bundle is fixed.
    match = re.fullmatch(r"/raid/bosses/([a-z0-9_]{1,100})\.png", path)
    if match:
        return partial(BOSSES.read, frame=match[1]), "image/png"
    return None


def render_page(mode, *, show_brand):
    links = []
    for entry in MODES:
        current = ' aria-current="page"' if entry == mode else ""
        links.append(f'<a href="{escape(entry.path)}"{current}>{escape(entry.label)}</a>')
    layout = Template((ROOT / "shared/layout.html").read_text(encoding="utf-8"))
    return layout.substitute(
        title=escape(mode.title),
        brand_icon='<img class="brand-icon" src="/brand.png" alt="">' if show_brand else "",
        slug=mode.slug,
        navigation="".join(links),
        body=(ROOT / mode.slug / "view.html").read_text(encoding="utf-8"),
    ).encode()
