# SPDX-License-Identifier: Apache-2.0
"""Try the preserved Tetis board on season 1 floor 1 using the local static response."""

import argparse
import json
from functools import lru_cache

from .punchking_static import atomic_write
from .raid_static import compress, decode, digest, records, selected_static_seed
from .reference import ReferenceData
from .state_lock import StateLock
from .village import integer

SELECTION = "tetis_map_trial.json"
STOCK_STAGE = 280010011
TRIAL_STAGE = 280010001


def selection(references):
    path = references.directory / SELECTION
    if not path.exists():
        return False, 0
    if path.stat().st_size > 256:
        raise ValueError("Invalid Tetis map trial settings")
    settings = json.loads(path.read_bytes())
    if (
        not isinstance(settings, dict)
        or set(settings) != {"enabled", "generation"}
        or type(settings["enabled"]) is not bool
        or not integer(settings["generation"], minimum=1)
    ):
        raise ValueError("Invalid Tetis map trial settings")
    return settings["enabled"], settings["generation"]


@lru_cache(maxsize=2)
def prepare(body, enabled, generation):
    lines, tables = records(decode(body))
    if not {"stages", "roguechess3", "__checksum__"} <= tables.keys():
        raise ValueError("The Tetis map trial requires the matching 3.57.0 stage and floor tables")
    stages = json.loads(tables["stages"][1])
    for stage_id, name in (
        (TRIAL_STAGE, "roguechess_1"),
        (STOCK_STAGE, "roguechess_season_1_normal"),
    ):
        matches = [row for row in stages if row["Id"] == stage_id]
        if (
            len(matches) != 1
            or matches[0].get("Tilemap", {}).get("Default") != name
            or "RogueChess" not in (matches[0].get("Event") or [])
        ):
            raise ValueError(f"Missing the original Tetis stage {name}")
    content = tables["roguechess3"][1]
    data = json.loads(content)
    matches = [row for row in data["Floors"] if row["SeasonId"] == 1 and row["Floor"] == 1]
    if len(matches) != 1 or matches[0]["Id"] != 10001 or matches[0]["StageId"] != STOCK_STAGE:
        raise ValueError("The trial requires the original season 1 floor 1")
    if enabled:
        matches[0]["StageId"] = TRIAL_STAGE
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Keep the Tetis revision independent of any other active trial. Their
    # calendar and item revisions can go down when the operator changes modes.
    checksum = digest(
        f"tetis-map-trial-v1/{generation}/{int(enabled)}/{tables['__checksum__'][1]}".encode()
        + content.encode()
    )
    for name, value in (("roguechess3", content), ("__checksum__", checksum)):
        index, _, parent_revision = tables[name]
        revision = parent_revision + generation
        if not integer(revision, minimum=1):
            raise ValueError("Tetis map trial revision exceeds the native integer range")
        lines[index : index + 4] = [
            f"{line}\n" for line in (name, value, revision, digest(value.encode()))
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(references, filename, request, parent):
    return selected_static_seed(references, filename, request, parent, selection, prepare)


def configure(references, enabled):
    with StateLock(references.directory, filename=".tetis_map_trial.lock"):
        current, generation = selection(references)
        if enabled != current:
            generation += 1
            prepare(references.read_bytes("static_data_get.bin"), enabled, generation)
            atomic_write(
                references.directory / SELECTION,
                json.dumps({"enabled": enabled, "generation": generation}).encode() + b"\n",
            )
    return {
        "season": 1,
        "floor": 1,
        "stage_id": TRIAL_STAGE if enabled else STOCK_STAGE,
        "enabled": enabled,
        "generation": generation,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "restore"))
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    try:
        result = configure(ReferenceData(args.reference_dir), args.action == "enable")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    print("Fully close and reopen Guardian Tales to load the selected map.")
