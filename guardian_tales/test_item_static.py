# SPDX-License-Identifier: Apache-2.0
"""Compose private, explicitly granted test pins over the effective static tables."""

import copy
import json
from functools import lru_cache

from .raid_static import compress, decode, digest, records
from .static_cache import prepare_static
from .village import integer

PIN_ID = 9110633
PIN_NAME = "aprilfool_2025_accessory_legend"
TABLE = "admin_test_item_grants"
MAX_GRANTS = 256


def has_grants(db):
    return bool(
        db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
    )


@lru_cache(maxsize=2)
def item_definitions(body):
    return item_definitions_from_tables(records(decode(body))[1])


def item_definitions_from_tables(tables):
    if not {"items", "__checksum__"} <= tables.keys():
        raise ValueError("Test pins require matching external items and checksum tables")
    items = json.loads(tables["items"][1])
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= 100000
        or any(
            not isinstance(s, dict)
            or not integer(s.get("Id"), minimum=1)
            or not isinstance(s.get("Name"), str)
            for s in items
        )
        or len({s["Id"] for s in items}) != len(items)
        or len({s["Name"] for s in items}) != len(items)
    ):
        raise ValueError("Invalid test-pin source item definitions")
    return items


def pin_spec(body, used_ids, defense, attack_percent):
    items = item_definitions(body)
    pins = [s for s in items if s["Id"] == PIN_ID]
    if len(pins) != 1 or any(
        pins[0].get(k) != v
        for k, v in {
            "Name": PIN_NAME,
            "Type": "weapon",
            "WeaponType": "accessory",
            "Rarity": 3,
            "OriginRarity": 3,
            "NameWithoutRarity": "aprilfool_2025_accessory",
        }.items()
    ):
        raise ValueError("The matching Rustic but Precious Pin definition is required")
    occupied = {s["Id"] for s in items} | set(used_ids)
    names = {s["Name"] for s in items}
    ident = next(
        (
            n
            for n in range(9990003, 10000000, 10)
            if n not in occupied and f"local_test_pin_{n}_legend" not in names
        ),
        None,
    )
    if ident is None:
        raise ValueError("No unused test-pin specification ID remains")
    spec = copy.deepcopy(pins[0])
    spec.update(
        Id=ident,
        Name=f"local_test_pin_{ident}_legend",
        Defense=defense,
        StatGrowthRate=1.0,
        Limited=True,
        Composable=False,
        Summonable=False,
        MinOptions=int(bool(attack_percent)),
        MaxOptions=int(bool(attack_percent)),
    )
    # The original has neither level scaling nor alternate (myth) statistics.
    spec.pop("LevelScale", None)
    spec.pop("Options", None)
    if attack_percent:
        tables = records(decode(body))[1]
        options = json.loads(tables.get("options", (0, "[]", 0))[1])
        attack = (
            [option for option in options if isinstance(option, dict) and option.get("Id") == 10]
            if isinstance(options, list)
            else []
        )
        if len(attack) != 1 or any(
            attack[0].get(k) != v
            for k, v in {
                "Class": "TotalAttackScale",
                "AttackScaleAdd": 0.01,
                "AttackScaleBase": 0,
            }.items()
        ):
            raise ValueError("The matching ATK percent suboption definition is required")
        spec["StaticOptions"] = [s for s in spec["StaticOptions"] if s["OptionId"] != 36]
        spec["Options"] = [
            dict(OptionId=10, MinLevel=attack_percent, MaxLevel=attack_percent, Probability=1)
        ]
    return spec


def active_specs(db):
    if not has_grants(db):
        return ()
    saved = db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()
    if saved is None:
        raise ValueError("Test-pin registry has no account")
    owned = {row["ItemId"] for row in json.loads(saved[0])["User"]["ItemWeapons"]}
    rows = db.execute(f"SELECT spec_id,spec FROM {TABLE} ORDER BY spec_id").fetchall()
    if len(rows) > MAX_GRANTS:
        raise ValueError("Test-pin registry exceeds its limit")
    result = []
    for ident, encoded in rows:
        if ident in owned:
            spec = json.loads(encoded)
            if not isinstance(spec, dict) or spec.get("Id") != ident:
                raise ValueError("Invalid saved test-pin definition")
            result.append(encoded)
    return tuple(result)


@lru_cache(maxsize=2)
def prepare(body, specs):
    items = copy.deepcopy(item_definitions(body))
    added = [json.loads(s) for s in specs]
    if not added or len(added) > MAX_GRANTS:
        raise ValueError("Invalid test-pin overlay size")
    if (
        {s["Id"] for s in added} & {s["Id"] for s in items}
        or {s["Name"] for s in added} & {s["Name"] for s in items}
        or len({s["Id"] for s in added}) != len(added)
        or len({s["Name"] for s in added}) != len(added)
    ):
        raise ValueError("Test-pin definitions collide with the current client items")
    lines, tables = records(decode(body))
    value = json.dumps(items + added, ensure_ascii=False, separators=(",", ":"))
    revision = max(tables["items"][2], tables["__checksum__"][2]) + 1
    if revision > 0x7FFFFFFF:
        raise ValueError("Test-pin static revision exceeds the native integer range")
    checksum = digest(
        b"local-test-pins-v1\n" + tables["__checksum__"][1].encode() + b"\n" + value.encode()
    )
    for name, content in (("items", value), ("__checksum__", checksum)):
        at = tables[name][0]
        lines[at : at + 4] = [
            name + "\n",
            content + "\n",
            str(revision) + "\n",
            digest(content.encode()) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(db, references, filename, request, parent):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return parent(references, filename, request)
    specs = active_specs(db)
    if not specs:
        return parent(references, filename, request)
    source = parent(references, "static_data_get.bin", request)
    body, checksum = prepare_static(references, prepare, source, specs)
    if filename == "static_data_get.bin":
        return body
    return json.dumps(
        {
            "UpToDate": isinstance(request, dict) and request.get("Checksum") == checksum,
            "Checksum": checksum,
            "QuitGameWhenStaticDataUpdateNeeded": False,
        }
    ).encode()
