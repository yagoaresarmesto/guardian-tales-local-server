# SPDX-License-Identifier: Apache-2.0
"""Read-only idle lobby needed when Events automatically selects Kama-ZONE."""

import hashlib
import json

from . import kamazone
from .raid_static import decode, records
from .village import integer

ROUTE = "/kamazonland/enter"


def enter(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"IsPartial"}
        or type(request["IsPartial"]) is not bool
        or account.needs_prologue()
    ):
        raise ValueError("Kama-ZONE preview requires Boolean IsPartial and a completed prologue")
    references = account.references
    selected = kamazone.load(references)
    if selected is None or selected["season_id"] is None:
        raise ValueError("Select a local Kama-ZONE season before opening its preview")
    source = references.read_bytes("static_data_get.bin")
    if hashlib.sha256(source).hexdigest() != selected["source_sha256"]:
        raise ValueError("Kama-ZONE preview belongs to another content pack")
    now = kamazone.utc_now()
    if not (
        kamazone.timestamp(selected["period"]["From"])
        <= now
        < kamazone.timestamp(selected["period"]["RewardUntil"])
    ):
        raise ValueError("Kama-ZONE preview window has expired; select the season again")
    if selected["season_id"] not in kamazone.catalog(source):
        raise ValueError("Kama-ZONE preview requires a preserved Global season")
    mode = json.loads(records(decode(source))[1]["kamazonland2"][1])
    season = kamazone.one(mode["Seasons"], "Id", selected["season_id"])
    group = season.get("MiniSeasonGroupId")
    minis = mode.get("MiniSeasons")
    if not integer(group, minimum=1) or not isinstance(minis, list):
        raise ValueError("Kama-ZONE preview requires the season's mini-season group")
    mini = kamazone.one(minis, "MiniSeasonGroupId", group)
    if not integer(mini.get("Id"), minimum=1):
        raise ValueError("Invalid Kama-ZONE preview mini-season")
    # Events may open this scene before showing the drawer. Its loader needs the
    # separate UserKamazonLand singleton, nonnull Progress/Likeability and lists.
    # An idle, concluded floor zero prevents the native Challenging predicate
    # from resuming a run. This view is never saved or added to the profile.
    return {
        "NewSeason": False,
        "UserKamazonLand": {
            "SeasonId": selected["season_id"],
            "MiniSeasonId": mini["Id"],
            "Difficulty": -1,
            "ClearRecords": [],
            "ClearRecordsInSeason": [],
            "InfinityRecordInSeason": 0,
            "Characters": [],
            "Formation": {"Id": 0, "Positions": []},
            "SilverCoin": 0,
            "KamazonPoint": 0,
            "KamazonPointTotal": 0,
            "Benefits": {},
            "Trials": [],
            "Artifacts": [],
            "Curses": [],
            "Progress": {"Floor": 0, "CurrentNodeId": 0, "Concluded": True},
            "Nodes": {},
            "Hps": {},
            "KnownEvents": [],
            "KnownChoices": [],
            "KnownRandomConclusions": [],
            "KnownHiddenBattlePresets": [],
            "ProgressInSeason": {},
            "ProgressInChallenge": {},
            "KamazonEventPoint": 0,
            "KamazonTicket": 0,
            "Likeability": {"Points": 0, "ClaimedRewardStep": 0},
        },
    }
