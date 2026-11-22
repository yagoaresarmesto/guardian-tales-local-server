# SPDX-License-Identifier: Apache-2.0
"""Resolve persisted stage handles from the matching public tilemap tables."""

from .story_data import load

CATALOG = "story_handles.json"


def stage_handles(references, stage_id):
    _, stages, _ = load(references)
    stage = stages.get(str(stage_id))
    if not stage or not (references.directory / CATALOG).is_file():
        raise ValueError("No public tilemap handle catalog for this story stage")
    value = references.json(CATALOG)
    maps = value.get("tilemaps") if isinstance(value, dict) else None
    if not isinstance(maps, dict) or not isinstance(maps.get(stage["tilemap"]), dict):
        raise ValueError("No public tilemap handle catalog for this story stage")
    row = maps[stage["tilemap"]]
    for kind, handles in row.items():
        if (
            kind not in {"1", "2", "3", "10"}
            or not isinstance(handles, dict)
            or len(handles) > 254
            or any(
                not isinstance(name, str)
                or not 1 <= len(name) <= 200
                or type(index) is not int
                or not 1 <= index <= 254
                for name, index in handles.items()
            )
            or len(set(handles.values())) != len(handles)
        ):
            raise ValueError("Invalid public story tilemap handles")
    return row
