# SPDX-License-Identifier: Apache-2.0
"""Persist discovered side-stage maps without entering or completing their stages."""

import json

from .campaign import STAGE_OPENED
from .story_handles import catalog as native_catalog
from .story_handles import map_events


def discover_substage(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"StageId", "handleName"}
        or type(request["StageId"]) is not int
        or not 0 < request["StageId"] <= 0x7FFFFFFF
        or not isinstance(request["handleName"], str)
        or not 1 <= len(request["handleName"]) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid side-stage map interaction")
    stage_id = request["StageId"]
    if account.db.execute("SELECT stage_id FROM campaign_session WHERE id=1").fetchone() != (
        stage_id,
    ):
        raise ValueError("Enter the stage before discovering its side-stage maps")
    catalog = (
        account.references.json("substage_catalog.json")
        if (account.references.directory / "substage_catalog.json").is_file()
        else {"stages": {}}
    )
    stages = catalog.get("stages") if isinstance(catalog, dict) else None
    maps = stages.get(str(stage_id), {}) if isinstance(stages, dict) else None
    if (
        not isinstance(maps, dict)
        or len(maps) > 10000
        or any(
            not isinstance(name, str)
            or not 1 <= len(name) <= 200
            or type(target) is not int
            or not 0 < target <= 0x7FFFFFFF
            or target == stage_id
            for name, target in maps.items()
        )
    ):
        raise ValueError("Invalid external side-stage map catalog")
    target = maps.get(request["handleName"])
    if target is None:
        event = (
            map_events(account.references, stage_id)
            .get("discoveries", {})
            .get(request["handleName"])
        )
        if event:
            target = native_catalog(account.references)["stage_ids"].get(event)
        if not target:
            raise ValueError("Unknown side-stage map in the current stage")
        target = int(target)
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
