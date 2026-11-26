# SPDX-License-Identifier: Apache-2.0
"""Read-only Backroom entry using client defaults without changing the saved account."""

import json
from functools import lru_cache

from guardian_tales.modes.guild.raid_static import decode, records
from guardian_tales.settlement.village import integer

ROUTE = "/my-room/enter"


@lru_cache(maxsize=2)
def default_media(body):
    _, tables = records(decode(body))
    if "items" not in tables:
        raise ValueError("Backroom entry requires the matching external items table")
    items = json.loads(tables["items"][1])
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= 100000
        or any(
            not isinstance(row, dict)
            or not integer(row.get("Id"), minimum=1)
            or not isinstance(row.get("Type"), str)
            for row in items
        )
        or len({row["Id"] for row in items}) != len(items)
    ):
        raise ValueError("Invalid Backroom item definitions")
    defaults = {"Wallpaper": [], "Music": []}
    for row in items:
        if row["Type"] != "MyRoomMedia" or row.get("GetMethod") != "Default":
            continue
        kind = row.get("MediaType")
        if kind not in defaults or type(row.get("Price")) is not int or row["Price"] != 0:
            raise ValueError("Backroom defaults must be free wallpaper or music definitions")
        defaults[kind].append(row["Id"])
    if any(len(values) != 1 for values in defaults.values()):
        raise ValueError("Backroom entry requires one default wallpaper and one default music item")
    return defaults["Wallpaper"][0], defaults["Music"][0]


def enter(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"IsPartial"}
        or type(request["IsPartial"]) is not bool
        or account.needs_prologue()
    ):
        raise ValueError("Backroom entry requires Boolean IsPartial and a completed prologue")
    user = account.profile()["User"]
    characters = user.get("Characters")
    if (
        not integer(user.get("Id"), minimum=1)
        or not isinstance(characters, list)
        or not characters
        or any(
            not isinstance(row, dict) or not integer(row.get("Id"), minimum=1) for row in characters
        )
    ):
        raise ValueError("Backroom entry requires a valid saved owner and owned character roster")
    owned = {row["Id"] for row in characters}
    representative = user.get("RepresentativeCharacterId")
    if len(owned) != len(characters) or (
        representative is not None
        and (not integer(representative) or representative != 0 and representative not in owned)
    ):
        raise ValueError("Invalid saved Backroom representative character")
    wallpaper, music = default_media(account.references.read_bytes("static_data_get.bin"))
    # UserMyRoom is a separate native singleton, absent from the imported profile.
    # Null Hero uses the current representative and costume. Wallpaper zero keeps
    # the bundled background, without downloading uncaptured standalone media.
    return {
        "UserMyRoom": {
            "Used": [wallpaper, music],
            "Hero": None,
            "X": 0.0,
            "Y": 0.0,
            "WallPaper": 0,
            "Music": music,
            "Favorites": [],
        },
        "NewGetItems": [],
    }
