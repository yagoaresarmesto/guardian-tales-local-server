# SPDX-License-Identifier: Apache-2.0
"""Optional per-stage Expedition enemy levels, without account or source writes."""

import argparse
import json
import os
import tempfile
from contextlib import nullcontext
from functools import lru_cache

from guardian_tales.content.reference import ReferenceData
from guardian_tales.modes.guild.raid_static import (
    atomic_replace,
    compress,
    decode,
    digest,
    records,
    source_tables,
)
from guardian_tales.runtime.state_lock import StateLock
from guardian_tales.settlement.village import integer

from .expedition import enabled

SELECTION = "expedition_levels.json"
MAX_CONFIG_BYTES = 32768
MAX_OVERRIDES = 256


@lru_cache(maxsize=2)
def catalog(body):
    tables = source_tables(body)
    if not {"expedition", "stages", "exps2", "__checksum__"} <= tables.keys():
        raise ValueError("Enemy levels require matching Expedition, stage and experience tables")
    expedition = json.loads(tables["expedition"][1])
    if (
        not isinstance(expedition, dict)
        or not isinstance(expedition.get("Districts"), list)
        or any(
            not isinstance(row, dict)
            or not isinstance(row.get("StageIds"), list)
            or any(not integer(ident, minimum=1) for ident in row["StageIds"])
            for row in expedition["Districts"]
        )
    ):
        raise ValueError("Invalid Expedition district definitions")
    districts = {
        ident: (row.get("Id"), row.get("DistrictNo"))
        for row in expedition["Districts"]
        for ident in row["StageIds"]
    }
    ids = districts.keys()
    stages = json.loads(tables["stages"][1])
    if not isinstance(stages, list) or any(not isinstance(row, dict) for row in stages):
        raise ValueError("Invalid stage definitions")
    # Include archived hidden, unexplored and event variants too. This changes
    # their data only; their entry/unlock contracts remain independent.
    rows = [row for row in stages if row.get("Id") in ids or "ExpeditionStageType" in row]
    if (
        not ids <= {row.get("Id") for row in rows}
        or len({row.get("Id") for row in rows}) != len(rows)
        or any(
            not integer(row.get("Id"), minimum=1)
            or "ExpeditionStageType" in row
            and not integer(row["ExpeditionStageType"], maximum=3)
            for row in rows
        )
    ):
        raise ValueError("Expedition stage definitions must be complete and unique")
    experience = json.loads(tables["exps2"][1])
    levels = experience.get("LevelExps") if isinstance(experience, dict) else None
    if (
        not isinstance(levels, list)
        or not 1 <= len(levels) <= 1000
        or any(
            not isinstance(row, dict)
            or row.get("Level") != index
            or type(row.get("Level")) is not int
            or not integer(row.get("TotalExps"), minimum=1)
            for index, row in enumerate(levels)
        )
        or any(a["TotalExps"] >= b["TotalExps"] for a, b in zip(levels, levels[1:]))
    ):
        raise ValueError("Invalid Global level experience table")
    result = {}
    for row in rows:
        region = row.get("StandardLevel")
        level = (
            region.get("KakaoGlobal", region.get("Default")) if isinstance(region, dict) else None
        )
        if not integer(level, maximum=len(levels)):
            raise ValueError("Invalid original Expedition enemy level")
        result[row["Id"]] = {
            "name": row.get("Name"),
            "original_level": level,
            "district": districts.get(row["Id"], (None, None)),
        }
    return result, len(levels)


def load_levels(references):
    path = references.directory / SELECTION
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError("Invalid Expedition enemy-level configuration file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "generation", "stages"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or not integer(value["generation"], minimum=1)
        or not isinstance(value["stages"], dict)
        or len(value["stages"]) > MAX_OVERRIDES
        or any(
            not key.isascii()
            or not key.isdecimal()
            or len(key) > 10
            or str(int(key)) != key
            or not integer(level, maximum=1000)
            for key, level in value["stages"].items()
        )
    ):
        raise ValueError("Invalid Expedition enemy-level configuration")
    return value["generation"], tuple(
        sorted((int(key), level) for key, level in value["stages"].items())
    )


def validate_levels(body, overrides):
    stages, maximum = catalog(body)
    for ident, level in overrides:
        if ident not in stages or not integer(level, maximum=maximum):
            raise ValueError(f"Choose a listed Expedition stage and a level from 1 to {maximum}")
    return stages, maximum


def visible_level(standard_level, maximum):
    # ExpToLevel returns a zero-based row and the UI adds one. At the final
    # threshold the lookup saturates at its last row. Retain raw v1 settings.
    return min(standard_level + 1, maximum)


@lru_cache(maxsize=2)
def prepare(body, generation, overrides):
    validate_levels(body, overrides)
    lines, tables = records(decode(body))
    stages = json.loads(tables["stages"][1])
    chosen = dict(overrides)
    for row in stages:
        if row["Id"] in chosen:
            row["StandardLevel"]["KakaoGlobal"] = chosen[row["Id"]]
    content = (
        json.dumps(stages, ensure_ascii=False, separators=(",", ":"))
        if overrides
        else tables["stages"][1]
    )
    revision = max(tables["stages"][2], tables["__checksum__"][2]) + generation
    if not integer(generation, minimum=1) or revision > 0x7FFFFFFF:
        raise ValueError("Expedition enemy-level revision exceeds the native integer range")
    checksum = digest(
        b"local-expedition-levels-v1\n"
        + tables["__checksum__"][1].encode()
        + b"\n"
        + str(generation).encode()
        + b"\n"
        + content.encode()
    )
    for name, value in (("stages", content), ("__checksum__", checksum)):
        at = tables[name][0]
        lines[at : at + 4] = [
            name + "\n",
            value + "\n",
            str(revision) + "\n",
            digest(value.encode()) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def write_levels(references, generation, overrides):
    path = references.directory / SELECTION
    # Retain an empty selection after restoration so its revision advances too.
    data = (
        json.dumps(
            {"version": 1, "generation": generation, "stages": dict(overrides)}, indent=2
        ).encode()
        + b"\n"
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".expedition-", delete=False
        ) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


class LevelSelectionChanged(ValueError):
    """A newer level selection must be reloaded before saving."""


def level_settings(
    references, action="list", *, stage=None, all_stages=False, level=None, expected_revision=None
):
    editing = action in ("set-level", "restore-level")
    if (
        action not in ("list", "set-level", "restore-level")
        or (action == "set-level") != (level is not None)
        or (editing and (stage is not None) == all_stages)
        or (not editing and all_stages)
    ):
        raise ValueError(
            "Use list [--stage ID], set-level --stage ID/--all --level N, or restore-level --stage ID/--all"
        )
    body = references.read_bytes("static_data_get.bin")
    lock = (
        StateLock(references.directory, filename=".expedition_levels.lock")
        if editing
        else nullcontext()
    )
    with lock:
        generation, overrides = load_levels(references) or (0, ())
        if expected_revision is not None and expected_revision != generation:
            raise LevelSelectionChanged(
                "Enemy levels changed. Reload the stage list before saving."
            )
        stages, maximum = validate_levels(body, overrides)
        if stage is not None and (not integer(stage, minimum=1) or stage not in stages):
            raise ValueError("Choose an Expedition stage ID from expedition list")
        trial_enabled = enabled(references)
        chosen = dict(overrides)
        targets = stages if all_stages else (stage,)
        if action == "set-level":
            if not trial_enabled:
                raise ValueError("Enable the Expedition trial before setting enemy levels")
            if not integer(level, minimum=1, maximum=maximum):
                raise ValueError(f"Choose a visible enemy level from 1 to {maximum}")
            chosen.update(dict.fromkeys(targets, level - 1))
        elif action == "restore-level":
            for ident in targets:
                chosen.pop(ident, None)
        updated = tuple(sorted(chosen.items()))
        if updated != overrides:
            if len(updated) > MAX_OVERRIDES:
                raise ValueError(f"Expedition supports up to {MAX_OVERRIDES} configured stages")
            generation += 1
            prepare(body, generation, updated)
            write_levels(references, generation, updated)

    return {
        "revision": generation,
        "trial_enabled": trial_enabled,
        "max_enemy_level": maximum,
        "stages": [
            dict(
                stage_id=ident,
                name=row["name"],
                district_id=row["district"][0],
                district_number=row["district"][1],
                original_level=visible_level(row["original_level"], maximum),
                enemy_level=visible_level(chosen.get(ident, row["original_level"]), maximum),
                overridden=ident in chosen,
            )
            for ident, row in sorted(stages.items())
            if stage in (None, ident)
        ],
        "restart_backend_and_game_required": editing,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Configure optional Expedition enemy levels")
    parser.add_argument("action", choices=("list", "set-level", "restore-level"))
    parser.add_argument("--stage", type=int, help="Expedition stage ID, from list")
    parser.add_argument(
        "--level",
        type=int,
        help="Visible enemy level; list reports the maximum for the Global data",
    )
    parser.add_argument("--all", action="store_true", help="Set or restore all Expedition stages")
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    references = ReferenceData(args.reference_dir)
    try:
        result = level_settings(
            references, args.action, stage=args.stage, all_stages=args.all, level=args.level
        )
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        parser.error(str(error))
