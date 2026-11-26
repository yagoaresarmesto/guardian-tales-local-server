# SPDX-License-Identifier: Apache-2.0
"""Skip rewards/payment for an explicitly configured regenerating village obstacle."""

import json
import time

from guardian_tales.accounts.snapshots import CLIENT

from .village import MAX_REVISION, MAX_TIME, current_village, integer

ROUTE = "/lobby-village/remove-obstacle"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS village_obstacle_mock_requests "
        "(operation_id TEXT PRIMARY KEY, building_id INTEGER NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / "village_obstacle_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Obstacle removal requires an explicit regenerating-obstacle mock catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "regenerating_specs"}
        or value["client"] != CLIENT
    ):
        raise ValueError("Invalid village obstacle mock catalog")
    specs = value["regenerating_specs"]
    if (
        not isinstance(specs, dict)
        or not 1 <= len(specs) <= 1000
        or any(
            not isinstance(k, str)
            or not k.isascii()
            or not k.isdecimal()
            or len(k) > 10
            or not integer(int(k), minimum=1)
            or str(int(k)) != k
            or not integer(v, 31536000, 1)
            for k, v in specs.items()
        )
    ):
        raise ValueError("Invalid regenerating obstacle specifications")
    return specs


def remove(account, body, operation_id, now=None):
    if (
        not isinstance(body, dict)
        or set(body) != {"buildingId"}
        or not integer(body["buildingId"], minimum=1)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Obstacle mock requires one buildingId after the prologue")
    village = current_village(account.db)
    building_id = body["buildingId"]
    previous = account.db.execute(
        "SELECT building_id FROM village_obstacle_mock_requests WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if previous:
        if previous[0] != building_id:
            raise ValueError("Obstacle retry differs from the saved request")
        return {"UserLobbyVillage": village}
    specs = load_catalog(account.references)
    buildings = village.get("Buildings")
    if (
        not integer(village.get("UserId"), MAX_REVISION, 1)
        or village["UserId"] != account.profile()["User"].get("Id")
        or not isinstance(buildings, list)
    ):
        raise ValueError("Invalid obstacle village owner or buildings")
    matches = [b for b in buildings if isinstance(b, dict) and b.get("Id") == building_id]
    if len(matches) != 1:
        raise ValueError("Obstacle must identify one owned village building")
    building = matches[0]
    if (
        not integer(building.get("SpecId"), minimum=1)
        or str(building["SpecId"]) not in specs
        or type(building.get("Status")) is not int
        or building["Status"] not in (0, 3)
        or not integer(building.get("EndTime"), MAX_TIME)
    ):
        raise ValueError("Only configured regenerating obstacles can be mocked")
    now = int(time.time()) if now is None else now
    interval = specs[str(building["SpecId"])]
    if not integer(now, MAX_TIME - interval, 1):
        raise ValueError("Invalid obstacle regeneration clock")
    changed = building["Status"] == 0 or building["EndTime"] <= now
    if changed:
        if not integer(village.get("Cas"), MAX_REVISION - 1):
            raise ValueError("Invalid obstacle village revision")
        # Keep the obstacle and its position; only restart its regeneration.
        # This explicit mock never charges soul points or grants a reward.
        building.update(Status=3, EndTime=now + interval)
        village["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "INSERT INTO village_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(village, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO village_obstacle_mock_requests VALUES(?,?)", (operation_id, building_id)
        )
    # Missing reward keys bypass the native item/hero reward branches.
    return {"UserLobbyVillage": village}
