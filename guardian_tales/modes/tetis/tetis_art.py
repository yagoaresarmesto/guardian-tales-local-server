# SPDX-License-Identifier: Apache-2.0
"""Fill missing Tetis archive media using the game's episode scenes and English titles."""

from functools import lru_cache
from io import BytesIO

from guardian_tales.panel_common.artwork import bundle_texture

PREFIX = "media/roguechess/"
BUNDLES = "AssetBundles/Android/ondemand/roguechess/narrative/"
SCENES = {
    "bg_rogue_chess_00.jpg": ("ep1", "bg_rogue_chess_00", False),
    "bg_rogue_chess_01.jpg": ("ep1", "bg_rogue_chess_00", True),
    "bg_rogue_chess_s2_00.png": ("ep2", "Roguechess_main_S02", False),
    "bg_rogue_chess_s2_01.png": ("ep2", "Roguechess_main_S02", True),
    "bg_rogue_chess_s3_00.jpg": ("ep3", "Roguechess_main_S03", False),
}
# Exact English labels from the supported client's strings table. All three seasons
# share one banner. The archive places the transparent chapter title over the scene.
TITLES = {
    "v2.93_rc_1_title_enUS.png": "Elf of the Abandoned Factory",
    "v3.09_rc_2_title_en.png": "The Train's Uninvited Passenger",
    "v3.25_rc_3_title_enUS.png": "The Young Lady of the Fortress City",
    "v2.93_rc_1_banner_enUS.png": "The Tale of the Tetis Hero",
}


@lru_cache(maxsize=8)
def _scene(path, checksum, texture, blur, format):
    from PIL import ImageFilter

    background = bundle_texture(path, texture).convert("RGB")
    if blur:
        background = background.filter(ImageFilter.GaussianBlur(8))
    out = BytesIO()
    background.save(out, format, **({"quality": 90} if format == "JPEG" else {}))
    return out.getvalue()


@lru_cache(maxsize=4)
def _title(text):
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default(size=52)
    except TypeError:  # Older Pillow ships a fixed-size default font.
        font = ImageFont.load_default()
    stroke = 2
    left, top, right, bottom = font.getbbox(text, stroke_width=stroke)
    image = Image.new("RGBA", (right - left + 12, bottom - top + 12))
    ImageDraw.Draw(image).text(
        (6 - left, 6 - top),
        text,
        font=font,
        fill="#fff1cd",
        stroke_width=stroke,
        stroke_fill="#202139",
    )
    if image.height < 40:
        image = image.resize((image.width * 3, image.height * 3), Image.Resampling.NEAREST)
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def missing_tetis_media(library, requested):
    if not requested or not requested.startswith(PREFIX):
        return None
    name = requested[len(PREFIX) :]
    try:
        if name in TITLES:
            return _title(TITLES[name])
        if name in SCENES:
            episode, texture, blur = SCENES[name]
            entry = library.files.get(BUNDLES + episode)
            if entry:
                return _scene(*entry, texture, blur, "PNG" if name.endswith(".png") else "JPEG")
    except (ImportError, KeyError, OSError, ValueError):
        pass
    return None
