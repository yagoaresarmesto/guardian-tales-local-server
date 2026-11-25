# SPDX-License-Identifier: Apache-2.0
"""Flatten the local Solo Expedition prefab into an illustrated district map."""

import json
from functools import lru_cache
from io import BytesIO
from threading import Lock

from guardian_tales.panel_common.art_cache import cached_art
from guardian_tales.panel_common.artwork import Atlas

WORLD = Atlas("ondemand/expedition/worldmap", "expedition_worldmap")
_lock = Lock()


def resource(references, *, layout=False):
    if not WORLD.available(references):
        raise FileNotFoundError("The local Expedition world map is unavailable")
    path = WORLD.path(references)
    stat = path.stat()

    def render():
        with _lock:
            image, districts = _render(path, stat.st_mtime_ns, stat.st_size)
        return districts if layout else image

    return cached_art(path, ("expedition-map", layout), (stat.st_mtime_ns, stat.st_size), render)


def _world_point(transform, transforms, point):
    """Project a local point through the prefab hierarchy, relative to its root."""
    while transform.m_Father.path_id:
        scale, q = transform.m_LocalScale, transform.m_LocalRotation
        x, y, z = point[0] * scale.x, point[1] * scale.y, point[2] * scale.z
        # Rotate the scaled vector with the local unit quaternion.
        a, b, c = 2 * (q.y * z - q.z * y), 2 * (q.z * x - q.x * z), 2 * (q.x * y - q.y * x)
        p = transform.m_LocalPosition
        point = (
            p.x + x + q.w * a + q.y * c - q.z * b,
            p.y + y + q.w * b + q.z * a - q.x * c,
            p.z + z + q.w * c + q.x * b - q.y * a,
        )
        transform = transforms[transform.m_Father.path_id]
    return point


def _paste_sprite(canvas, sprite, corners):
    """Draw a transformed native sprite using its top-left, top-right and bottom-left."""
    from PIL import Image

    (x, y), (right, top), (left, bottom) = corners
    a, b, c, d = right - x, top - y, left - x, bottom - y
    determinant = a * d - b * c
    if abs(determinant) < 1:
        return
    x0, y0 = max(0, int(min(x, right, left, right + c))), max(0, int(min(y, top, bottom, top + d)))
    x1 = min(canvas.width, int(max(x, right, left, right + c)) + 1)
    y1 = min(canvas.height, int(max(y, top, bottom, top + d)) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    w, h = sprite.size
    u, v, s, t = (
        d * w / determinant,
        -c * w / determinant,
        -b * h / determinant,
        a * h / determinant,
    )
    inverse = (u, v, u * (x0 - x) + v * (y0 - y), s, t, s * (x0 - x) + t * (y0 - y))
    tile = sprite.transform(
        (x1 - x0, y1 - y0), Image.Transform.AFFINE, inverse, Image.Resampling.BILINEAR
    )
    canvas.paste(tile, (x0, y0), tile)


def _landmark(canvas, mesh, atlas, transform, project):
    """The cave and volcano use horizontal pairs of mesh vertices for their relief."""
    from UnityPy.helpers.MeshHelper import MeshHandler

    data = MeshHandler(mesh)
    data.process()
    rows = {}
    for vertex, (u, v) in zip(data.m_Vertices, data.m_UV0, strict=True):
        rows.setdefault(v, []).append((u, project(transform, vertex)))
    strips = sorted(rows.items(), reverse=True)
    for (v1, upper), (v2, lower) in zip(strips, strips[1:]):
        (u1, tl), (u2, tr) = sorted(upper)
        bl = min(lower)[1]
        box = (
            round(u1 * atlas.width),
            round((1 - v1) * atlas.height),
            round(u2 * atlas.width),
            round((1 - v2) * atlas.height),
        )
        _paste_sprite(canvas, atlas.crop(box), (tl, tr, bl))


def _districts_and_visibility(behaviours, objects, by_object, transforms):
    districts = {}
    hidden = {key for key, obj in objects.items() if not obj.m_IsActive}
    for obj in behaviours:
        data = obj.read_typetree()
        if "districtSpecId" in data:
            t = by_object[data["m_GameObject"]["m_PathID"]]
            districts[data["districtSpecId"]] = _world_point(t, transforms, (0, 0, 0))[:2]
        if "cloudCurtain" in data:
            # These are the progression fog layers. The editor shows the entire region.
            hidden.add(data["cloudCurtain"]["m_PathID"])
        if variants := data.get("matchingUis"):
            # Use the final narrative appearance consistently in the fully revealed map.
            hidden.update(item["uiObject"]["m_PathID"] for item in variants)
            last = max(variants, key=lambda item: item["narrativeId"])
            hidden.discard(last["uiObject"]["m_PathID"])
    if not districts:
        raise ValueError("No Expedition district gates in the local world map")
    return districts, hidden


def _sprite_layers(renderers, by_object, transforms, hidden):
    layers = []
    for obj in renderers:
        renderer = obj.read()
        if not renderer.m_Enabled or not renderer.m_Sprite.path_id:
            continue
        transform = by_object[renderer.m_GameObject.path_id]
        ancestor = transform
        while ancestor.m_GameObject.path_id not in hidden and ancestor.m_Father.path_id:
            ancestor = transforms[ancestor.m_Father.path_id]
        if ancestor.m_GameObject.path_id in hidden:
            continue
        depth = _world_point(transform, transforms, (0, 0, 0))[2]
        layers.append(
            (
                bool(renderer.m_SortingLayerID),
                renderer.m_SortingOrder,
                -depth,
                obj.path_id,
                renderer,
                transform,
            )
        )
    return sorted(layers)


def _draw_sprite(canvas, renderer, transform, project, sprites):
    key = renderer.m_Sprite.path_id
    if key not in sprites:
        sprite = renderer.m_Sprite.read()
        sprites[key] = (sprite, sprite.image.convert("RGBA"))
    sprite, pixels = sprites[key]
    w, h = (
        sprite.m_Rect.width / sprite.m_PixelsToUnits,
        sprite.m_Rect.height / sprite.m_PixelsToUnits,
    )
    x, y = -sprite.m_Pivot.x * w, (1 - sprite.m_Pivot.y) * h
    corners = []
    for sx, sy in ((x, y), (x + w, y), (x, y - h)):
        point = (-sx if renderer.m_FlipX else sx, -sy if renderer.m_FlipY else sy, 0)
        corners.append(project(transform, point))
    _paste_sprite(canvas, pixels, corners)


@lru_cache(maxsize=1)
def _render(path, mtime_ns, size):
    import UnityPy
    from PIL import Image

    scene = UnityPy.load(str(path))
    by_type = {}
    for obj in scene.objects:
        by_type.setdefault(obj.type.name, []).append(obj)
    transforms = {o.path_id: o.read() for o in by_type["Transform"] + by_type["RectTransform"]}
    by_object = {t.m_GameObject.path_id: t for t in transforms.values()}
    objects = {o.path_id: o.read() for o in by_type["GameObject"]}
    textures = {o.peek_name(): o for o in by_type["Texture2D"]}
    districts, hidden = _districts_and_visibility(
        by_type["MonoBehaviour"], objects, by_object, transforms
    )
    xs, ys = zip(*districts.values())
    left, right = min(xs) - 2.35, max(xs) + 1.95
    top, bottom = max(ys) + 2.25, min(ys) - 2.4
    density = 100
    width, height = round((right - left) * density), round((top - bottom) * density)

    def screen(point):
        return ((point[0] - left) * density, (top - point[1]) * density)

    def project(transform, point):
        return screen(_world_point(transform, transforms, point))

    canvas = Image.new("RGB", (width, height), "#bba781")
    atlas = textures["expedition_worldmap"].read().image.convert("RGBA")
    terrain_meshes = []
    for obj in by_type["MeshFilter"]:
        part = obj.read()
        go_id = part.m_GameObject.path_id
        transform = by_object[go_id]
        name = objects[go_id].m_Name
        if name == "plane":
            # The native sky material spans Unity's built-in 10 by 10 plane.
            corners = [
                project(transform, corner) for corner in ((5, 0, -5), (-5, 0, -5), (5, 0, 5))
            ]
            _paste_sprite(canvas, textures["background"].read().image.convert("RGBA"), corners)
        elif name in ("cave", "volcano"):
            terrain_meshes.append((part.m_Mesh, transform))
    sprites = {}
    layers = _sprite_layers(by_type["SpriteRenderer"], by_object, transforms, hidden)
    for foreground, _, _, _, renderer, transform in layers:
        # Both relief meshes sit above the islands and beneath the foreground sprites.
        if foreground and terrain_meshes:
            for mesh, placement in terrain_meshes:
                _landmark(canvas, mesh.read(), atlas, placement, project)
            terrain_meshes.clear()
        _draw_sprite(canvas, renderer, transform, project, sprites)
    output = BytesIO()
    canvas.save(output, format="WEBP", quality=88, method=4)
    pins = []
    for ident, point in sorted(districts.items()):
        x, y = screen(point)
        pins.append({"id": ident, "x": round(x / width, 6), "y": round(y / height, 6)})
    layout = {"width": width, "height": height, "districts": pins}
    return output.getvalue(), json.dumps(layout, separators=(",", ":")).encode()
