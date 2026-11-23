# SPDX-License-Identifier: Apache-2.0
"""Read the original 3.57 DKA portraits from the local bosses sprite atlas."""

import json
from functools import lru_cache
from importlib.util import find_spec
from io import BytesIO
from threading import Lock

# SpriteName.default on the monsters used by the three practice variants.
FRAMES = {
    "basic": "punchking_boss_slime.none",
    "light": "punchking_boss_slime.light",
    "dark": "punchking_boss_slime.darkness",
    "fire": "boss_lava_slime_king",
    "water": "punchking_boss_slime.ice",
    "earth": "punchking_boss_slime.earth",
    "space": "punchking_boss_slime.super",
}
_lock = Lock()


def bundle_path(references):
    return references.directory.parent / "resources/files/AssetBundles/Android/spritesheets/bosses"


def available(references):
    return bundle_path(references).is_file() and find_spec("UnityPy") is not None


def frame_png(sheet, entry):
    from PIL import Image

    frame = entry["frame"]
    x, y, w, h = (frame[k] for k in ("x", "y", "w", "h"))
    if not (0 <= x < x + w <= sheet.width and 0 <= y < y + h <= sheet.height):
        raise ValueError("Slime frame is outside the bosses atlas")
    pixels = sheet.crop((x, y, x + w, y + h))
    if entry["rotated"]:
        pixels = pixels.transpose(Image.Transpose.ROTATE_90)
    source, trim = entry["sourceSize"], entry["spriteSourceSize"]
    width, height = source["w"], source["h"]
    if (
        not 0 < width <= sheet.width
        or not 0 < height <= sheet.height
        or pixels.size != (trim["w"], trim["h"])
        or not 0 <= trim["x"] <= width - pixels.width
        or not 0 <= trim["y"] <= height - pixels.height
    ):
        raise ValueError("Invalid slime portrait trim in the bosses atlas")
    icon = Image.new("RGBA", (width, height))
    icon.paste(pixels, (trim["x"], trim["y"]))
    output = BytesIO()
    icon.save(output, format="PNG")
    return output.getvalue()


@lru_cache(maxsize=1)
def _read_icons(path, mtime_ns, size):
    import UnityPy

    objects = {
        obj.type.name: obj
        for obj in UnityPy.load(str(path)).objects
        if obj.type.name in ("TextAsset", "Texture2D") and obj.peek_name() == "bosses"
    }
    frames = json.loads(objects["TextAsset"].read().m_Script)["frames"]
    sheet = objects["Texture2D"].read().image.convert("RGBA")
    return {element: frame_png(sheet, frames[name]) for element, name in FRAMES.items()}


def read(references, *, element):
    if not available(references):
        raise FileNotFoundError("The local bosses atlas and panel-art extra are required")
    path = bundle_path(references)
    stat = path.stat()
    # Seven image requests can arrive together on the first page load.
    with _lock:
        return _read_icons(path, stat.st_mtime_ns, stat.st_size)[element]
