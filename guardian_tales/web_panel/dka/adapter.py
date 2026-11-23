# SPDX-License-Identifier: Apache-2.0
"""Dungeon Kingdom Arena practice adapter."""

from ... import punchking, punchking_static
from . import sprites


def arena_image(references):
    return (
        references.directory.parent
        / "resources/files/media/guildpunchking/guild_punchking_bg_00.jpg"
    )


def state(references):
    catalog = punchking.load_catalog(references)
    selection = punchking_static.load_selection(references)
    return {
        "variants": sorted(catalog["variants"], key=lambda variant: variant["id"]),
        "active": {"variant": selection["variant"], "day": selection["day"]} if selection else None,
        "revision": selection["static_data_revision"] if selection else 0,
        "hasArt": arena_image(references).is_file(),
        "hasSlimeSprites": sprites.available(references),
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
