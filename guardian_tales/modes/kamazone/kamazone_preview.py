# SPDX-License-Identifier: Apache-2.0
"""Read-only Kama-ZONE entry, projecting seasonal menu benefits and local run state."""

import hashlib
from functools import lru_cache

from guardian_tales.settlement.village import integer

from . import kamazone, kamazone_practice, kamazone_run

ROUTE = "/kamazonland/enter"
RANKINGS = "/kamazonland/get-rankings"
ROUTES = (ROUTE, RANKINGS)


def selected_source(account):
    if account.needs_prologue():
        raise ValueError("Complete the prologue before opening the Kama-ZONE preview")
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
    if not kamazone.playable_season(source, selected["season_id"]):
        raise ValueError("Kama-ZONE preview requires a preserved Global season")
    return selected, source


def rankings(account, request):
    if request is not None and (not isinstance(request, dict) or request):
        raise ValueError("Kama-ZONE rankings accept no parameters")
    selected_source(account)
    # The native popup reads a Rankings list from its JSON resource. There is
    # no local scored run yet, and official rankings are never queried/copied.
    return {"Rankings": []}


@lru_cache(maxsize=2)
def mini_season_id(source, season_id):
    # Cache only an immutable static identity, keyed by the complete source and
    # season. Every action still validates selection and reads live local state.
    # Avoid decompressing and checking the complete pack on every run response.
    mode = kamazone.mode_data(source, season_id)
    season = kamazone.one(mode["Seasons"], "Id", season_id)
    group = season.get("MiniSeasonGroupId")
    minis = mode.get("MiniSeasons")
    if not integer(group, minimum=1) or not isinstance(minis, list):
        raise ValueError("Kama-ZONE preview requires the season's mini-season group")
    mini = kamazone.one(minis, "MiniSeasonGroupId", group)
    if not integer(mini.get("Id"), minimum=1):
        raise ValueError("Invalid Kama-ZONE preview mini-season")
    return mini["Id"]


def enter(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"IsPartial"}
        or type(request["IsPartial"]) is not bool
    ):
        raise ValueError("Kama-ZONE preview requires Boolean IsPartial")
    selected, source = selected_source(account)
    mini_id = mini_season_id(source, selected["season_id"])
    # Events may open this scene before showing the drawer. Its loader needs the
    # separate UserKamazonLand singleton, nonnull Progress/Likeability and lists.
    # An idle, concluded floor zero prevents the native Challenging predicate
    # from resuming a run. This view is never saved or added to the profile.
    response = {
        "NewSeason": False,
        "UserKamazonLand": {
            "SeasonId": selected["season_id"],
            "MiniSeasonId": mini_id,
            "Difficulty": -1,
            "ClearRecords": [],
            "ClearRecordsInSeason": [],
            "InfinityRecordInSeason": 0,
            "Characters": [],
            "Formation": {"Id": 0, "Positions": []},
            "SilverCoin": 0,
            "KamazonPoint": 0,
            "KamazonPointTotal": 0,
            "Benefits": [],
            "Trials": [],
            "Artifacts": [],
            "Curses": [],
            "Progress": {"Floor": 0, "CurrentNodeId": 0, "Concluded": True},
            "Nodes": [],
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
    response = kamazone_practice.project(
        account.references, source, selected["season_id"], response
    )
    return kamazone_run.project(account, source, selected["season_id"], response)
