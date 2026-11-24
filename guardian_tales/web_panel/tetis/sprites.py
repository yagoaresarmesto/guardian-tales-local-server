# SPDX-License-Identifier: Apache-2.0
"""Native NGUI specialty and spell icons from the installed Tetis UI bundle."""

from functools import lru_cache
from threading import Lock

from ...panel_common.artwork import decoder_available, frame_png

_lock = Lock()


@lru_cache(maxsize=2)
def _sheet(path, stamp, atlas):
    import UnityPy

    name = f"roguechess{atlas}"
    bundle = UnityPy.load(str(path))
    prefab = bundle.container[f"assets/ondemand/roguechess/ui/spritesheets/{atlas}/{name}.prefab"]
    components = (pair.component.read() for pair in prefab.read().m_Component)
    sprites = next(component.mSprites for component in components if hasattr(component, "mSprites"))
    texture = next(
        obj
        for obj in bundle.objects
        if obj.type.name == "Texture2D" and obj.peek_name().lower() == name
    )
    return texture.read().image.convert("RGBA"), {row.name: row for row in sprites}


@lru_cache(maxsize=100)
def _png(path, stamp, atlas, frame):
    pixels, sprites = _sheet(path, stamp, atlas)
    if frame not in sprites:
        raise FileNotFoundError("Tetis sprite unavailable")
    row = sprites[frame]
    return frame_png(
        pixels,
        {
            "frame": {"x": row.x, "y": row.y, "w": row.width, "h": row.height},
            "rotated": False,
            "spriteSourceSize": {
                "x": row.paddingLeft,
                "y": row.paddingTop,
                "w": row.width,
                "h": row.height,
            },
            "sourceSize": {
                "w": row.width + row.paddingLeft + row.paddingRight,
                "h": row.height + row.paddingTop + row.paddingBottom,
            },
        },
    )


def read(references, *, atlas, frame):
    path = (
        references.directory.parent / "resources/files/AssetBundles/Android/ondemand/roguechess/ui"
    )
    if not path.is_file() or not decoder_available():
        raise FileNotFoundError(
            "Install the Tetis UI bundle and panel-art extra to view specialties"
        )
    stat = path.stat()
    with _lock:
        return _png(path, (stat.st_mtime_ns, stat.st_size), atlas, frame)
