# SPDX-License-Identifier: Apache-2.0
"""Selectable Dungeon Kingdom Arena practice, with independent battle receipts."""

import argparse
import json
from datetime import datetime, timedelta, timezone

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.content.reference import ReferenceData
from guardian_tales.teams.presets import DKA_PRESET_COUNT, owned_party_preset

from .guild_menu import own_guild

PREFIX = "/guild-punchking/"
ENTRY = PREFIX + "enter"
START = PREFIX + "start-stage"
END = PREFIX + "end-stage"
RANKINGS = tuple(PREFIX + "get-" + kind + "-rankings" for kind in ("guild", "member", "user"))
ROUTES = (ENTRY, START, END, *RANKINGS)
CATALOG = "guild_punchking_catalog.json"
SELECTION = "guild_punchking_selection.json"


def integer(value, minimum=0, maximum=0x7FFFFFFF):
    return type(value) is int and minimum <= value <= maximum


def utc_now():
    return datetime.now(timezone.utc)


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS punchking_active (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS punchking_requests (operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, token TEXT NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / CATALOG
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Dungeon Kingdom Arena requires a matching external practice catalog")
    value = references.json(CATALOG)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "practice_only", "variants"}
        or value["client"] != CLIENT
        or value["practice_only"] is not True
    ):
        raise ValueError("Invalid Dungeon Kingdom Arena practice policy")
    variants = value["variants"]
    if not isinstance(variants, list) or len(variants) != 3:
        raise ValueError("Configure exactly three Dungeon Kingdom Arena variants")
    for variant in variants:
        if (
            not isinstance(variant, dict)
            or set(variant) != {"id", "season_id", "calendar_id", "days"}
            or not integer(variant["id"], 1, 3)
            or not integer(variant["season_id"], 1)
            or not integer(variant["calendar_id"], 5300001, 5300999)
        ):
            raise ValueError("Invalid Dungeon Kingdom Arena variant")
        if not isinstance(variant["days"], list) or len(variant["days"]) != 7:
            raise ValueError("Each Dungeon Kingdom Arena variant needs seven days")
        for day in variant["days"]:
            if (
                not isinstance(day, dict)
                or set(day) != {"id", "monster_id", "stage_id", "weak_point", "element"}
                or any(not integer(day[k], 1) for k in ("id", "monster_id", "stage_id"))
                or day["weak_point"] not in ("Down", "Poison", "Aerial")
                or not isinstance(day["element"], str)
            ):
                raise ValueError("Invalid Dungeon Kingdom Arena monster/day catalog")
    if (
        {v["id"] for v in variants} != {1, 2, 3}
        or len({v["season_id"] for v in variants}) != 3
        or len({v["calendar_id"] for v in variants}) != 3
    ):
        raise ValueError("Dungeon Kingdom Arena variants must have distinct identities")
    return value


def window(day, now=None):
    now = (now or utc_now()).astimezone(timezone.utc)
    if not integer(day, 1, 7):
        raise ValueError("Choose a Dungeon Kingdom Arena day from 1 to 7")
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=day - 1)
    return today.date().isoformat(), {
        "from": start.isoformat(),
        "to": (start + timedelta(days=7, seconds=-1)).isoformat(),
    }


def selected(references):
    from .punchking_static import load_selection, raid_digest

    value = load_selection(references)
    if value is None:
        raise ValueError("Select a Dungeon Kingdom Arena variant with dka-season set")
    variant = next(v for v in load_catalog(references)["variants"] if v["id"] == value["variant"])
    if value["content_date"] != utc_now().date().isoformat() or value["raid_sha256"] != raid_digest(
        references
    ):
        raise ValueError("Restart the game to refresh Dungeon Kingdom Arena static data")
    return value, variant


def context(account):
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering Dungeon Kingdom Arena")
    guild = own_guild(account, None)["Guild"]
    if guild is None:
        raise ValueError("Dungeon Kingdom Arena requires owned guild membership")
    selection, variant = selected(account.references)
    profile = account.profile()
    saved = profile.get("UserRaid")
    if saved is not None and (not isinstance(saved, dict) or saved.get("PunchKingSeasonId", 0)):
        raise ValueError(
            "Preserved Dungeon Kingdom Arena progress needs its own validated contract"
        )
    start = datetime.fromisoformat(selection["period"]["from"])
    # Native status is a list of dated rows, each with a dictionary of user status.
    status = [
        {
            "Id": i,
            "Date": (start + timedelta(days=i)).isoformat(),
            "UserStatus": {
                str(profile["User"]["Id"]): {
                    "Damage": 0,
                    "Score": 0,
                    "Characters": [],
                    "PlayCount": 0,
                }
            },
        }
        for i in range(7)
    ]
    view = {
        "GuildId": guild["Id"],
        "PunchKingSeasonId": variant["season_id"],
        "PunchKingPoints": 0,
        "PunchKingStatus": status,
    }
    return selection, variant, profile, view


def handle(account, route, body, operation_id):
    if route == ENTRY:
        if (
            not isinstance(body, dict)
            or set(body) != {"IsPartial"}
            or type(body["IsPartial"]) is not bool
        ):
            raise ValueError("Arena entry requires Boolean IsPartial")
    elif route in RANKINGS:
        if body not in (None, {}):
            raise ValueError("Arena rankings accept no parameters")
    elif route == START:
        if (
            not isinstance(body, dict)
            or set(body) != {"MonsterId"}
            or not integer(body["MonsterId"], 1)
        ):
            raise ValueError("Arena stage entry requires its configured MonsterId")
    elif route == END:
        if (
            not isinstance(body, dict)
            or set(body) != {"Damage", "Abandoned"}
            or not integer(body["Damage"])
            or type(body["Abandoned"]) is not bool
        ):
            raise ValueError(
                "Arena completion requires nonnegative Int32 Damage and Boolean Abandoned"
            )
    else:
        raise ValueError("Unsupported Dungeon Kingdom Arena operation")
    selection, variant, profile, view = context(account)
    if route == ENTRY:
        return {
            "UserRaid": {
                "UserId": profile["User"]["Id"],
                "PunchKingSeasonId": variant["season_id"],
            },
            "GuildRaid": view,
        }
    if route in RANKINGS:
        return (
            {"Rankings": []}
            if route == RANKINGS[1]
            else {"Rankings": [], "MyRank": None, "MyScore": 0}
        )
    if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 200:
        raise ValueError("Arena stage requests require an operation identity")
    encoded = json.dumps({"route": route, "body": body}, sort_keys=True, separators=(",", ":"))
    token = selection["static_data_sha256"]
    previous = account.db.execute(
        "SELECT request,token FROM punchking_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous != (encoded, token):
            raise ValueError(
                "Arena request identity or selected variant/day conflicts with its receipt"
            )
    else:
        if route == START:
            if body["MonsterId"] != variant["days"][selection["day"] - 1]["id"]:
                raise ValueError(
                    "Arena boss differs from the selected variant/day; restart the game"
                )
            preset_id = profile["User"]["SelectedPresetId"].get("GuildPunchKing")
            if not integer(preset_id, 1300, 1300 + DKA_PRESET_COUNT - 1):
                raise ValueError("Choose an existing Dungeon Kingdom Arena team first")
            owned_party_preset(account.db, profile, preset_id)
        elif account.db.execute("SELECT token FROM punchking_active WHERE id=1").fetchone() != (
            token,
        ):
            raise ValueError("Finish a started battle under the same arena variant/day")
        with account.db:
            if route == START:
                account.db.execute(
                    "INSERT INTO punchking_active VALUES(1,?) ON CONFLICT(id) DO UPDATE SET token=excluded.token",
                    (token,),
                )
            else:
                account.db.execute("DELETE FROM punchking_active WHERE id=1")
            account.db.execute(
                "INSERT INTO punchking_requests VALUES(?,?,?)", (operation_id, encoded, token)
            )
    # Practice has no currency, reward, attempt, personal-best or official ranking writes.
    return (
        {"Messages": []}
        if route == START
        else {"GuildRaid": view, "Abandoned": body["Abandoned"], "IsRenew": False}
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Select Dungeon Kingdom Arena practice variant/day"
    )
    parser.add_argument("action", choices=("list", "set"))
    parser.add_argument("variant", type=int, nargs="?")
    parser.add_argument("--day", type=int, default=1)
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    refs = ReferenceData(args.reference_dir)
    try:
        if args.action == "set":
            from .punchking_static import select

            select(refs, args.variant, args.day)
            print(
                json.dumps(
                    {
                        "variant": args.variant,
                        "day": args.day,
                        "restart_game_required": True,
                        "practice_without_rewards": True,
                    }
                )
            )
        else:
            if args.variant is not None:
                raise ValueError("Use dka-season list, or dka-season set VARIANT --day DAY")
            print(json.dumps(load_catalog(refs), indent=2))
    except (ValueError, OSError) as error:
        parser.error(str(error))
