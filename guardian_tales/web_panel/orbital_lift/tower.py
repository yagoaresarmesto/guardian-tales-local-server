# SPDX-License-Identifier: Apache-2.0
"""Read-only tower scenery and encounter previews from the installed client."""

import hashlib
import json
from functools import lru_cache
from io import BytesIO
from threading import Lock

from guardian_tales.orbital import LAST_SELECTABLE_FLOOR
from guardian_tales.orbital_levels import floor_data
from guardian_tales.panel_common.artwork import decoder_available
from guardian_tales.panel_common.labels import english_labels
from guardian_tales.raid_static import decode, records
from guardian_tales.reference import ReferenceData

BACKDROPS = {"a", "a1", "c", "mars-bg", "mars-main_bg", "mars-bottom"}
SCENERY = BACKDROPS | {
    "satellite",
    "satellite_back",
    "base_castle",
    "ic_tower1000_clear_00",
    "star2",
}
_FRAMES = SCENERY | {
    "stars",
    "base_back",
    "room_a",
    "room_a_back",
    "room_x",
    "room_x_back",
    "room_a_disable",
    "room_x_disable",
    "highlight_a",
    "highlight_x",
    "cable",
    "cable_b",
    *(f"number-{digit}" for digit in range(10)),
}
_lock = Lock()


def scene(references, *, name="tower"):
    path = references.directory.parent / "resources/files/AssetBundles/Android/ui/tower/elevator"
    if not path.is_file() or not decoder_available():
        raise FileNotFoundError("Orbital Lift scene artwork unavailable")
    stat = path.stat()
    with _lock:
        return _atlas(path, stat.st_mtime_ns, stat.st_size)[name]


def _webp(image, *, quality=84, lossless=False):
    out = BytesIO()
    image.save(out, format="WEBP", quality=quality, lossless=lossless, method=4)
    return out.getvalue()


@lru_cache(maxsize=1)
def _atlas(path, mtime, size):
    import UnityPy
    from PIL import Image

    sprites = {
        obj.peek_name(): obj
        for obj in UnityPy.load(str(path)).objects
        if obj.type.name == "Sprite" and obj.peek_name() in _FRAMES
    }
    if sprites.keys() != _FRAMES:
        raise ValueError("Incomplete Orbital Lift scene")
    pixels = {name: sprite.read().image.convert("RGBA") for name, sprite in sprites.items()}
    scenery = {name: _webp(pixels.pop(name), lossless=name not in BACKDROPS) for name in SCENERY}
    frames = {}
    x = y = row_height = 0
    width = 1024
    for name, image in sorted(pixels.items(), key=lambda item: -item[1].height):
        if x + image.width > width:
            x, y, row_height = 0, y + row_height + 2, 0
        frames[name] = (x, y, image.width, image.height)
        row_height = max(row_height, image.height)
        x += image.width + 2
    atlas = Image.new("RGBA", (width, y + row_height))
    for name, (x, y, _, _) in frames.items():
        atlas.paste(pixels[name], (x, y))
    scenery["tower"] = _webp(atlas, lossless=True)
    scenery["frames"] = json.dumps(frames, separators=(",", ":")).encode()
    return scenery


def encounters(references):
    return _encounters(references.read_bytes("static_data_get.bin"), references.directory)


@lru_cache(maxsize=1)
def _encounters(source, directory):
    _, tables = records(decode(source))
    floors, _ = floor_data(tables)
    preview = []
    reward_sets = {}
    for row in sorted(floors, key=lambda row: row["Floor"]):
        if row["Floor"] <= LAST_SELECTABLE_FLOOR:
            rewards = tuple((r["ItemId"], r["Amount"]) for r in row.get("Rewards", []))
            reward_index = reward_sets.setdefault(rewards, len(reward_sets))
            preview.append((row["FloorType"], row["StandardLevel"] + 1, reward_index))
    used = {item for rewards in reward_sets for item, _ in rewards}
    names = (
        {row["Id"]: row["Name"] for row in json.loads(tables["items"][1]) if row["Id"] in used}
        if "items" in tables
        else {}
    )
    labels = english_labels(
        ReferenceData(directory), hashlib.sha256(source).hexdigest(), set(names.values())
    )
    return {
        "floors": preview,
        "rewardSets": list(reward_sets),
        "items": {
            key: labels.get(name, name.replace("_", " ").title()) for key, name in names.items()
        },
    }
