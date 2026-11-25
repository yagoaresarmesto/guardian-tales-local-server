# SPDX-License-Identifier: Apache-2.0
"""Prepare the opening event for an owned Heavenhold dispatch base."""

import json
import random
from functools import lru_cache

from .raid_static import decode, records
from .village import MAX_REVISION, current_village, integer

PREPARE = "/lobby-village/prepare-dispatch"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS village_dispatch_prepare_requests "
        "(operation_id TEXT PRIMARY KEY, building_id INTEGER NOT NULL)"
    )


@lru_cache(maxsize=1)
def dispatch_bases(static_data):
    tables = records(decode(static_data))[1]
    try:
        data = json.loads(tables["lobbyvillage"][1])
        events = {row["Id"] for row in data["DispatchEvents"]}
        dispatches = {}
        for row in data["Dispatches"]:
            ident, starts = row["Id"], row["StartEvents"]
            if (
                not integer(ident, minimum=1)
                or ident in dispatches
                or not isinstance(starts, list)
                or not starts
                or any(not integer(evt, minimum=1) or evt not in events for evt in starts)
            ):
                raise ValueError("Invalid village dispatch or start events")
            dispatches[ident] = tuple(starts)
        bases = {}
        for row in data["LobbyBuildings"]:
            if row.get("PortalType") == "DispatchBase" and row.get("IsOpened") is True:
                ident, dispatch_id = row["Id"], row["DispatchId"]
                if (
                    ident in bases
                    or not integer(ident, minimum=1)
                    or not integer(dispatch_id, minimum=1)
                ):
                    raise ValueError("Invalid dispatch base definition")
                bases[ident] = (dispatch_id, dispatches[dispatch_id])
        return bases
    except (KeyError, TypeError) as error:
        raise ValueError("Missing village dispatch definitions in client static data") from error


def prepare(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"dispatchBuildingId"}
        or not integer(body["dispatchBuildingId"], minimum=1)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
    ):
        raise ValueError("Select an owned dispatch base")
    building_id = body["dispatchBuildingId"]
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        village = current_village(db)
        prior = db.execute(
            "SELECT building_id FROM village_dispatch_prepare_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if prior:
            if prior[0] != building_id:
                raise ValueError("Dispatch request identity belongs to another building")
            return {"UserLobbyVillage": village}
        buildings = village.get("Buildings")
        if not isinstance(buildings, list) or any(not isinstance(b, dict) for b in buildings):
            raise ValueError("Invalid saved village buildings")
        buildings = [b for b in buildings if b.get("Id") == building_id]
        if len(buildings) != 1 or not integer(buildings[0].get("Status"), maximum=0):
            raise ValueError("Dispatch preparation requires an idle, owned base")
        spec = buildings[0].get("SpecId")
        bases = dispatch_bases(account.references.read_bytes("static_data_get.bin"))
        if not integer(spec, minimum=1) or spec not in bases:
            raise ValueError("This building is not an open dispatch base")
        dispatch_id, starts = bases[spec]
        rows = village.get("Dispatches")
        if rows is None:
            rows = village["Dispatches"] = []
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError("Invalid saved village dispatches")
        matches = [r for r in rows if r.get("Id") == building_id]
        if len(matches) > 1:
            raise ValueError("Ambiguous saved dispatch for this building")
        row = matches[0] if matches else {}
        start = row.get("StartEventId", 0)
        if start:
            if row.get("DispatchId") != dispatch_id or not integer(start) or start not in starts:
                raise ValueError("Invalid saved dispatch opening event")
        else:
            if not integer(start) or not integer(village.get("Cas"), MAX_REVISION - 1):
                raise ValueError("Invalid saved dispatch or village revision")
            row.update(
                Id=building_id,
                DispatchId=dispatch_id,
                StartEventId=random.choice(starts),
                StartRewardGroupId=0,
                FinishEventId=0,
            )
            if not matches:
                rows.append(row)
            village["Cas"] += 1
            db.execute(
                "INSERT INTO village_state(id,value) VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(village, separators=(",", ":")),),
            )
        db.execute(
            "INSERT INTO village_dispatch_prepare_requests VALUES(?,?)", (operation_id, building_id)
        )
    return {"UserLobbyVillage": village}
