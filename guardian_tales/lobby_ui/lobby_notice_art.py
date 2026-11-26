# SPDX-License-Identifier: Apache-2.0
"""Render a published game mode snapshot as a lobby banner or a scrollable detail page."""

import json
from functools import lru_cache
from io import BytesIO

from guardian_tales.content.reference import ReferenceData

# Registered web-panel resources, with the horizontal focal point for each scene.
MODE_ART = {
    "Guild Raid": ("/map.png", None, 0.5),
    "Dungeon Kingdom Arena": ("/dka/arena-backdrop.jpg", None, 0.5),
    "Kama-ZONE": ("/kamazone/lobby.jpg", None, 0.82),
    "Expedition": ("/expedition/world-map.webp", "/expedition/emblem.png", 0.64),
    "Guild Wars": (None, "/guild-war/fortress.png", 0.5),
    "Orbital Lift": ("/orbital-lift/elevator.jpg", None, 0.93),
    "Tetis": ("/tetis/skill-tree.jpg", None, 0.78),
}


@lru_cache(maxsize=64)
def font(size, bold=False):
    from PIL import ImageFont

    names = ("segoeuib.ttf", "DejaVuSans-Bold.ttf") if bold else ("segoeui.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def panel_image(refs, path):
    from PIL import Image

    from guardian_tales.web_panel.routes import media_resource

    if path:
        source = media_resource(path)
        if source and source[1].startswith("image/"):
            try:
                with Image.open(BytesIO(source[0](refs))) as image:
                    return image.convert("RGBA")
            except (OSError, ValueError, KeyError, ImportError):
                pass
    return None


def mode_illustration(refs, mode):
    from PIL import Image, ImageDraw, ImageOps

    background, sprite, focus = MODE_ART.get(mode["name"], (None, None, 0.5))
    scene = panel_image(refs, mode.get("backdrop"))
    if scene is None:
        scene = panel_image(refs, background)
    actor = panel_image(refs, mode.get("sprite") or sprite)
    width, height = 489, 165
    tile = Image.new("RGB", (width, height), "#1c2e41")
    if scene is not None:
        # Let the illustration show on the right while preserving contrast under the labels.
        fitted = ImageOps.fit(
            scene.convert("RGB"), tile.size, Image.Resampling.LANCZOS, centering=(focus, 0.5)
        )
        ramp = bytes(round(244 * min(1, max(0, (x - 100) / 305)) ** 1.9) for x in range(width))
        tile.paste(fitted, mask=Image.frombytes("L", (width, 1), ramp).resize(tile.size))
    if actor is not None and (bounds := actor.getbbox()):
        actor = ImageOps.contain(actor.crop(bounds), (126, 132), Image.Resampling.NEAREST)
        tile.paste(actor, (width - 77 - actor.width // 2, (height - actor.height) // 2), actor)
    mask = Image.new("L", tile.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=14, fill=255)
    tile.putalpha(mask)
    return tile, scene is not None or actor is not None


def banner(directory, cards):
    from PIL import Image, ImageDraw

    from guardian_tales.web_panel.artwork import BOSSES

    image = Image.new("RGB", (1560, 680), "#101c2b")
    draw = ImageDraw.Draw(image)
    refs = ReferenceData(directory)
    white, light, gold = "#f4f7fa", "#bdd0dc", "#ffce72"

    def label(x, y, value, size, color, width, bold=False):
        face = font(size, bold)
        while draw.textlength(value, font=face) > width and size > 14:
            size -= 1
            face = font(size, bold)
        draw.text((x, y), value, font=face, fill=color, anchor="lt")

    draw.rectangle((0, 0, 1559, 7), fill=gold)
    label(44, 33, "Game mode settings", 54, white, 1100, True)
    label(1168, 58, "Move opens full settings", 24, light, 355)
    raid, *modes = cards
    draw.rounded_rectangle(
        (40, 122, 508, 646), radius=14, fill="#20364b", outline="#53748a", width=2
    )
    label(64, 148, raid["name"], 30, gold, 406, True)
    label(64, 200, raid["summary"], 45, white, 413, True)
    label(65, 258, raid["caption"], 26, light, 413)
    for i, (name, element) in enumerate(raid["details"]):
        y = 310 + i * 62
        draw.line((64, y, 480, y), fill="#40576a")
        frame = raid.get("portraits", [])[i]
        portrait = None
        if frame:
            try:
                with Image.open(BytesIO(BOSSES.read(refs, frame=frame))) as original:
                    portrait = original.convert("RGBA")
                    portrait.thumbnail((48, 48), Image.Resampling.NEAREST)
            except (OSError, KeyError, ValueError, ImportError):
                pass
        if portrait:
            image.paste(
                portrait,
                (67 + (48 - portrait.width) // 2, y + 7 + (48 - portrait.height) // 2),
                portrait,
            )
        else:
            label(68, y + 21, f"{i+1:02d}", 22, gold, 50, True)
        label(127, y + 17, name, 27, white, 247, True)
        label(386, y + 21, element, 23, light, 92)
    if raid.get("hp"):
        label(65, 587, raid["hp"], 28, gold, 409, True)
    for i, mode in enumerate(modes):
        col, row = i % 2, i // 2
        x, y = 526 + 504 * col, 122 + 180 * row
        tile, illustrated = mode_illustration(refs, mode)
        image.paste(tile, (x, y), tile)
        draw.rounded_rectangle((x, y, x + 488, y + 164), radius=14, outline="#465c72", width=2)
        text_width = 315 if illustrated else 443
        label(x + 23, y + 19, mode["name"], 24, "#a1e3f4", text_width, True)
        label(x + 23, y + 62, mode["summary"], 34, white, text_width, True)
        label(x + 23, y + 117, mode["caption"], 25, light, text_width)
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


@lru_cache(maxsize=4)
def render(directory, data, extension):
    cards = json.loads(data)
    if extension == "html":
        from .lobby_notice_details import detail_page

        return detail_page(ReferenceData(directory), cards)
    return banner(directory, cards)
