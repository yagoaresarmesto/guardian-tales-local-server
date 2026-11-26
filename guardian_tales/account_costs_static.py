# SPDX-License-Identifier: Apache-2.0
"""Apply free local account costs in one pass over the effective client tables."""

import json
from functools import lru_cache

from .inventory_expansion import expansion_rows
from .raid_static import compress, decode, digest, records
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
    if "ChangeNickCost" not in constants and "inventoryexpansion" not in items:
        return None
    cost = constants.get("ChangeNickCost", 0)
    if not integer(cost) or "__checksum__" not in items:
        raise ValueError("Invalid nickname cost or static checksum")
    changes = {}
    if cost:
        constants["ChangeNickCost"] = 0
        changes["constants"] = constants
    if "inventoryexpansion" in items:
        rows = expansion_rows(items["inventoryexpansion"][1])
        if any(row["InvenExpandCost"] or row["InvenTotalExpandCost"] for row in rows):
            for row in rows:
                row.update(InvenExpandCost=0, InvenTotalExpandCost=0)
            changes["inventoryexpansion"] = rows
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
        prepared = prepare(parent(references, "static_data_get.bin", request))
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
