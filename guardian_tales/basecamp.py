# SPDX-License-Identifier: Apache-2.0
"""Acknowledge guardian base camp collections and advance the camp clock."""

import json
import time

from .snapshots import CLIENT
from .village import MAX_REVISION, MAX_TIME, current_village, integer

ROUTE = "/lobby-village/harvest-basecamp"
MASTERY_POINTS = 70033


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS basecamp_harvest_requests "
        "(operation_id TEXT PRIMARY KEY, result TEXT NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / "basecamp_harvest_catalog.json"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Base-camp harvesting requires a matching camp catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or value.keys() - {"client", "portal_specs", "min_seconds", "debug_mastery_points"}
        or value.get("client") != CLIENT
        or not integer(value.get("min_seconds"), 86400, 1)
        or not integer(value.get("debug_mastery_points", 0))
        or not isinstance(value.get("portal_specs"), list)
        or not 1 <= len(value["portal_specs"]) <= 1000
        or any(not integer(i, minimum=1) for i in value["portal_specs"])
        or len(set(value["portal_specs"])) != len(value["portal_specs"])
    ):
        raise ValueError("Invalid base-camp harvest catalog")
    return value


def advance_camp_clock(user, village, catalog, now):
    if (
        not integer(now, MAX_TIME, 1)
        or not integer(village.get("UserId"), MAX_REVISION, 1)
        or village["UserId"] != user.get("Id")
        or not integer(user.get("GuardianMasteryLevel"))
    ):
        raise ValueError("Invalid base-camp clock or village owner")
    buildings = village.get("Buildings")
    if not isinstance(buildings, list) or len(buildings) > 1000:
        raise ValueError("Invalid saved village buildings")
    matches = [
        row
        for row in buildings
        if isinstance(row, dict)
        and type(row.get("SpecId")) is int
        and row["SpecId"] in catalog["portal_specs"]
    ]
    if (
        len(matches) != 1
        or not integer(matches[0].get("Id"), minimum=1)
        or type(matches[0].get("Status")) is not int
        or matches[0]["Status"] != 2
        or not integer(matches[0].get("EndTime"), MAX_TIME)
    ):
        raise ValueError("Harvesting requires one opened, producing guardian base camp")
    camp = matches[0]
    if camp["EndTime"] == 0 or now - camp["EndTime"] < catalog["min_seconds"]:
        return False
    if not integer(village.get("Cas"), MAX_REVISION - 1):
        raise ValueError("Invalid village revision")
    camp["EndTime"] = now
    village["Cas"] += 1
    return True


def harvest(account, body, operation_id, now=None):
    if (
        body not in (None, {})
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Base-camp harvesting accepts no parameters after the prologue")
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        village = current_village(db)
        user = account.profile()["User"]
        response = {"User": user, "UserLobbyVillage": village, "AddedItems": []}
        # Old receipts can contain a reward notice. Only their identity matters now.
        if db.execute(
            "SELECT 1 FROM basecamp_harvest_requests WHERE operation_id=?", (operation_id,)
        ).fetchone():
            return response
        catalog = load_catalog(account.references)
        now = int(time.time()) if now is None else now
        if advance_camp_clock(user, village, catalog, now):
            db.execute(
                "INSERT INTO village_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(village, separators=(",", ":")),),
            )
        db.execute("INSERT INTO basecamp_harvest_requests VALUES(?, '[]')", (operation_id,))
    return response
