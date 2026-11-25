# SPDX-License-Identifier: Apache-2.0
"""Public panel modes and their explicitly served resources."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from html import escape
from pathlib import Path

from guardian_tales.panel_common.views import CSS, DASHBOARD, JS, render_layout

from .. import orbital_boards, orbital_levels
from ..expedition_levels import LevelSelectionChanged
from ..guild_raid import RaidSelectionChanged
from ..guild_war_static import WarSelectionChanged
from ..kamazone import SeasonSelectionChanged
from ..punchking_static import ArenaSelectionChanged
from .artwork import (
    BOSSES,
    CHARACTERS,
    ELEMENT_FRAMES,
    EXPEDITION,
    KAMAZONE,
    TETIS,
    TETIS_ARTIFACTS,
    UI,
    WAR,
)
from .dka import adapter as dka
from .dka import sprites
from .expedition import adapter as expedition
from .guild_war import adapter as guild_war
from .kamazone import adapter as kamazone
from .kamazone.season_art import SEASONS as KAMAZONE_SEASONS
from .orbital_lift.adapter import OrbitalChanged, OrbitalEditor
from .raid import adapter as raid
from .tetis import sprites as tetis_sprites
from .tetis.adapter import TetisChanged, TetisEditor

ROOT = Path(__file__).parent


@dataclass(frozen=True)
class Editor:
    state: Callable
    apply: Callable
    conflict: type[ValueError]
    source: str = "references"


@dataclass(frozen=True)
class Mode:
    slug: str
    path: str
    label: str
    title: str
    editor: Editor

    @property
    def directory(self):
        return ROOT / self.slug.replace("-", "_")


MODES = (
    Mode(
        "raid", "/raid", "Raid", "Guild Raid", Editor(raid.state, raid.apply, RaidSelectionChanged)
    ),
    Mode(
        "dka",
        "/dka",
        "DKA",
        "Dungeon Kingdom Arena",
        Editor(dka.state, dka.apply, ArenaSelectionChanged),
    ),
    Mode(
        "guild-war",
        "/guild-war",
        "Guild Wars",
        "Guild Wars",
        Editor(guild_war.state, guild_war.apply, WarSelectionChanged),
    ),
    Mode(
        "kamazone",
        "/kamazone",
        "Kama-ZONE",
        "Kama-ZONE",
        Editor(kamazone.state, kamazone.apply, SeasonSelectionChanged),
    ),
    Mode(
        "expedition",
        "/expedition",
        "Expedition",
        "Expedition",
        Editor(expedition.state, expedition.apply, LevelSelectionChanged),
    ),
    Mode(
        "orbital-lift",
        "/orbital-lift",
        "Orbital Lift",
        "Orbital Lift",
        Editor(OrbitalEditor.state, OrbitalEditor.write, OrbitalChanged, "orbital"),
    ),
    Mode(
        "tetis",
        "/tetis",
        "Tetis",
        "The Tale of the Tetis Hero",
        Editor(TetisEditor.state, TetisEditor.apply, TetisChanged, "tetis"),
    ),
)
PAGES = {mode.path: mode for mode in MODES}
API = {f"/api/{mode.slug}": mode.editor for mode in MODES}
API["/api/orbital-lift/boards"] = Editor(
    orbital_boards.state, orbital_boards.apply, orbital_levels.LevelChanged
)
API["/api/orbital-lift/enemy-level"] = Editor(
    orbital_levels.state, orbital_levels.apply, orbital_levels.LevelChanged
)
FILES = {"/panel.css": (ROOT / "shared/panel.css", CSS), "/panel.js": (ROOT / "shared/ui.js", JS)}
FILES["/dashboard.css"] = (DASHBOARD / "dashboard.css", CSS)
FILES["/backend.js"] = (ROOT / "shared/backend.js", JS)
FILES["/tetis-specialty.js"] = (ROOT / "tetis/specialty.js", JS)
FILES["/services.css"] = (ROOT / "shared/services.css", CSS)
FILES["/orbital-board.js"] = (ROOT / "orbital_lift/board.js", JS)
FILES["/tetis-loadout.js"] = (ROOT / "tetis/loadout.js", JS)
FILES["/tetis-loadout.css"] = (ROOT / "tetis/loadout.css", CSS)
for mode in MODES:
    for suffix, mime in (("css", CSS), ("js", JS)):
        FILES[f"/{mode.slug}.{suffix}"] = (mode.directory / f"panel.{suffix}", mime)
MEDIA = {
    **{
        f"/tetis/specialty/{frame}.png": (partial(UI.read, frame=frame), "image/png")
        for frame in (
            "frame_deco_perks_00",
            "frame_perks_on_00",
            "frame_perks_on_01",
            "ic_lock_perks_00",
            "ic_rogue_chess_perks_num_00",
            "ic_rogue_chess_perks_num_01",
            "ic_rogue_chess_perks_num_02",
        )
    },
    "/tetis/skill-tree.jpg": (TETIS.read, "image/jpeg"),
    "/map.png": (lambda refs: raid.map_image(refs).read_bytes(), "image/png"),
    "/guild-war/fortress.png": (partial(WAR.read, frame="gvg_multi_castle_03.png"), "image/png"),
    "/kamazone/lobby.jpg": (KAMAZONE.read, "image/jpeg"),
    **{
        f"/kamazone/seasons/{art.hero}.png": (art.read, "image/png")
        for art in KAMAZONE_SEASONS.values()
    },
    "/expedition/forest.jpg": (EXPEDITION.read, "image/jpeg"),
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
    portrait = re.fullmatch(r"/orbital-lift/enemies/([a-zA-Z0-9_.-]{1,100})\.png", path)
    if portrait:
        if portrait[1] == "boss_shadow_beast":
            return partial(BOSSES.read, frame="boss_shadow_beast_b"), "image/png"
        return partial(CHARACTERS.read, frame=portrait[1]), "image/png"
    artifact = re.fullmatch(r"/tetis/artifacts/(rc_[a-z0-9_]{1,60})\.png", path)
    if artifact:
        return partial(TETIS_ARTIFACTS.read, frame=artifact[1]), "image/png"
    if path in MEDIA:
        return MEDIA[path]
    match = re.fullmatch(r"/tetis/specialty/(nodes|spells)/([a-z0-9_]{1,100})\.png", path)
    if match:
        return partial(tetis_sprites.read, atlas=match[1], frame=match[2]), "image/png"
    # Only the frame name varies. The local bosses bundle is fixed.
    match = re.fullmatch(r"/raid/bosses/([a-z0-9_]{1,100})\.png", path)
    if match:
        return partial(BOSSES.read, frame=match[1]), "image/png"
    return None


def render_page(mode, *, show_brand):
    return render_layout(
        mode.directory / "view.html",
        tabs=((entry.path, entry.label) for entry in MODES),
        active_path=mode.path,
        title=escape(mode.title),
        base_css="/panel.css",
        stylesheet="/" + mode.slug + ".css",
        preview_controls="",
        body_attributes="",
        brand_icon='<img class="brand-icon" src="/brand.png" alt="">' if show_brand else "",
        slug=mode.slug,
    )
