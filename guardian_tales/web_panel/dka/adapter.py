# SPDX-License-Identifier: Apache-2.0
"""Dungeon Kingdom Arena practice adapter."""

from importlib.util import find_spec
from io import BytesIO

from guardian_tales.modes.guild import punchking, punchking_static
from guardian_tales.panel_common.art_cache import cached_art

from ..artwork import BOSSES, UI


def arena_image(references):
    return (
        references.directory.parent
        / "resources/files/media/guildpunchking/guild_punchking_bg_00.jpg"
    )


def arena_backdrop(references):
    return arena_image(references).with_name("guild_punchking_ui_bg_00.png")


def backdrop_jpeg(references):
    try:
        from PIL import Image
    except ImportError as error:
        raise FileNotFoundError("Arena backdrop decoder unavailable") from error

    path = arena_backdrop(references)
    stat = path.stat()

    def render():
        with Image.open(path) as image:
            output = BytesIO()
            image.convert("RGB").save(output, "JPEG", quality=85)
            return output.getvalue()

    return cached_art(path, "arena-backdrop", (stat.st_mtime_ns, stat.st_size), render)


def state(references):
    catalog = punchking.load_catalog(references)
    selection = punchking_static.load_selection(references)
    return {
        "variants": sorted(catalog["variants"], key=lambda variant: variant["id"]),
        "active": {"variant": selection["variant"], "day": selection["day"]} if selection else None,
        "revision": selection["static_data_revision"] if selection else 0,
        "hasArt": arena_image(references).is_file(),
        "hasBackdrop": arena_backdrop(references).is_file() and find_spec("PIL") is not None,
        "hasElementIcons": UI.available(references),
        "hasSlimeSprites": BOSSES.available(references),
    }


def apply(references, body):
    if (
        not isinstance(body, dict)
        or body.keys() != {"variant", "day", "revision"}
        or not punchking.integer(body["revision"])
    ):
        raise ValueError("Choose an arena variant and day using the current revision")
    punchking_static.select(
        references, body["variant"], body["day"], expected_revision=body["revision"]
    )
