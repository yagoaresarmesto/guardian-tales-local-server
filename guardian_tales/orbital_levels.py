# SPDX-License-Identifier: Apache-2.0
"""Serve a uniform enemy level for Orbital Lift floors without changing the save."""

import json
from functools import lru_cache

from .orbital import LAST_SELECTABLE_FLOOR
from .punchking_static import atomic_write
from .raid_static import compress, decode, digest, records
from .state_lock import StateLock
from .village import integer

SELECTION = "orbital_enemy_level.json"
TABLE = "infinitytowerfloors"


class LevelChanged(ValueError):
    pass


def settings(references):
    path = references.directory / SELECTION
    if not path.exists():
        return {"level": None, "revision": 0, "boards": {}}
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Invalid Orbital Lift enemy level settings.")
    data = json.loads(path.read_bytes())
    if (
        not isinstance(data, dict)
        or set(data) not in ({"level", "revision"}, {"level", "revision", "boards"})
        or not isinstance(data.get("boards", {}), dict)
        or not integer(data["revision"], minimum=1)
        or data["level"] is not None
        and not integer(data["level"], minimum=1)
    ):
        raise ValueError("Invalid Orbital Lift enemy level settings.")
    data.setdefault("boards", {})
    return data


def selection(references):
    data = settings(references)
    return data["level"], data["revision"]


def bootstrap_selection(references):
    data = settings(references)
    return (
        data["level"],
        json.dumps(data["boards"], sort_keys=True) if data["boards"] else "",
    ), data["revision"]


def prepare_selection(source, value, revision):
    return prepare(source, value[0], revision, value[1])


def floor_data(tables):
    if not {TABLE, "exps2", "__checksum__"} <= tables.keys():
        raise ValueError("The Orbital Lift floor and experience tables are required.")
    floors = json.loads(tables[TABLE][1])
    experience = json.loads(tables["exps2"][1])
    levels = experience.get("LevelExps") if isinstance(experience, dict) else None
    if (
        not isinstance(levels, list)
        or not isinstance(floors, list)
        or any(
            not isinstance(row, dict)
            or not integer(row.get("Floor"), maximum=LAST_SELECTABLE_FLOOR + 1, minimum=1)
            or not integer(row.get("StandardLevel"), maximum=len(levels) - 1)
            for row in floors
        )
    ):
        raise ValueError("Invalid Orbital Lift floor or enemy level.")
    if sorted(row["Floor"] for row in floors) != list(range(1, LAST_SELECTABLE_FLOOR + 2)):
        raise ValueError("The complete 3.57.0 Orbital Lift floor catalog is required.")
    # The native StandardLevel is zero-based. Use this mode's highest original
    # visible level, including its final record room, rather than the global cap.
    return floors, max(row["StandardLevel"] for row in floors) + 1


@lru_cache(maxsize=1)
def max_level(source):
    _, tables = records(decode(source))
    return floor_data(tables)[1]


def check_level(level, maximum):
    if level is not None and not integer(level, maximum=maximum, minimum=1):
        raise ValueError(f"Choose an enemy level from 1 to {maximum}.")


def state(references):
    maximum = max_level(references.read_bytes("static_data_get.bin"))
    level, revision = selection(references)
    check_level(level, maximum)
    return {"level": level, "maxLevel": maximum, "revision": revision}


@lru_cache(maxsize=2)
def prepare(source, level, revision, boards=""):
    lines, tables = records(decode(source))
    floors, maximum = floor_data(tables)
    check_level(level, maximum)
    content = tables[TABLE][1]
    if level is not None or boards:
        for row in floors:
            if level is not None and row["Floor"] <= LAST_SELECTABLE_FLOOR:
                row["StandardLevel"] = level - 1
        if boards:
            from .orbital_boards import apply_overrides

            apply_overrides(floors, json.loads(boards), tables, maximum)
        content = json.dumps(floors, ensure_ascii=False, separators=(",", ":"))
    checksum = digest(
        f"orbital-enemy-level-v1/{revision}/{tables['__checksum__'][1]}\n".encode()
        + content.encode()
    )
    for name, value in ((TABLE, content), ("__checksum__", checksum)):
        at, _, base_revision = tables[name]
        version = base_revision + revision
        if not integer(version, minimum=1):
            raise ValueError("Orbital Lift enemy level revision exceeds the native range.")
        lines[at : at + 4] = [
            f"{part}\n" for part in (name, value, version, digest(value.encode()))
        ]
    return compress("".join(lines).encode()), checksum


def publish(references, source, data):
    data["revision"] += 1
    boards = json.dumps(data["boards"], sort_keys=True) if data["boards"] else ""
    prepare(source, data["level"], data["revision"], boards)
    atomic_write(
        references.directory / SELECTION, json.dumps(data, separators=(",", ":")).encode() + b"\n"
    )


def apply(references, body):
    if (
        not isinstance(body, dict)
        or set(body) != {"level", "revision"}
        or not integer(body["revision"])
    ):
        raise ValueError("Choose a level or restore the original enemy levels.")
    level = body["level"]  # null restores the individual floors' original levels.
    with StateLock(references.directory, filename=".orbital_enemy_level.lock"):
        data = settings(references)
        if body["revision"] != data["revision"]:
            raise LevelChanged("Enemy levels changed. Reload before applying.")
        source = references.read_bytes("static_data_get.bin")
        check_level(level, max_level(source))
        if level != data["level"]:
            data["level"] = level
            publish(references, source, data)
