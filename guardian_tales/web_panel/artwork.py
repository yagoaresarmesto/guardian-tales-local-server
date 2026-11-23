# SPDX-License-Identifier: Apache-2.0
"""Read individual PNGs from the panel's fixed local TexturePacker atlases."""

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.util import find_spec
from io import BytesIO
from threading import Lock


@dataclass(frozen=True)
class Atlas:
    bundle: str
    sheet: str

    def path(self, references):
        return references.directory.parent / "resources/files/AssetBundles/Android" / self.bundle

    def available(self, references):
        return self.path(references).is_file() and find_spec("UnityPy") is not None

    def read(self, references, *, frame):
        if not self.available(references):
            raise FileNotFoundError("The local sprite atlas and panel-art extra are required")
        path = self.path(references)
        stat = path.stat()
        # Concurrent image requests share one decoded sheet per bundle version.
        with _lock:
            return _read_png(path, self.sheet, stat.st_mtime_ns, stat.st_size, frame)


BOSSES = Atlas("spritesheets/bosses", "bosses")
UI = Atlas("spritesheets/ui/main_s3", "MainUiS3")
WAR = Atlas("ondemand/guild_war/ui", "guildWar")
ELEMENT_FRAMES = {
    "basic": "ic_attribute_no",
    "dark": "ic_attribute_dark",
    "earth": "ic_attribute_ground",
    "fire": "ic_attribute_fire",
    "light": "ic_attribute_light",
    "water": "ic_attribute_water",
    "space": "ic_attribute_nebula",
}
_lock = Lock()


def frame_png(sheet, entry):
    from PIL import Image

    frame = entry["frame"]
    x, y, w, h = (frame[k] for k in ("x", "y", "w", "h"))
    if not (0 <= x < x + w <= sheet.width and 0 <= y < y + h <= sheet.height):
        raise ValueError("Sprite frame is outside its atlas")
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
        raise ValueError("Invalid sprite trim in the atlas")
    icon = Image.new("RGBA", (width, height))
    icon.paste(pixels, (trim["x"], trim["y"]))
    output = BytesIO()
    icon.save(output, format="PNG")
    return output.getvalue()


@lru_cache(maxsize=3)
def _read_sheet(path, sheet, mtime_ns, size):
    import UnityPy

    objects = {
        obj.type.name: obj
        for obj in UnityPy.load(str(path)).objects
        if obj.type.name in ("TextAsset", "Texture2D") and obj.peek_name() == sheet
    }
    frames = json.loads(objects["TextAsset"].read().m_Script)["frames"]
    pixels = objects["Texture2D"].read().image.convert("RGBA")
    return pixels, frames


@lru_cache(maxsize=64)
def _read_png(path, sheet, mtime_ns, size, frame):
    pixels, frames = _read_sheet(path, sheet, mtime_ns, size)
    if frame not in frames:
        raise FileNotFoundError("Frame unavailable in the local atlas")
    return frame_png(pixels, frames[frame])
