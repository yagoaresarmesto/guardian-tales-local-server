# SPDX-License-Identifier: Apache-2.0
"""Expand equipment storage to the selected catalog step without spending gems."""

import json
from functools import lru_cache

from .raid_static import decode, records
from .village import INT_MAX, MAX_REVISION, integer

ROUTE = "/user/expand-inventory"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS inventory_expansion_requests "
        "(operation_id TEXT PRIMARY KEY, target_step INTEGER NOT NULL)"
    )


def expansion_rows(content):
    rows = json.loads(content)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Missing inventory expansion steps")
    steps = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not integer(row.get("InvenExpandCount"), minimum=1)
            or not integer(row.get("InvenExpandCost"))
            or not integer(row.get("InvenTotalExpandCost"))
            or row["InvenExpandCount"] in steps
        ):
            raise ValueError("Invalid inventory expansion step")
        steps.add(row["InvenExpandCount"])
    return rows


@lru_cache(maxsize=2)
def rules(body):
    _, tables = records(decode(body))
    try:
        constants = json.loads(tables["constants"][1])
        base, slots = constants["DefaultInventoryLimit"], constants["InvenExpandAmount"]
        steps = frozenset(
            r["InvenExpandCount"] for r in expansion_rows(tables["inventoryexpansion"][1])
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("Missing inventory expansion catalog") from exc
    if (
        not integer(base, minimum=1)
        or not integer(slots, minimum=1)
        or base + max(steps) * slots > INT_MAX
    ):
        raise ValueError("Invalid inventory expansion capacity")
    return slots, steps


def expand(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"TargetStep"}
        or not integer(body["TargetStep"], minimum=1)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select a positive inventory expansion step after the prologue")
    target = body["TargetStep"]
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user = profile["User"]
        adjustment = user.get("InvenLimitAdj", 0)
        if not integer(adjustment) or not integer(user.get("Cas"), MAX_REVISION):
            raise ValueError("Invalid saved inventory capacity or revision")
        previous = db.execute(
            "SELECT target_step FROM inventory_expansion_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if previous and previous[0] != target:
            raise ValueError("Inventory expansion identity already belongs to another request")
        if not previous:
            slots, steps = rules(account.references.read_bytes("static_data_get.bin"))
            if target not in steps:
                raise ValueError("Unknown inventory expansion step")
            target_adjustment = target * slots
            if target_adjustment > adjustment:
                if user["Cas"] == MAX_REVISION:
                    raise ValueError("Inventory expansion revision overflow")
                adjustment = user["InvenLimitAdj"] = target_adjustment
                user["Cas"] += 1
                db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
            db.execute(
                "INSERT INTO inventory_expansion_requests VALUES(?,?)", (operation_id, target)
            )
    return {"User": {"Id": user["Id"], "Cas": user["Cas"], "InvenLimitAdj": adjustment}}
