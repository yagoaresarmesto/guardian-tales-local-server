# SPDX-License-Identifier: Apache-2.0
"""Persist discovered side-stage maps without entering or completing their stages."""

import json

from .campaign import FIRST_STAGE_ID, STAGE_OPENED


def discover_substage(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"StageId", "handleName"}
        or type(request["StageId"]) is not int
        or request["StageId"] != FIRST_STAGE_ID
        or not isinstance(request["handleName"], str)
        or not 1 <= len(request["handleName"]) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid side-stage map interaction")
    if account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
        FIRST_STAGE_ID,
    ):
        raise ValueError("Enter Inn before discovering its side-stage maps")
    catalog = account.references.json("substage_catalog.json")
    stages = catalog.get("stages") if isinstance(catalog, dict) else None
    maps = stages.get(str(FIRST_STAGE_ID)) if isinstance(stages, dict) else None
    if (
        not isinstance(maps, dict)
        or not 1 <= len(maps) <= 10000
        or any(
            not isinstance(name, str)
            or not 1 <= len(name) <= 200
            or type(target) is not int
            or not 0 < target <= 0x7FFFFFFF
            or target == FIRST_STAGE_ID
            for name, target in maps.items()
        )
    ):
        raise ValueError("Invalid external side-stage map catalog")
    target = maps.get(request["handleName"])
    if target is None:
        raise ValueError("Unknown side-stage map in the current stage")
    profile = account.profile()
    progress = profile["UserProgress"]
    key = str(target)
    state = progress["StageStates"].get(key, 0)
    if not state & STAGE_OPENED:
        progress["StageStates"][key] = state | STAGE_OPENED
        progress["Cas"] += 1
        with account.db:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"UserProgress": progress}
