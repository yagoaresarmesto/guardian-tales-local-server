# SPDX-License-Identifier: Apache-2.0
"""Local artwork for missing Recommended cards in the Book of Contents."""

from functools import lru_cache
from io import BytesIO

from .panel_common.artwork import bundle_texture

PREFIX = "media/contents_book/banner_book_recommend_"
# This scenery from the Invader Journalist storyline is distributed as a plain PNG.
STORY_SCENERY = "media/roadmap/v3.57_roadmap_indaver_journalist.png"
TETIS = ("ui/backgrounds/rogue_chess", "bg_rogue_chess_perks_00")
COOP = ("ondemand/coop_expedition/ui", "coop_expedition_worldmap_02")
SOURCES = {
    "story_short_00.png": None,
    **{f"ch{i:02}_00.png": ("ui/backgrounds/worldmap", "bg_stagemap") for i in range(1, 23)},
    **{f"rogue_chess_{i:02}.png": TETIS for i in range(3)},
    **{f"coop_expedi_{i:02}.png": COOP for i in range(4)},
    "coop_expedi_event_01.png": COOP,
}


@lru_cache(maxsize=8)
def _card(path, checksum, texture):
    from PIL import Image, ImageOps

    picture = ImageOps.fit(
        bundle_texture(path, texture).convert("RGB"), (390, 300), Image.Resampling.LANCZOS
    )
    output = BytesIO()
    picture.save(output, format="PNG")
    return output.getvalue()


def missing_recommended(library, requested):
    if not requested or not requested.startswith(PREFIX):
        return None, None
    name = requested[len(PREFIX) :]
    if name not in SOURCES:
        return None, None
    source = SOURCES[name]
    if source:
        bundle, texture = source
        entry = library.files.get("AssetBundles/Android/" + bundle)
        if entry:
            try:
                png = _card(*entry, texture)
            except (ImportError, KeyError, OSError, ValueError):
                png = None
            if png:
                return None, png
    return library.files.get(STORY_SCENERY), None
