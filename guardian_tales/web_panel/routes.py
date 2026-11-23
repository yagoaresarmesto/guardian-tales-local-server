# SPDX-License-Identifier: Apache-2.0
"""Public panel modes and their explicitly served resources."""

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from string import Template

from ..guild_raid import RaidSelectionChanged
from ..punchking_static import ArenaSelectionChanged
from ..reference import ReferenceData
from .dka import adapter as dka
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
}


def render_page(mode):
    links = []
    for entry in MODES:
        current = ' aria-current="page"' if entry == mode else ""
        links.append(f'<a href="{escape(entry.path)}"{current}>{escape(entry.label)}</a>')
    layout = Template((ROOT / "shared/layout.html").read_text(encoding="utf-8"))
    return layout.substitute(
        title=escape(mode.title),
        slug=mode.slug,
        navigation="".join(links),
        body=(ROOT / mode.slug / "view.html").read_text(encoding="utf-8"),
    ).encode()
