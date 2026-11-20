# SPDX-License-Identifier: Apache-2.0
"""Read-only Colosseum lobby for the pinned European client."""

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .presets import owned_party_preset
from .raid_static import decode, records
from .village import integer

ENTRY = "/colosseum/enter"
OPPONENTS = "/colosseum/get-opponents"
REFRESH = "/colosseum/refresh-opponents"
RANKING = "/colosseum/get-my-ranking"
READ_ROUTES = (ENTRY, OPPONENTS, REFRESH, RANKING)


@lru_cache(maxsize=1)
def practice_season(body):
    _, tables = records(decode(body))
    if "colosseum" not in tables:
        raise ValueError("Missing Colosseum seasons")
    seasons = json.loads(tables["colosseum"][1]).get("Seasons", [])
    # The local lobby uses the latest season with a map in this client.
    return max(
        row["SeasonId"]
        for row in seasons
        if integer(row.get("SeasonId"), minimum=1)
        and integer(row.get("MapId", {}).get("KakaoGlobal"), minimum=1)
    )


def read(account, route, request):
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering Colosseum")
    if route not in READ_ROUTES:
        raise ValueError("Unsupported Colosseum read")
    if request not in (None, {}):
        if route != ENTRY:
            raise ValueError("Colosseum opponent and ranking reads accept no parameters")
        if (
            not isinstance(request, dict)
            or set(request) != {"IsPartial"}
            or type(request["IsPartial"]) is not bool
        ):
            raise ValueError("Colosseum entry expects a Boolean IsPartial cache hint")
    profile = account.profile()
    if route == RANKING:
        ranking = profile.get("UserColosseum", {}).get("Ranking")
        if ranking is None:
            ranking = profile["UserRecord"].get("ColosseumRank", 0)
        return {"Ranking": ranking or 0}
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reset = (midnight + timedelta(days=7 - now.weekday())).isoformat()
    # NeedRefresh compares server time to NextRefresh even with a cached empty list.
    # Renew the deadline on list reads as well, including a session crossing a reset.
    lobby = (
        {"Opponents": []}
        if route in (OPPONENTS, REFRESH)
        else {"SeasonUntil": reset, "DefenseBattleRecords": [], "NewSeason": False}
    )
    if "UserColosseum" in profile:
        return {**lobby, "UserColosseum": {**profile["UserColosseum"], "NextRefresh": reset}}
    user = profile["User"]
    record = profile["UserRecord"]
    preset_id = user.get("SelectedPresetId", {}).get("ColosseumAttack", 0)
    defense = None
    if preset_id:
        preset = owned_party_preset(account.db, profile, preset_id)
        defense = {"Preset": preset, "Formation": {"Id": 0, "Positions": [12, 3, 19, 9]}}
    season = practice_season(account.references.read_bytes("static_data_get.bin"))
    return {
        **lobby,
        "UserColosseum": {
            "SeasonId": season,
            "PrevSeasonId": season,
            "SeasonClaimed": True,
            "Trophy": record.get("ColosseumTrophy", 0),
            "Ranking": record.get("ColosseumRank") or None,
            "Win": 0,
            "Lose": 0,
            "Streak": 0,
            "OpponentIds": [],
            "Challenges": [],
            "Formations": {},
            "DefensePartyInfo": defense,
            "RefreshCount": 0,
            "NextRefresh": reset,
            "NextReset": reset,
            "Ticket": {
                "Type": 3,
                "PlayCount": 0,
                "RefillCount": 0,
                "NextCharge": None,
                "NextDailyReset": (midnight + timedelta(days=1)).isoformat(),
                "PlayLimitUpgradeExpireTime": None,
            },
        },
    }
