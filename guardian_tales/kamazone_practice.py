# SPDX-License-Identifier: Apache-2.0
"""Seasonal menu benefits, a shared budget policy and separate local allocations."""

import argparse
import hashlib
import json
from functools import lru_cache
from threading import Lock

from . import kamazone
from .punchking_static import atomic_write
from .raid_static import compress, decode, digest, records
from .reference import ReferenceData
from .village import integer

CONFIG = "kamazone_practice.json"
SAVE = "/kamazonland/save-benefits"
MAX_BENEFITS = 8
BUDGET = 4000
_save_lock = Lock()


@lru_cache(maxsize=2)
def catalog(source, season_id):
    if season_id not in kamazone.catalog(source):
        raise ValueError("Kama-ZONE practice requires a preserved Global season")
    mode = kamazone.mode_data(source)
    return seasonal_benefits(mode, kamazone.one(mode["Seasons"], "Id", season_id))


def seasonal_benefits(mode, season):
    ids = season.get("Benefits")
    rows = mode.get("Benefits")
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 128
        or any(not integer(i, minimum=1) for i in ids)
        or len(set(ids)) != len(ids)
        or not isinstance(rows, list)
    ):
        raise ValueError("Invalid seasonal Kama-ZONE benefit list")
    benefits = {i: kamazone.one(rows, "Id", i) for i in ids}
    for row in benefits.values():
        maximum, prices = row.get("MaxLevel"), row.get("Points")
        if (
            not integer(maximum, maximum=100, minimum=1)
            or not isinstance(prices, list)
            or len(prices) != maximum
            or any(not integer(p) for p in prices)
            or not isinstance(row.get("OpenType"), str)
        ):
            raise ValueError("Invalid Kama-ZONE benefit level or cost")
    minis = mode.get("MiniSeasons")
    if not isinstance(minis, list):
        raise ValueError("Missing Kama-ZONE mini-season limits")
    mini = kamazone.one(minis, "MiniSeasonGroupId", season.get("MiniSeasonGroupId"))
    limit = mini.get("KamazonPointLimit")
    if not integer(limit, minimum=1):
        raise ValueError("Invalid Kama-ZONE mini-season point limit")
    return benefits


def legacy_config(references):
    path = references.directory / CONFIG
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("Invalid Kama-ZONE practice configuration")
    value = references.json(CONFIG)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "version",
            "generation",
            "enabled",
            "source_sha256",
            "season_id",
            "points",
            "unlock_benefits",
            "benefits",
            "seen_operations",
        }
        or type(value["version"]) is not int
        or value["version"] != 1
        or not integer(value["generation"], minimum=1)
        or type(value["enabled"]) is not bool
        or not integer(value["season_id"], minimum=1)
        or not integer(value["points"], minimum=1)
        or not isinstance(value["source_sha256"], str)
        or len(value["source_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in value["source_sha256"])
        or not isinstance(value["unlock_benefits"], list)
        or len(value["unlock_benefits"]) > 128
        or any(not integer(i, minimum=1) for i in value["unlock_benefits"])
        or len(set(value["unlock_benefits"])) != len(value["unlock_benefits"])
        or not isinstance(value["benefits"], dict)
        or len(value["benefits"]) > 128
        or any(
            not key.isascii()
            or not key.isdecimal()
            or str(int(key)) != key
            or not integer(int(key), minimum=1)
            or not integer(level, minimum=1)
            for key, level in value["benefits"].items()
        )
        or not isinstance(value["seen_operations"], list)
        or len(value["seen_operations"]) > 64
        or any(
            not isinstance(op, str) or not 1 <= len(op) <= 160 for op in value["seen_operations"]
        )
        or len(set(value["seen_operations"])) != len(value["seen_operations"])
    ):
        raise ValueError("Invalid Kama-ZONE practice configuration")
    return value


def allocated_points(benefits, levels):
    # The native plus button charges Points[current level] at each upgrade;
    # reaching level N therefore spends the first N listed prices, not just N's.
    return sum(sum(benefits[int(key)]["Points"][:level]) for key, level in levels.items())


@lru_cache(maxsize=3)
def source_hash(source):
    return hashlib.sha256(source).hexdigest()


def allocation_file(source, season_id):
    return f"kamazone_benefits_{season_id}_{source_hash(source)}.json"


def selection(benefits, levels):
    if not isinstance(levels, dict) or len(levels) > len(benefits):
        raise ValueError("Expected a seasonal benefit ID-to-level map")
    chosen = {}
    for key, level in levels.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or len(key) > 10
            or str(int(key)) != key
            or int(key) not in benefits
            or not integer(level, maximum=benefits[int(key)]["MaxLevel"])
        ):
            raise ValueError("Invalid or out-of-season Kama-ZONE benefit or level")
        if level:
            chosen[key] = level
    if len(chosen) > MAX_BENEFITS or allocated_points(benefits, chosen) > BUDGET:
        raise ValueError("Benefit selection exceeds eight benefits or 4,000 points")
    return chosen


def effective(references, source, season_id):
    benefits = catalog(source, season_id)
    name = allocation_file(source, season_id)
    path = references.directory / name
    if path.exists():
        if not path.is_file() or path.stat().st_size > 16384:
            raise ValueError("Invalid Kama-ZONE benefit allocation file")
        value = references.json(name)
        if not isinstance(value, dict) or set(value) != {"benefits", "seen_operations"}:
            raise ValueError("Invalid Kama-ZONE benefit allocation")
    else:
        legacy = legacy_config(references)
        if legacy and (legacy["source_sha256"], legacy["season_id"]) == (
            source_hash(source),
            season_id,
        ):
            value = {key: legacy[key] for key in ("benefits", "seen_operations")}
        else:
            return {"benefits": {}, "seen_operations": []}
    operations = value["seen_operations"]
    if (
        selection(benefits, value["benefits"]) != value["benefits"]
        or not isinstance(operations, list)
        or len(operations) > 64
        or any(not isinstance(op, str) or not 1 <= len(op) <= 160 for op in operations)
        or len(set(operations)) != len(operations)
    ):
        raise ValueError("Invalid saved Kama-ZONE benefit allocation or receipts")
    return value


def project(references, source, season_id, response):
    benefits = catalog(source, season_id)
    levels = effective(references, source, season_id)["benefits"]
    # The native eight-slot limit counts every returned row, even at level zero.
    response["UserKamazonLand"].update(
        KamazonPoint=BUDGET - allocated_points(benefits, levels),
        KamazonPointTotal=BUDGET,
        Benefits=[{"Id": i, "Level": levels[str(i)]} for i in benefits if str(i) in levels],
    )
    return response


def save(references, source, season_id, request, operation_id):
    if (
        not isinstance(request, dict)
        or set(request) != {"Benefits"}
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 160
    ):
        raise ValueError("Invalid Kama-ZONE save-benefits request")
    chosen = selection(catalog(source, season_id), request["Benefits"])
    with _save_lock:
        value = effective(references, source, season_id)
        if operation_id not in value["seen_operations"]:
            value = dict(
                benefits=chosen, seen_operations=(value["seen_operations"] + [operation_id])[-64:]
            )
            encoded = json.dumps(value, indent=2).encode() + b"\n"
            if len(encoded) > 16384:
                raise ValueError("Kama-ZONE benefit allocation exceeds its file size limit")
            atomic_write(references.directory / allocation_file(source, season_id), encoded)


@lru_cache(maxsize=2)
def prepare(body, generation, season_id):
    lines, tables = records(decode(body))
    content = tables["kamazonland2"][1]
    if season_id is not None:
        mode = json.loads(content)
        season = kamazone.one(mode["Seasons"], "Id", season_id)
        for row in seasonal_benefits(mode, season).values():
            if row["OpenType"] != "None":
                row.update(OpenType="None", OpenValue=0, OpenValues=None)
        mini = kamazone.one(mode["MiniSeasons"], "MiniSeasonGroupId", season["MiniSeasonGroupId"])
        mini["KamazonPointLimit"] = BUDGET
        content = json.dumps(mode, ensure_ascii=False, separators=(",", ":"))
    # Advance beyond the old practice overlay even for an unchanged season.
    revision = max(tables["kamazonland2"][2], tables["__checksum__"][2]) + generation + 3
    if revision > 0x7FFFFFFF:
        raise ValueError("Kama-ZONE practice revision exceeds the native integer range")
    checksum = digest(
        (
            "local-kamazone-benefits-v3" + tables["__checksum__"][1] + str(generation) + content
        ).encode()
    )
    for name, text in (("kamazonland2", content), ("__checksum__", checksum)):
        at = tables[name][0]
        lines[at : at + 4] = [
            name + "\n",
            text + "\n",
            str(revision) + "\n",
            digest(text.encode()) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(references, filename, request, parent):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return parent(references, filename, request)
    selected = kamazone.load(references)
    legacy = legacy_config(references)
    if selected is None and legacy is None:
        return parent(references, filename, request)
    generation = (selected or {}).get("generation", 0) + (legacy or {}).get("generation", 0)
    body, checksum = prepare(
        parent(references, "static_data_get.bin", request),
        generation,
        selected["season_id"] if selected else None,
    )
    if filename == "static_data_get.bin":
        return body
    return json.dumps(
        dict(
            Checksum=checksum,
            UpToDate=isinstance(request, dict) and request.get("Checksum") == checksum,
            QuitGameWhenStaticDataUpdateNeeded=False,
        )
    ).encode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "enable", "disable"))
    parser.add_argument(
        "--unlock-benefit", action="append", type=int, default=[], help=argparse.SUPPRESS
    )
    parser.add_argument("--points", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    refs = ReferenceData(args.reference_dir)
    try:
        if args.action == "disable" or args.points not in (None, BUDGET):
            raise ValueError("Menu benefits are automatic with a fixed 4,000-point budget")
        if args.action != "enable" and (args.unlock_benefit or args.points is not None):
            raise ValueError("Status takes no point or unlock options")
        selected = kamazone.load(refs)
        season_id = selected["season_id"] if selected else None
        levels = {}
        ids = []
        if season_id is not None:
            source = refs.read_bytes("static_data_get.bin")
            if selected["source_sha256"] != source_hash(source):
                raise ValueError("Select the season again for the current content pack")
            ids = list(catalog(source, season_id))
            levels = effective(refs, source, season_id)["benefits"]
        if not set(args.unlock_benefit) <= set(ids):
            raise ValueError("Requested benefit is outside the selected season")
        print(
            json.dumps(
                dict(
                    automatic=True,
                    selected_season_id=season_id,
                    points=BUDGET,
                    unlocked_benefits=ids,
                    benefits=levels,
                    changed=False,
                    message="All menu benefits unlock when a season is selected. No practice command is required.",
                ),
                indent=2,
            )
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
