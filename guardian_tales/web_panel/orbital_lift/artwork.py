# SPDX-License-Identifier: Apache-2.0
"""Render the panel header from the installed Orbital Lift elevator scene."""

from functools import lru_cache
from io import BytesIO

from guardian_tales.panel_common.artwork import decoder_available


def banner(references):
    path = references.directory.parent / "resources/files/AssetBundles/Android/ui/tower/elevator"
    if not path.is_file() or not decoder_available():
        raise FileNotFoundError("Orbital Lift scene artwork unavailable")
    stat = path.stat()
    return _banner(path, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=2)
def _banner(path, mtime_ns, size):
    import UnityPy
    from PIL import Image

    placement = (
        ("star2", (93, 93), (750, 18)),
        ("cable", (5, 190), (984, 0)),
        ("cable", (5, 190), (1072, 0)),
        ("room_a_back", (185, 47), (938, 62)),
        ("room_a", (210, 47), (926, 62)),
        ("highlight_a", (205, 44), (928, 63)),
    )
    names = {"c"} | {name for name, _, _ in placement}
    layers = {
        obj.peek_name(): obj
        for obj in UnityPy.load(str(path)).objects
        if obj.type.name == "Sprite" and obj.peek_name() in names
    }
    horizon = layers["c"].read().image.resize((1200, 276), Image.Resampling.BICUBIC)
    scene = horizon.crop((0, 0, 1200, 190)).convert("RGBA")
    for name, bounds, position in placement:
        sprite = layers[name].read().image.convert("RGBA").resize(bounds, Image.Resampling.NEAREST)
        scene.alpha_composite(sprite, position)
    output = BytesIO()
    scene.convert("RGB").save(output, format="JPEG", quality=88)
    return output.getvalue()
