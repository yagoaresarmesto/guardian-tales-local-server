# SPDX-License-Identifier: Apache-2.0
"""Compose floor-specific Orbital Lift enemy formations over the shared level setting."""

import hashlib
import json
from functools import lru_cache

from . import orbital_levels as levels
from .orbital import FORMATION_CELLS, LAST_SELECTABLE_FLOOR
from .panel_common.labels import english_labels
from .raid_static import source_tables
from .reference import ReferenceData
from .state_lock import StateLock
from .village import integer


def stock_units(floor):
    return [
        {"position": row["Position"], "enemy": row["MonsterId"], "origin": row["Position"]}
        for row in floor["Monsters"]
    ]


def roster(floors, tables):
    used = {unit["MonsterId"] for floor in floors for unit in floor["Monsters"]}
    specs = {
        spec["MonsterId"]: spec
        for spec in json.loads(tables["infinitytowermonsters"][1])
        if spec["MonsterId"] in used
    }
    if used != specs.keys():
        raise ValueError("The Orbital Lift monster catalog is incomplete.")
    return specs


def elite_catalog(specs, tables):
    used = {option for spec in specs.values() for option in spec.get("AvailableEliteOption", [])}
    titles = {
        "elite_mortar": "Mortar (Shelling)",
        "elite_stat_up": "Stat Up (Enlargement)",
        "elite_melee_immune": "Melee immunity",
        "elite_projectile_immune": "Ranged immunity",
    }
    options = json.loads(tables["options"][1]) if used and "options" in tables else []
    names = {
        row["Id"]: titles.get(
            row["Name"], row["Name"].removeprefix("elite_").replace("_", " ").title()
        )
        for row in options
        if row["Id"] in used
    }
    allowed = {
        enemy: [key for key in spec.get("AvailableEliteOption", []) if key in names]
        for enemy, spec in specs.items()
    }
    return names, allowed


@lru_cache(maxsize=2)
def catalog(source, directory):
    tables = source_tables(source)
    floors, maximum = levels.floor_data(tables)
    specs = roster(floors, tables)
    models = {row["Id"]: row for row in json.loads(tables["monsters"][1])}
    modifiers, allowed = elite_catalog(specs, tables)
    names = {
        enemy: models[spec["SpecId"]]["Name"].removeprefix("it_") for enemy, spec in specs.items()
    }
    labels = english_labels(
        ReferenceData(directory), hashlib.sha256(source).hexdigest(), set(names.values())
    )
    choices = []
    for enemy, spec in specs.items():
        model = models[spec["SpecId"]]
        name = names[enemy]
        sprite = (
            (model.get("SpriteName") or {}).get("default")
            or (model.get("SpineAssetName") or {}).get("default")
            or ""
        )
        choices.append(
            {
                "id": enemy,
                "name": labels.get(name) or name.replace("_", " ").title(),
                "element": model.get("ElementalType"),
                "boss": spec.get("Class") == "boss",
                "elites": allowed[enemy],
                "sprite": sprite.split(":")[-1].split("#")[-1],
            }
        )
    return {
        "maxLevel": maximum,
        "eliteNames": modifiers,
        "enemies": sorted(choices, key=lambda x: (x["name"], x["id"])),
        "floors": {
            row["Floor"]: {
                "type": row["FloorType"],
                "level": row["StandardLevel"] + 1,
                "units": stock_units(row),
                "originalElites": {
                    unit["Position"]: unit["Options"][0]["OptionId"]
                    for unit in row["Monsters"]
                    if unit.get("Options")
                },
            }
            for row in floors
            if row["Floor"] <= LAST_SELECTABLE_FLOOR
        },
    }


def state(references, floor=1):
    source = references.read_bytes("static_data_get.bin")
    data = levels.settings(references)
    view = catalog(source, references.directory)
    return {
        "floor": view["floors"][floor],
        "custom": data["boards"].get(str(floor)),
        "modifiedFloors": sorted(map(int, data["boards"])),
        "enemies": view["enemies"],
        "eliteNames": view["eliteNames"],
        "maxLevel": view["maxLevel"],
        "revision": data["revision"],
        "globalLevel": data["level"],
    }


def validate_board(board, original, enemies, maximum):
    if not isinstance(board, dict) or set(board) != {"level", "units"}:
        raise ValueError("Choose a floor level and enemy formation.")
    levels.check_level(board["level"], maximum)
    units = board["units"]
    if units is None:
        return
    if not isinstance(units, list) or not (int(bool(original)) <= len(units) <= FORMATION_CELLS):
        raise ValueError("A combat board needs 1–20 enemies.")
    stock = {unit["position"]: unit["enemy"] for unit in original}
    positions, origins = set(), set()
    for unit in units:
        if not isinstance(unit, dict) or not {"enemy", "position"} <= unit.keys() <= {
            "enemy",
            "position",
            "origin",
            "elite",
        }:
            raise ValueError("Invalid enemy placement.")
        pos, enemy = unit["position"], unit["enemy"]
        if (
            not integer(pos, FORMATION_CELLS, 1)
            or pos in positions
            or not integer(enemy, minimum=1)
            or enemy not in enemies
        ):
            raise ValueError("Use one Orbital Lift enemy per cell.")
        positions.add(pos)
        modifier = unit.get("elite")
        if modifier is not None and (
            not integer(modifier, minimum=1) or modifier not in enemies[enemy]
        ):
            raise ValueError("Choose one elite modifier available to this enemy.")
        if "origin" in unit:
            origin = unit["origin"]
            if (
                not integer(origin, FORMATION_CELLS, 1)
                or origin in origins
                or stock.get(origin) != enemy
            ):
                raise ValueError("An original enemy and its modifiers can only be moved once.")
            origins.add(origin)


def native_unit(unit, original):
    row = {
        **original.get(unit.get("origin"), {}),
        "Position": unit["position"],
        "MonsterId": unit["enemy"],
    }
    # Old boards omit elite and inherit the complete original options through origin.
    if "elite" in unit:
        if unit["elite"] is None:
            row.pop("Options", None)
        else:
            row["Options"] = [{"OptionId": unit["elite"], "Level": 1}]
    return row


def apply_overrides(floors, boards, tables, maximum):
    _, enemies = elite_catalog(roster(floors, tables), tables)
    by_floor = {str(row["Floor"]): row for row in floors if row["Floor"] <= LAST_SELECTABLE_FLOOR}
    for key, board in boards.items():
        if key not in by_floor:
            raise ValueError("Invalid custom Orbital Lift floor.")
        row = by_floor[key]
        validate_board(board, stock_units(row), enemies, maximum)
        if board["level"] is not None:
            row["StandardLevel"] = board["level"] - 1
        if board["units"] is not None:
            original = {unit["Position"]: unit for unit in row["Monsters"]}
            row["Monsters"] = [native_unit(unit, original) for unit in board["units"]]
            if row["Monsters"] and row["FloorType"] == "RecordRoom":
                row["FloorType"] = "Normal"


def apply(references, body):
    if (
        not isinstance(body, dict)
        or set(body) != {"floor", "board", "revision"}
        or not integer(body["floor"], LAST_SELECTABLE_FLOOR, 1)
        or not integer(body["revision"])
    ):
        raise ValueError("Choose a floor from 1 to 1500 and reload its board.")
    with StateLock(references.directory, filename=".orbital_enemy_level.lock"):
        data = levels.settings(references)
        if body["revision"] != data["revision"]:
            raise levels.LevelChanged("Orbital Lift settings changed. Reload before saving.")
        floor, board = body["floor"], body["board"]
        source = references.read_bytes("static_data_get.bin")
        if board is not None:
            view = catalog(source, references.directory)
            stock = view["floors"][floor]["units"]
            validate_board(
                board,
                stock,
                {enemy["id"]: enemy["elites"] for enemy in view["enemies"]},
                view["maxLevel"],
            )
            if board["units"] == stock:
                board = {**board, "units": None}
            if board == {"level": None, "units": None}:
                board = None
        key = str(floor)
        if data["boards"].get(key) != board:
            if board is None:
                del data["boards"][key]
            else:
                data["boards"][key] = board
            levels.publish(references, source, data)
