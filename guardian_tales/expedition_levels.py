# SPDX-License-Identifier: Apache-2.0
"""Optional per-stage Expedition enemy levels, without account or source writes."""

import argparse
import json
import os
import tempfile
from functools import lru_cache

from .raid_static import atomic_replace, compress, decode, digest, records
from .reference import ReferenceData
from .village import integer

SELECTION = "expedition_levels.json"
MAX_CONFIG_BYTES = 32768


@lru_cache(maxsize=2)
def catalog(body):
    _, tables = records(decode(body))
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
    ids = {ident for row in expedition["Districts"] for ident in row["StageIds"]}
    stages = json.loads(tables["stages"][1])
    if not isinstance(stages, list) or any(not isinstance(row, dict) for row in stages):
        raise ValueError("Invalid stage definitions")
    rows = [row for row in stages if row.get("Id") in ids]
    if len(rows) != len(ids) or len({row["Id"] for row in rows}) != len(ids):
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
            or not integer(row.get("TotalExps"))
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
        if not integer(level, minimum=1, maximum=len(levels)):
            raise ValueError("Invalid original Expedition enemy level")
        result[row["Id"]] = {"name": row.get("Name"), "original_level": level}
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
        or len(value["stages"]) > 256
        or any(
            not key.isascii()
            or not key.isdecimal()
            or len(key) > 10
            or str(int(key)) != key
            or not integer(level, minimum=1, maximum=1000)
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
        if ident not in stages or not integer(level, minimum=1, maximum=maximum):
            raise ValueError(f"Choose a listed Expedition stage and a level from 1 to {maximum}")
    return stages, maximum


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Configure optional Expedition enemy levels")
    parser.add_argument("action", choices=("list", "set-level", "restore-level"))
    parser.add_argument("--stage", type=int, help="Expedition stage ID, from list")
    parser.add_argument(
        "--level", type=int, help="Enemy level supported by the Global experience table"
    )
    parser.add_argument("--all", action="store_true", help="Restore every stage's original level")
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    references = ReferenceData(args.reference_dir)
    try:
        if (
            args.action == "list"
            and (args.level is not None or args.all)
            or args.action == "set-level"
            and (args.stage is None or args.level is None or args.all)
            or args.action == "restore-level"
            and (args.level is not None or (args.stage is not None) == args.all)
        ):
            raise ValueError(
                "Use list [--stage ID], set-level --stage ID --level N, or restore-level --stage ID/--all"
            )
        body = references.read_bytes("static_data_get.bin")
        selection = load_levels(references)
        generation, overrides = selection or (0, ())
        stages, maximum = validate_levels(body, overrides)
        if args.stage is not None and args.stage not in stages:
            raise ValueError("Choose an Expedition stage ID from expedition list")
        chosen = dict(overrides)
        if args.action == "set-level":
            from .expedition import enabled

            if not enabled(references):
                raise ValueError("Enable the Expedition trial before setting enemy levels")
            chosen[args.stage] = args.level
            validate_levels(body, tuple(chosen.items()))
        elif args.action == "restore-level":
            if args.all:
                chosen.clear()
            else:
                chosen.pop(args.stage, None)
        if args.action != "list" and chosen != dict(overrides):
            # Check the complete candidate before atomically publishing it.
            prepare(body, generation + 1, tuple(sorted(chosen.items())))
            write_levels(references, generation + 1, tuple(sorted(chosen.items())))
        print(
            json.dumps(
                {
                    "max_enemy_level": maximum,
                    "stages": [
                        dict(
                            stage_id=ident,
                            **row,
                            enemy_level=chosen.get(ident, row["original_level"]),
                            overridden=ident in chosen,
                        )
                        for ident, row in sorted(stages.items())
                        if args.stage in (None, ident)
                    ],
                    "restart_backend_and_game_required": args.action != "list",
                },
                indent=2,
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
