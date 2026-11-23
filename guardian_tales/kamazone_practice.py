# SPDX-License-Identifier: Apache-2.0
"""Optional seasonal unlocks and a benefit budget, outside the saved account."""

import argparse
import hashlib
import json
from functools import lru_cache

from . import kamazone
from .punchking_static import atomic_write
from .raid_static import compress, decode, digest, records
from .reference import ReferenceData
from .village import integer

CONFIG = "kamazone_practice.json"
SAVE = "/kamazonland/save-benefits"
MAX_BENEFITS = 8


@lru_cache(maxsize=2)
def catalog(source, season_id):
    if season_id not in kamazone.catalog(source):
        raise ValueError("Kama-ZONE practice requires a preserved Global season")
    mode = json.loads(records(decode(source))[1]["kamazonland2"][1])
    season = kamazone.one(mode["Seasons"], "Id", season_id)
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
    return benefits, limit


def load(references):
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


def validate(value, source):
    if value["source_sha256"] != hashlib.sha256(source).hexdigest():
        raise ValueError("Kama-ZONE practice belongs to another content pack; disable it first")
    benefits, limit = catalog(source, value["season_id"])
    if (
        not integer(value["points"], minimum=1)
        or value["points"] > limit
        or not set(value["unlock_benefits"]) <= benefits.keys()
    ):
        raise ValueError("Practice points/unlocks exceed the selected season's definitions")
    if any(
        int(key) not in benefits
        or level > benefits[int(key)]["MaxLevel"]
        or benefits[int(key)]["OpenType"] != "None"
        and int(key) not in value["unlock_benefits"]
        for key, level in value["benefits"].items()
    ):
        raise ValueError("Invalid saved practice benefit selection")
    if (
        len(value["benefits"]) > MAX_BENEFITS
        or allocated_points(benefits, value["benefits"]) > value["points"]
    ):
        raise ValueError(
            "Saved practice benefits exceed the original selection limit or point budget"
        )
    return benefits


def allocated_points(benefits, levels):
    # The native plus button charges Points[current level] at each upgrade;
    # reaching level N therefore spends the first N listed prices, not just N's.
    return sum(sum(benefits[int(key)]["Points"][:level]) for key, level in levels.items())


def effective(references, source, season_id):
    value = load(references)
    if value is None or not value["enabled"]:
        return None
    validate(value, source)
    return value if value["season_id"] == season_id else None


def delta(value, source):
    benefits = validate(value, source)
    return {
        "UserKamazonLand": {
            "KamazonPoint": value["points"] - allocated_points(benefits, value["benefits"]),
            "KamazonPointTotal": value["points"],
            # Membership.Load copies every supplied row into its selected map.
            # Zero-level placeholders count toward the native eight-benefit cap.
            "Benefits": [
                {"Id": i, "Level": value["benefits"][str(i)]}
                for i in benefits
                if str(i) in value["benefits"]
            ],
        }
    }


def project(references, source, season_id, response):
    value = effective(references, source, season_id)
    if value is not None:
        response["UserKamazonLand"].update(delta(value, source)["UserKamazonLand"])
    return response


def publish(references, value):
    atomic_write(references.directory / CONFIG, json.dumps(value, indent=2).encode() + b"\n")


def save(references, source, season_id, request, operation_id):
    value = effective(references, source, season_id)
    if value is None:
        raise ValueError("Enable Kama-ZONE practice before saving test benefits")
    benefits = validate(value, source)
    if (
        not isinstance(request, dict)
        or set(request) != {"Benefits"}
        or not isinstance(request["Benefits"], dict)
        or len(request["Benefits"]) > len(benefits)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 160
    ):
        raise ValueError("Kama-ZONE save-benefits requires an Id-to-level map")
    chosen = {}
    for key, level in request["Benefits"].items():
        if (
            not key.isascii()
            or not key.isdecimal()
            or str(int(key)) != key
            or int(key) not in benefits
            or not integer(level)
            or level > benefits[int(key)]["MaxLevel"]
            or level > 0
            and benefits[int(key)]["OpenType"] != "None"
            and int(key) not in value["unlock_benefits"]
        ):
            raise ValueError("Invalid, locked or out-of-season Kama-ZONE benefit")
        if level:
            chosen[key] = level
    if len(chosen) > MAX_BENEFITS or allocated_points(benefits, chosen) > value["points"]:
        raise ValueError(
            "Benefit selection exceeds the original eight-benefit limit or point budget"
        )
    if operation_id not in value["seen_operations"]:
        value = dict(
            value,
            benefits=chosen,
            seen_operations=(value["seen_operations"] + [operation_id])[-64:],
        )
        publish(references, value)
    return delta(value, source)


@lru_cache(maxsize=2)
def prepare(body, generation, season_id, unlocks):
    lines, tables = records(decode(body))
    content = tables["kamazonland2"][1]
    if season_id is not None:
        catalog(body, season_id)
        mode = json.loads(content)
        for row in mode["Benefits"]:
            if row["Id"] in unlocks:
                row.update(OpenType="None", OpenValue=0, OpenValues=None)
        content = json.dumps(mode, ensure_ascii=False, separators=(",", ":"))
    # The extra revision step also replaces cached zero-price data from v1
    # when an existing enabled configuration keeps the same generation.
    revision = max(tables["kamazonland2"][2], tables["__checksum__"][2]) + generation + 2
    if revision > 0x7FFFFFFF:
        raise ValueError("Kama-ZONE practice revision exceeds the native integer range")
    checksum = digest(
        (
            "local-kamazone-practice-v2" + tables["__checksum__"][1] + str(generation) + content
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
    value = load(references)
    if value is None:
        return parent(references, filename, request)
    selected = kamazone.load(references)
    active = value["enabled"] and selected and selected["season_id"] == value["season_id"]
    if value["enabled"]:
        validate(value, references.read_bytes("static_data_get.bin"))
    body, checksum = prepare(
        parent(references, "static_data_get.bin", request),
        value["generation"],
        value["season_id"] if active else None,
        tuple(value["unlock_benefits"]) if active else (),
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
    parser.add_argument("action", choices=("enable", "disable", "status"))
    parser.add_argument("--unlock-benefit", action="append", type=int, default=[])
    parser.add_argument("--points", type=int)
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    refs = ReferenceData(args.reference_dir)
    try:
        if args.action != "enable" and (args.unlock_benefit or args.points is not None):
            raise ValueError("Only practice enable accepts point/unlock options")
        previous = load(refs)
        candidate = previous
        if args.action == "enable":
            selection = kamazone.load(refs)
            if selection is None or selection["season_id"] is None:
                raise ValueError("Select a Kama-ZONE season before enabling practice")
            source = refs.read_bytes("static_data_get.bin")
            sha = hashlib.sha256(source).hexdigest()
            if selection["source_sha256"] != sha:
                raise ValueError("Select the season again for the current content pack")
            same = (
                previous
                and previous["source_sha256"] == sha
                and previous["season_id"] == selection["season_id"]
            )
            candidate = dict(
                version=1,
                generation=(previous or {}).get("generation", 0),
                enabled=True,
                source_sha256=sha,
                season_id=selection["season_id"],
                points=args.points if args.points is not None else 4000,
                unlock_benefits=sorted(set(args.unlock_benefit)),
                benefits=previous["benefits"] if same else {},
                seen_operations=previous["seen_operations"] if same else [],
            )
            candidate["generation"] = (previous or {}).get("generation", 0) or 1
            validate(candidate, source)
            if candidate != previous:
                candidate["generation"] = (previous or {}).get("generation", 0) + 1
        elif args.action == "disable" and previous and previous["enabled"]:
            candidate = dict(previous, enabled=False, generation=previous["generation"] + 1)
        changed = candidate != previous
        if changed:
            source = refs.read_bytes("static_data_get.bin")
            prepare(
                source,
                candidate["generation"],
                candidate["season_id"] if candidate["enabled"] else None,
                tuple(candidate["unlock_benefits"]) if candidate["enabled"] else (),
            )
            publish(refs, candidate)
        print(
            json.dumps(
                dict(
                    configuration=candidate,
                    changed=changed,
                    saved_account_modified=False,
                    scope="Seasonal unlocks and a benefit point budget at original costs; no scored runs or rewards",
                    restart_backend_and_game_required=changed,
                ),
                indent=2,
            )
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
