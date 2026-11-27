# SPDX-License-Identifier: Apache-2.0
"""Local guild views, entry prerequisites and an explicit no-reward attendance mock."""

import hashlib
import json

CASTLE_ENTER = "/guild-castle/enter"
CASTLE_LEAVE = "/guild-castle/leave"
SCARECROW_INDIVIDUAL = "/guild-castle/get-scarecrow-individual-rankings"
SCARECROW_GUILD = "/guild-castle/get-scarecrow-guild-rankings"
# The client indexes each response list by the bit position of its element.
SCARECROW_RECORDS = (
    "ScarecrowBasic",
    "ScarecrowFire",
    "ScarecrowIce",
    "ScarecrowEarth",
    "ScarecrowLight",
    "ScarecrowDark",
)

GUILD_MENU_ROUTES = (
    "/guild/get-my-guild",
    "/guild/red-dot",
    "/guild-raid2/reset",
    "/guild/claim-guild-daily-attendance",
    CASTLE_ENTER,
    CASTLE_LEAVE,
    SCARECROW_INDIVIDUAL,
    SCARECROW_GUILD,
)


def _saved_member(profile):
    member = profile.get("GuildMember")
    if member is None:
        return None
    if (
        not isinstance(member, dict)
        or type(member.get("UserId")) is not int
        or member["UserId"] != profile["User"]["Id"]
    ):
        raise ValueError("Saved guild membership must belong to the local user")
    guild_id = member.get("GuildId")
    if guild_id is None or type(guild_id) is int and guild_id == 0:
        return None
    if type(guild_id) is not int or not 1 <= guild_id <= 0x7FFFFFFF:
        raise ValueError("Invalid saved guild identity")
    return member


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
    member = _saved_member(account.profile())
    if member is None:
        return {"Hash": 0, "Guild": None, "GuildMember": None, "GuildMembers": []}
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
        "Id": member["GuildId"],
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


def _scarecrow_rankings(records):
    if records is None:
        records = {}
    if not isinstance(records, dict):
        raise ValueError("Invalid saved scarecrow records")
    scores = [records.get(key) for key in SCARECROW_RECORDS]
    if any(n is not None and (type(n) is not int or not 0 <= n < 2**63) for n in scores):
        raise ValueError("Invalid saved scarecrow score")
    return {
        "Rankings": [[] for _ in SCARECROW_RECORDS],
        "MyRanking": [None] * len(SCARECROW_RECORDS),
        "MyScore": scores,
    }


def read(account, route, request):
    if route in (CASTLE_ENTER, CASTLE_LEAVE, SCARECROW_INDIVIDUAL, SCARECROW_GUILD):
        if request is not None and request != {}:
            raise ValueError("Guild Castle requests accept no parameters")
        if route == CASTLE_LEAVE:
            return {}
        profile = account.profile()
        member = _saved_member(profile)
        if member is None:
            raise ValueError("Guild Castle requires guild membership")
        if route == SCARECROW_INDIVIDUAL:
            return _scarecrow_rankings(member.get("UserRecords"))
        if route == SCARECROW_GUILD:
            return _scarecrow_rankings(None)
        user = profile["User"]
        if type(user.get("Id")) is not int or not 1 <= user["Id"] <= 0x7FFFFFFF:
            raise ValueError("Invalid Guild Castle host identity")
        visitor = {"Id": user["Id"]}
        if isinstance(user.get("Name"), str):
            visitor["Name"] = user["Name"]
        # The scene resolves the host from CastleUsers and uses its local player for this ID.
        return {"CastleUsers": [visitor], "HostUserId": user["Id"]}
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
