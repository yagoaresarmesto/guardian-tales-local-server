# SPDX-License-Identifier: Apache-2.0
"""Read a fresh local meteor menu without excavating or delivering rewards."""

from datetime import datetime, timezone

from .guild_menu import own_guild
from .snapshots import CLIENT
from .village import integer

ROUTE = "/guild-meteor/enter"
CATALOG = "guild_meteor_entry_catalog.json"


def utc_now():
    return datetime.now(timezone.utc)


def load_catalog(references):
    path = references.directory / CATALOG
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Meteor entry requires a matching external season catalog")
    value = references.json(CATALOG)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "fresh_local", "seasons"}
        or value["client"] != CLIENT
        or value["fresh_local"] is not True
        or not isinstance(value["seasons"], list)
        or not 1 <= len(value["seasons"]) <= 1000
    ):
        raise ValueError("Invalid local meteor entry policy")
    dates, ids = [], set()
    for row in value["seasons"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "from"}
            or not integer(row["id"], minimum=1)
            or row["id"] in ids
            or not isinstance(row["from"], str)
        ):
            raise ValueError("Invalid meteor season identity")
        stamp = datetime.fromisoformat(row["from"])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Meteor season dates require a timezone")
        dates.append((stamp, row["id"]))
        ids.add(row["id"])
    if len({stamp for stamp, _ in dates}) != len(dates):
        raise ValueError("Meteor season dates must be unambiguous")
    return sorted(dates)


def enter(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"IsPartial"}
        or type(request["IsPartial"]) is not bool
    ):
        raise ValueError("Meteor entry requires Boolean IsPartial")
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering the guild meteor menu")
    guild = own_guild(account, None)["Guild"]
    if guild is None:
        raise ValueError("Meteor entry requires owned guild membership")
    profile = account.profile()
    saved = profile.get("UserRaid")
    if saved is not None and (
        not isinstance(saved, dict)
        or saved.get("MeteorSeasonId", 0) != 0
        or saved.get("MeteorClaimed", []) != []
    ):
        raise ValueError("Preserved meteor progression cannot be replaced by a fresh menu")
    past = [(stamp, sid) for stamp, sid in load_catalog(account.references) if stamp <= utc_now()]
    if not past:
        raise ValueError("No local meteor season has started")
    season_id = past[-1][1]
    # Empty native collections represent a fresh guild view. GetMeteorState
    # supplies each meteor's native untouched default when no status is saved.
    return {
        "UserRaid": {
            "UserId": profile["User"]["Id"],
            "MeteorSeasonId": season_id,
            "MeteorClaimed": [],
        },
        "GuildRaid": {
            "GuildId": guild["Id"],
            "MeteorSeasonId": season_id,
            "MeteorStatus": [],
            "ExcavationStatus": {},
        },
        "MeteorExcavation": [],
        "AddedItems": [],
    }
