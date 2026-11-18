# SPDX-License-Identifier: Apache-2.0
"""Explicit fixed mastery rewards for a preserved, upgraded guardian base camp."""

import json
import time

from .snapshots import CLIENT
from .village import INT_MAX, MAX_REVISION, MAX_TIME, current_village, integer

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
        raise ValueError("Base-camp harvesting requires an explicit debug reward catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "portal_specs", "min_seconds", "debug_mastery_points"}
        or value["client"] != CLIENT
        or not integer(value["min_seconds"], 86400, 1)
        or not integer(value["debug_mastery_points"], minimum=1)
        or not isinstance(value["portal_specs"], list)
        or not 1 <= len(value["portal_specs"]) <= 1000
        or any(not integer(i, minimum=1) for i in value["portal_specs"])
        or len(set(value["portal_specs"])) != len(value["portal_specs"])
    ):
        raise ValueError("Invalid explicit base-camp debug reward catalog")
    return value


def collect(user, village, catalog, now):
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
        return []
    assets = user.get("Assets")
    rows = (
        [a for a in assets if isinstance(a, dict) and a.get("Id") == MASTERY_POINTS]
        if isinstance(assets, list)
        else []
    )
    if len(rows) != 1 or not integer(rows[0].get("Amount")):
        raise ValueError("Harvesting requires one valid saved mastery-point asset")
    amount = catalog["debug_mastery_points"]
    if rows[0]["Amount"] > INT_MAX - amount:
        raise ValueError("Fixed mastery-point reward exceeds the supported balance")
    if any(not integer(v, MAX_REVISION - 1) for v in (user.get("Cas"), village.get("Cas"))):
        raise ValueError("Invalid account or village revision")
    # This is an opt-in debug policy, not inferred production. It intentionally
    # credits the configured mastery amount without normal guardian points,
    # gold conversion, ticket consumption or character/equipment changes.
    rows[0]["Amount"] += amount
    camp["EndTime"] = now
    user["Cas"] += 1
    village["Cas"] += 1
    return [{"ItemId": MASTERY_POINTS, "Amount": amount}]


def harvest(account, body, operation_id, now=None):
    if (
        body not in (None, {})
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Base-camp harvesting accepts no parameters after the prologue")
    profile = account.profile()
    village = current_village(account.db)
    previous = account.db.execute(
        "SELECT result FROM basecamp_harvest_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        return {
            "User": profile["User"],
            "UserLobbyVillage": village,
            "AddedItems": json.loads(previous[0]),
        }
    catalog = load_catalog(account.references)
    now = int(time.time()) if now is None else now
    notices = collect(profile["User"], village, catalog, now)
    with account.db:
        if notices:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
            account.db.execute(
                "INSERT INTO village_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(village, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO basecamp_harvest_requests VALUES(?,?)",
            (operation_id, json.dumps(notices, separators=(",", ":"))),
        )
    return {"User": profile["User"], "UserLobbyVillage": village, "AddedItems": notices}
