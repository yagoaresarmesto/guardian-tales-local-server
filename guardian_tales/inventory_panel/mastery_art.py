# SPDX-License-Identifier: Apache-2.0
"""Render a still of the mastery training room from the installed 3.57.0 artwork."""

from functools import lru_cache
from io import BytesIO

from guardian_tales.panel_common.art_cache import cached_art
from guardian_tales.panel_common.artwork import decoder_available

_BASE_POSE = (
    "[base]legL",
    "[base]legR",
    "[base]body",
    "[base]elbowL",
    "[base]elbowR",
    "[base]armL",
    "[base]armR",
    "[base]head",
)
_ACTORS = {
    "ice_hockey_fan": (
        "side",
        ("bag", "hair", *_BASE_POSE, "face/[base]idle", "helmR"),
        229,
        152,
        1.65,
    ),
    "forest_elf_tree_elf": (
        "front",
        ("hairB", *_BASE_POSE, "face/[base]idle"),
        704,
        158,
        1.48,
    ),
    "blond_knight": ("front", ("cloak", "hair", *_BASE_POSE, "face/[base]idle"), 924, 122, 1.15),
}


def sprite_pose(objects, sheet, layers):
    """Place trimmed atlas regions back on their original shared pose canvas."""
    from PIL import Image

    pixels = objects[sheet].read().image.convert("RGBA")
    regions = {}
    for line in objects[sheet + ".atlas"].read().m_Script.splitlines():
        if line and not line.startswith(" ") and ":" not in line:
            region = regions[line] = {}
        elif line.startswith("  "):
            key, value = line.strip().split(": ", 1)
            region[key] = value

    def pair(region, key):
        return tuple(map(int, region[key].split(",")))

    pose = None
    for name in layers:
        part = regions[name]
        x, y = pair(part, "xy")
        w, h = pair(part, "size")
        dx, dy = pair(part, "offset")
        rotated = part["rotate"] == "true"
        sprite = pixels.crop((x, y, x + (h if rotated else w), y + (w if rotated else h)))
        if rotated:
            sprite = sprite.transpose(Image.Transpose.ROTATE_270)
        width, height = pair(part, "orig")
        if pose is None:
            pose = Image.new("RGBA", (width, height))
        pose.alpha_composite(sprite, (dx, height - dy - h))
    return pose.crop(pose.getbbox())


def training_banner(references):
    root = references.directory.parent / "resources/files/AssetBundles/Android"
    lobby = root / "ui/lobby"
    if not lobby.is_file() or not decoder_available():
        raise FileNotFoundError("The imported training room artwork is unavailable.")
    bundles = (root / "characters" / name for name in _ACTORS)
    actors = []
    for path in bundles:
        if path.is_file():
            stat = path.stat()
            actors.append((path, stat.st_mtime_ns, stat.st_size))
    stat = lobby.stat()
    revision = (stat.st_mtime_ns, stat.st_size, [(p.name, m, s) for p, m, s in actors])
    return cached_art(
        lobby,
        "mastery-training",
        revision,
        lambda: _banner(lobby, stat.st_mtime_ns, stat.st_size, tuple(actors)),
    )


@lru_cache(maxsize=2)
def _banner(lobby, lobby_revision, lobby_size, actors):
    import UnityPy
    from PIL import Image

    def sheets(path, names):
        return {
            obj.peek_name(): obj
            for obj in UnityPy.load(str(path)).objects
            if obj.type.name in ("Texture2D", "TextAsset") and obj.peek_name() in names
        }

    props = ("treadmill", "ologram_puppet", "electric_pressure")
    objects = sheets(lobby, {"GuardianBasecamp", *props, *(p + ".atlas" for p in props)})
    # The 3.57.0 lobby packs the full-width room above the base camp UI icons.
    atlas = objects["GuardianBasecamp"].read().image
    if atlas.size != (2048, 256):
        raise FileNotFoundError("Unknown base camp texture layout.")
    scene = atlas.convert("RGBA").crop((320, 0, 1423, 176))

    def place(sprite, center, floor, scale):
        sprite = sprite.resize(
            (round(sprite.width * scale), round(sprite.height * scale)), Image.Resampling.NEAREST
        )
        scene.alpha_composite(sprite, (center - sprite.width // 2, floor - sprite.height))

    belt = sprite_pose(
        objects,
        "treadmill",
        [
            "side/[base]body",
            "side/bodyrolling_1",
            "side/safetybarL",
            "side/safetybarR",
            "side/headon",
        ],
    )
    place(belt, 261, 165, 1.75)
    hologram = sprite_pose(
        objects,
        "ologram_puppet",
        [
            "side/bottomplate",
            "side/bottomplate2",
            "side/pelvis",
            "side/[base]body",
            "side/[base]elbowL",
            "side/[base]elbowR",
            "side/[base]armL",
            "side/[base]armR",
            "side/[base]head",
        ],
    )
    place(hologram, 638, 162, 1.75)
    capsule = sprite_pose(
        objects,
        "electric_pressure",
        [
            "front/bodyB",
            "front/bodyTB",
            "front/bodyLB",
            "front/bodyRB",
            "front/glass",
            "front/bodyT",
            "front/bodyL",
            "front/bodyR",
            "front/bodyF",
            "front/bodyF2",
            "front/bodyF2_0",
            "front/body2",
            "front/body2_eff",
        ],
    )
    place(capsule, 924, 169, 1.47)
    for path, _, _ in actors:
        hero = path.name
        direction, layers, center, floor, scale = _ACTORS[hero]
        sheets_for_hero = sheets(path, {hero, hero + ".atlas"})
        if hero in sheets_for_hero and hero + ".atlas" in sheets_for_hero:
            place(
                sprite_pose(sheets_for_hero, hero, [direction + "/" + part for part in layers]),
                center,
                floor,
                scale,
            )
    out = BytesIO()
    scene.save(out, "PNG")
    return out.getvalue()
