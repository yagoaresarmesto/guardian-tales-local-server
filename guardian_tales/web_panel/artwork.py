# SPDX-License-Identifier: Apache-2.0
"""Artwork used by the game mode panel."""

from guardian_tales.panel_common.artwork import UI as UI
from guardian_tales.panel_common.artwork import Atlas
from guardian_tales.panel_common.artwork import frame_png as frame_png

BOSSES = Atlas("spritesheets/bosses", "bosses")
CHARACTERS = Atlas("spritesheets/heroes", "characters")
WAR = Atlas("ondemand/guild_war/ui", "guildWar")
KAMAZONE = Atlas("ondemand/ancientmall/ui", "roguelike_mall_bg")
EXPEDITION = Atlas("ondemand/expedition/ui", "expedition_bg_forest_night")
TETIS_ARTIFACTS = Atlas("spritesheets/items", "items")
TETIS = Atlas("ui/backgrounds/rogue_chess", "bg_rogue_chess_perks_00")
ELEMENT_FRAMES = {
    "basic": "ic_attribute_no",
    "dark": "ic_attribute_dark",
    "earth": "ic_attribute_ground",
    "fire": "ic_attribute_fire",
    "light": "ic_attribute_light",
    "water": "ic_attribute_water",
    "space": "ic_attribute_nebula",
}
