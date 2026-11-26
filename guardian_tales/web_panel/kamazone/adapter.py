# SPDX-License-Identifier: Apache-2.0
"""Expose the same Global season catalog and selection as the Kama-ZONE CLI."""

from guardian_tales.modes.kamazone import kamazone
from guardian_tales.settlement.village import integer

from ..artwork import KAMAZONE
from .season_art import season_card


def state(references):
    current = kamazone.status(references)
    return {
        "seasonId": current["selected_season_id"],
        "phase": current["calendar_phase"],
        "period": current["local_period"],
        "revision": current["generation"],
        "seasons": [season_card(references, row) for row in current["seasons"]],
        "oldSeasons": [
            {
                "id": row["season_id"],
                "name": row["name"],
                "from": kamazone.timestamp(row["original_period"]["From"]).date().isoformat(),
                "to": kamazone.timestamp(row["original_period"]["To"]).date().isoformat(),
            }
            for row in current["old_seasons"]
        ],
        "oldActive": current["old_active"],
        "previousEventId": current["previous_event_season_id"],
        "hasArt": KAMAZONE.available(references),
    }


def apply(references, body):
    if not isinstance(body, dict) or not integer(body.get("revision")):
        raise ValueError("Reload the season calendar before applying.")
    action = body.get("action")
    if action in ("disable", "leave-old") and body.keys() == {"action", "revision"}:
        season_id = None
    elif (
        action in ("select", "select-old")
        and body.keys() == {"action", "revision", "seasonId"}
        and integer(body["seasonId"], minimum=1)
    ):
        season_id = body["seasonId"]
    else:
        raise ValueError(
            "Choose a season from the Global catalog or restore the original calendar."
        )
    kamazone.change_season(
        references,
        season_id,
        expected_generation=body["revision"],
        old=action == "select-old",
        leave_old=action == "leave-old",
    )
