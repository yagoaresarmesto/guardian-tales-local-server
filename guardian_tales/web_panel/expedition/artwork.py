# SPDX-License-Identifier: Apache-2.0
"""Read the Expedition journal illustrations and stage markers from the local UI bundle."""

from functools import lru_cache
from io import BytesIO

from guardian_tales.panel_common.art_cache import cached_art
from guardian_tales.panel_common.artwork import Atlas, bundle_texture

from ..artwork import EXPEDITION

MARKERS = Atlas(EXPEDITION.bundle, "Expedition")
SCENES = {
    "journey": ("expedition_bg_event_clara_smile_set_01", (960, 370), (0.5, 0.38)),
    "camp": ("expedition_bg_forest_night", (480, 180), (0.5, 0.63)),
}


def scene(references, *, name):
    if not EXPEDITION.available(references):
        raise FileNotFoundError("The local Expedition UI bundle and panel-art extra are required")
    path = EXPEDITION.path(references)
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    return cached_art(path, ("journal", name), stamp, lambda: _scene(path, *stamp, name))


@lru_cache(maxsize=4)
def _scene(path, mtime_ns, size, name):
    from PIL import Image, ImageOps

    texture, bounds, center = SCENES[name]
    pixels = bundle_texture(path, texture)
    image = ImageOps.fit(pixels, bounds, Image.Resampling.LANCZOS, centering=center)
    output = BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=82)
    return output.getvalue()
