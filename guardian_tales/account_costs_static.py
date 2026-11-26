# SPDX-License-Identifier: Apache-2.0
"""Apply free local account costs in one pass over the effective client tables."""

import json
from functools import lru_cache

from .inventory_expansion import expansion_rows
from .raid_static import compress, decode, digest, records
from .static_cache import prepare_static
from .village import integer


@lru_cache(maxsize=2)
def prepare(body):
    raw = decode(body)
    if raw.strip() == b"[]":
        return None
    lines, items = records(raw)
    constants = json.loads(items["constants"][1]) if "constants" in items else {}
    if not isinstance(constants, dict):
        raise ValueError("Invalid nickname constants table")
    equipment = json.loads(items["weaponenhance"][1]) if "weaponenhance" in items else {}
    compose_steps = equipment.get("WeaponCompose", []) if isinstance(equipment, dict) else []
    evolve_steps = equipment.get("WeaponEvolve", []) if isinstance(equipment, dict) else []
    myth_steps = equipment.get("WeaponMyth", []) if isinstance(equipment, dict) else []
    if (
        "ChangeNickCost" not in constants
        and not {"inventoryexpansion", "merch"} & items.keys()
        and not compose_steps
        and not evolve_steps
        and not myth_steps
    ):
        return None
    cost = constants.get("ChangeNickCost", 0)
    if not integer(cost) or "__checksum__" not in items:
        raise ValueError("Invalid nickname cost or static checksum")
    changes = {}
    for step in (*compose_steps, *evolve_steps):
        if not isinstance(step, dict) or not integer(step.get("GoldCost")):
            raise ValueError("Invalid equipment evolution price")
        if step["GoldCost"]:
            step["GoldCost"] = 0
            changes["weaponenhance"] = equipment
    for step in myth_steps:
        # The Grade 6 screen needs the material entry to display its icon.
        for price in step.get("Costs", []):
            if not integer(price.get("ItemId"), minimum=1) or not integer(price.get("Amount")):
                raise ValueError("Invalid Grade 6 evolution material")
            if price["Amount"]:
                price["Amount"] = 0
                changes["weaponenhance"] = equipment
    if cost:
        constants["ChangeNickCost"] = 0
        changes["constants"] = constants
    if "inventoryexpansion" in items:
        rows = expansion_rows(items["inventoryexpansion"][1])
        if any(row["InvenExpandCost"] or row["InvenTotalExpandCost"] for row in rows):
            for row in rows:
                row.update(InvenExpandCost=0, InvenTotalExpandCost=0)
            changes["inventoryexpansion"] = rows
    if "merch" in items:
        forge = json.loads(items["merch"][1])
        if not isinstance(forge, dict):
            raise ValueError("Invalid merch forge table")
        for name in ("MerchLevels", "MerchEvolves"):
            rows = forge.get(name, [])
            if not isinstance(rows, list):
                raise ValueError("Invalid merch forge rows")
            for row in rows:
                prices = row.get("GoldNeeded", []) if isinstance(row, dict) else None
                if not isinstance(prices, list) or not all(integer(n) for n in prices):
                    raise ValueError("Invalid merch forge prices")
                if any(prices):
                    row["GoldNeeded"] = [0] * len(prices)
                    changes["merch"] = forge
        specs = json.loads(items["items"][1]) if "items" in items else []
        if not isinstance(specs, list) or not all(isinstance(s, dict) for s in specs):
            raise ValueError("Invalid item specifications for merch forge")
        for spec in specs:
            if spec.get("Type") == "merchenhance" and spec.get("GoldNeeded"):
                spec["GoldNeeded"] = 0
                changes["items"] = specs
    if not changes:
        return body, items["__checksum__"][1]
    values = {
        name: json.dumps(table, ensure_ascii=False, separators=(",", ":"))
        for name, table in changes.items()
    }
    revision = max(items[name][2] for name in (*values, "__checksum__")) + 1
    if not integer(revision):
        raise ValueError("Local account cost revision exceeds the native integer range")
    checksum = digest(
        "\n".join(
            ("local-free-account-costs-v1", items["__checksum__"][1], *values.values())
        ).encode()
    )
    values["__checksum__"] = checksum
    for name, value in values.items():
        at = items[name][0]
        lines[at : at + 4] = [
            name + "\n",
            value + "\n",
            str(revision) + "\n",
            digest(value.encode()) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(references, filename, request, parent):
    if filename in ("static_data_get.bin", "static_data_check.bin"):
        source = parent(references, "static_data_get.bin", request)
        prepared = prepare_static(references, prepare, source)
        if prepared is not None:
            body, checksum = prepared
            if filename == "static_data_get.bin":
                return body
            return json.dumps(
                {
                    "UpToDate": isinstance(request, dict) and request.get("Checksum") == checksum,
                    "Checksum": checksum,
                    "QuitGameWhenStaticDataUpdateNeeded": False,
                }
            ).encode()
    return parent(references, filename, request)
