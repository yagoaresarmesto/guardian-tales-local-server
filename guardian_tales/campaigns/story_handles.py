# SPDX-License-Identifier: Apache-2.0
"""Resolve stage handles and interaction definitions from the matching client data."""

import json
from functools import lru_cache

from guardian_tales.modes.guild.raid_static import decode, records

CATALOG = "story_handles.json"
EVENT_CATALOG = "story_map_events.json"
CATEGORIES = {
    "General": "1",
    "PurpleCoin": "2",
    "StarPiece": "3",
    "Item": "4",
    "Box": "5",
    "Flag": "6",
    "Exit": "7",
    "Gatherable": "8",
    "Monster": "10",
    "Waypoint": "11",
}


@lru_cache(maxsize=2)
def _tables(path, stamp, size):
    _, tables = records(decode(path.read_bytes()))

    def rows(name, default):
        return json.loads(tables[name][1]) if name in tables else default

    stages = rows("stages", [])
    enhancement = rows("weaponenhance", {})
    return {
        "maps": {
            r["Id"]: r["Tilemap"]["Default"]
            for r in stages
            if isinstance(r.get("Tilemap"), dict) and r["Tilemap"].get("Default")
        },
        "stage_ids": {r["Name"]: r["Id"] for r in stages if r.get("Name")},
        "metadata": rows("stagemetaitem", {}),
        "followers": rows("followers", {}),
        "world_pass": rows("worldpass", {}),
        "merch_levels": rows("merch", {}).get("MerchLevels", []),
        "constants": rows("constants", {}),
        "revive_limits": {r["Id"]: r.get("ReviveLimitCount", -1) for r in stages},
        "items": {r["Id"]: r for r in rows("items", [])},
        "weapon_levels": enhancement.get("LevelExps.Kong") or enhancement.get("LevelExps") or [],
    }


def catalog(references):
    path = references.directory / "static_data_get.bin"
    if not path.is_file():
        return {}
    stat = path.stat()
    return _tables(path, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _tilemaps(path, stamp, size):
    data = json.loads(path.read_bytes())
    if not isinstance(data, dict) or not isinstance(data.get("tilemaps"), dict):
        raise ValueError("Invalid public story tilemap catalog")
    return data["tilemaps"]


def _map_row(references, filename, tilemap, required=False):
    path = references.directory / filename
    if path.is_file():
        stat = path.stat()
        row = _tilemaps(path, stat.st_mtime_ns, stat.st_size).get(tilemap)
        if isinstance(row, dict):
            return row
    if required:
        raise ValueError(f"Missing {filename} entry for story map {tilemap}")
    return {}


def metadata(references, stage_id):
    tables = catalog(references)
    return tables.get("metadata", {}).get(tables.get("maps", {}).get(stage_id), {})


def map_events(references, stage_id, *, required=False):
    tilemap = catalog(references).get("maps", {}).get(stage_id)
    return _map_row(references, EVENT_CATALOG, tilemap, required)


def stage_handles(references, stage_id):
    tilemap = catalog(references).get("maps", {}).get(stage_id)
    row = dict(_map_row(references, CATALOG, tilemap))
    for key, names in metadata(references, stage_id).get("HandleNames", {}).items():
        if key in CATEGORIES:
            row[CATEGORIES[key]] = {
                name: i for i, name in enumerate(names) if i and name and i <= 254
            }
    if not tilemap or not row:
        raise ValueError("No public tilemap handle catalog for this story stage")
    for kind, handles in row.items():
        if (
            kind not in CATEGORIES.values()
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
