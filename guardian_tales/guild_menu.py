# SPDX-License-Identifier: Apache-2.0
"""Local guild views, entry prerequisites and an explicit no-reward attendance mock."""

import hashlib
import json

GUILD_MENU_ROUTES = (
    "/guild/get-my-guild",
    "/guild/red-dot",
    "/guild-raid2/reset",
    "/guild/claim-guild-daily-attendance",
)


def own_guild(account, request):
    if request is not None and request != {}:
        if (
            not isinstance(request, dict)
            or set(request) != {"Hash"}
            or (
                request["Hash"] is not None
                and (
                    type(request["Hash"]) is not int
                    or not -0x80000000 <= request["Hash"] <= 0x7FFFFFFF
                )
            )
        ):
            raise ValueError("Local guild reads accept only a nullable integer Hash")
    profile = account.profile()
    member = profile.get("GuildMember")
    empty = {"Hash": 0, "Guild": None, "GuildMember": None, "GuildMembers": []}
    if member is None:
        return empty
    if (
        not isinstance(member, dict)
        or type(member.get("UserId")) is not int
        or member["UserId"] != profile["User"]["Id"]
    ):
        raise ValueError("Saved guild membership must belong to the local user")
    guild_id = member.get("GuildId")
    if guild_id is None or type(guild_id) is int and guild_id == 0:
        return empty
    if type(guild_id) is not int or not 1 <= guild_id <= 0x7FFFFFFF:
        raise ValueError("Invalid saved guild identity")
    achievement = member.get("Achievement")
    points = {"Id": 0, "Points": 0}
    if achievement is not None:
        if not isinstance(achievement, dict) or any(
            type(achievement.get(k)) is not int or not 0 <= achievement[k] <= 0x7FFFFFFF
            for k in points
        ):
            raise ValueError("Invalid saved guild member achievement")
        points = {k: achievement[k] for k in points}
    # Guild details and the other members were not captured. This explicitly
    # named local view contains only the saved member and their achievement.
    # The ancient date, emblem and empty notices are display placeholders.
    guild = {
        "Id": guild_id,
        "Name": "Local guild",
        "CreatedAt": "2000-01-01T00:00:00+00:00",
        "Emblem": 0,
        "IsPublic": False,
        "Introduce": "",
        "Notice": "",
        "Notices": {"Notice": [], "RepresentativeNotice": 0},
        "MasterName": "",
        "MemberCount": 1,
        "ApplicantCount": 0,
        "IsApplicable": False,
        "Achievement": points,
    }
    result = {
        "Guild": guild,
        "GuildMember": member,
        "GuildMembers": [member],
        "Applicants": [],
        "DismissedMasterName": "",
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    # The native callback skips replacement when Hash is unchanged. Use a
    # stable nonzero content hash, distinct from the older empty view's zero.
    result["Hash"] = (
        int.from_bytes(hashlib.sha256(encoded).digest()[:4], "little") & 0x7FFFFFFF
    ) or 1
    return result


def read(account, route, request):
    if route == "/guild/claim-guild-daily-attendance":
        if request is not None and (not isinstance(request, dict) or request):
            raise ValueError("Guild attendance mock accepts no parameters")
        # Native callbacks consume AddedItems. The explicitly requested mock
        # returns an empty list without claiming attendance or changing state.
        return {"AddedItems": []}
    if route == "/guild/get-my-guild":
        return own_guild(account, request)
    if route == "/guild/red-dot":
        if request is not None and (not isinstance(request, dict) or request):
            raise ValueError("Local guild notification reads accept no parameters")
        return {"Raid": False, "Meteor": False, "PunchKing": False, "GuildWar": False}
    if route == "/guild-raid2/reset":
        if (
            not isinstance(request, dict)
            or set(request) != {"IsPartial"}
            or type(request["IsPartial"]) is not bool
        ):
            raise ValueError("Local raid menu preparation requires a Boolean IsPartial")
        # Entry callers inspect this flag before requesting rewards. No UserRaid
        # was captured; omit it instead of resetting cached seasons/currencies.
        return {"ClaimRaidSeasonReward": False}
    raise ValueError("Unsupported local guild menu read")
