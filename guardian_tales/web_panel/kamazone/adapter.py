# SPDX-License-Identifier: Apache-2.0
"""Expose the same Global season catalog and selection as the Kama-ZONE CLI."""

from ... import kamazone
from ...village import integer
from ..artwork import KAMAZONE


def state(references):
    current = kamazone.status(references)
    return {
        "seasonId": current["selected_season_id"],
        "phase": current["calendar_phase"],
        "period": current["local_period"],
        "revision": current["generation"],
        "seasons": [{"id": row["season_id"], "name": row["name"]} for row in current["seasons"]],
        "hasArt": KAMAZONE.available(references),
    }


def apply(references, body):
    if not isinstance(body, dict) or not integer(body.get("revision")):
        raise ValueError("Reload the season calendar before applying.")
    if body.get("action") == "disable" and body.keys() == {"action", "revision"}:
        season_id = None
    elif (
        body.get("action") == "select"
        and body.keys() == {"action", "revision", "seasonId"}
        and integer(body["seasonId"], minimum=1)
    ):
        season_id = body["seasonId"]
    else:
        raise ValueError(
            "Choose a season from the Global catalog or restore the original calendar."
        )
    kamazone.change_season(references, season_id, expected_generation=body["revision"])
