# SPDX-License-Identifier: Apache-2.0
"""Opt-in fresh local raid menu; battle authorization/results are separate."""

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

from .guild_menu import own_guild
from .reference import ReferenceData
from .snapshots import CLIENT

ENTRY_ROUTE = "/guild-raid2/enter"
GUILD_RANKINGS = "/guild-raid2/get-guild-rankings"
MEMBER_RANKINGS = "/guild-raid2/get-member-rankings"
RANKING_ROUTES = (GUILD_RANKINGS, MEMBER_RANKINGS)
UPDATE_STATUS = "/guild-raid2/update-status"
BATTLE_STATUS = "/guild-raid2/get-battle-status"
LATEST_RECORDS = "/guild-raid2/get-battle-records/latest"
MENU_READ_ROUTES = (UPDATE_STATUS, BATTLE_STATUS, LATEST_RECORDS)
CATALOG = "guild_raid_entry_catalog.json"
SELECTION = "guild_raid_selection.json"


def integer(value, minimum=1):
    return type(value) is int and minimum <= value <= 0x7FFFFFFF


def load_catalog(references):
    path = references.directory / CATALOG
    if not path.is_file() or path.stat().st_size > 256 * 1024:
        raise ValueError("Local raid entry requires an explicit matching season catalog")
    value = references.json(CATALOG)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "client",
            "fresh_local",
            "default_season_id",
            "seasons",
            "daily_entries",
            "max_retry",
            "play_time_ms",
        }
        or value["client"] != CLIENT
        or value["fresh_local"] is not True
        or not integer(value["default_season_id"])
        or not integer(value["daily_entries"])
        or value["daily_entries"] > 100
        or not integer(value["max_retry"], 0)
        or value["max_retry"] > 100
        or not integer(value["play_time_ms"])
        or value["play_time_ms"] > 3600000
    ):
        raise ValueError("Invalid local raid season policy")
    seasons = value["seasons"]
    if not isinstance(seasons, list) or not 1 <= len(seasons) <= 1000:
        raise ValueError("Invalid local raid season list")
    for season in seasons:
        validate_season(season)
    ids = {s["season_id"] for s in seasons}
    if len(ids) != len(seasons) or value["default_season_id"] not in ids:
        raise ValueError("Duplicate raid seasons or unknown default season")
    return value


def validate_season(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"season_id", "boss_set", "round_set", "period", "bosses", "first_round"}
        or any(not integer(value[k]) for k in ("season_id", "boss_set", "round_set"))
    ):
        raise ValueError("Invalid local raid season")
    period, bosses, first = (value[k] for k in ("period", "bosses", "first_round"))
    if not isinstance(period, dict) or set(period) != {"from", "to"}:
        raise ValueError("Invalid local raid season period")
    try:
        dates = [datetime.fromisoformat(period[k]) for k in ("from", "to")]
        if any(d.tzinfo is None or d.utcoffset() is None for d in dates) or dates[0] >= dates[1]:
            raise ValueError("Invalid local raid season period")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid local raid season period") from exc
    if (
        not isinstance(bosses, list)
        or len(bosses) != 4
        or any(
            not isinstance(b, dict)
            or set(b) != {"slot", "id", "stage_id"}
            or any(not integer(b[k]) for k in b)
            for b in bosses
        )
        or sorted(b["slot"] for b in bosses) != [1, 2, 3, 4]
        or len({b["id"] for b in bosses}) != 4
        or len({b["stage_id"] for b in bosses}) != 4
        or not isinstance(first, dict)
        or set(first) != {"number", "score", "buff_level", "boss_hp_bar"}
        or type(first["number"]) is not int
        or first["number"] != 1
        or any(not integer(first[k]) for k in ("score", "boss_hp_bar"))
        or not integer(first["buff_level"], 0)
    ):
        raise ValueError("Invalid local raid boss or first-round catalog")


def selected_season(references, catalog=None):
    catalog = load_catalog(references) if catalog is None else catalog
    season_id = catalog["default_season_id"]
    selection = load_selection(references)
    if selection is not None:
        season_id = selection["season_id"]
    return find_season(catalog, season_id)


def load_selection(references):
    from .raid_static import MANIFEST_KEYS, validate_manifest

    path = references.directory / SELECTION
    if path.exists():
        if not path.is_file() or path.stat().st_size > 1024:
            raise ValueError("Invalid local raid selection file")
        selection = references.json(SELECTION)
        if (
            not isinstance(selection, dict)
            or set(selection)
            not in ({"client", "season_id"}, {"client", "season_id"} | MANIFEST_KEYS)
            or selection["client"] != CLIENT
            or not integer(selection["season_id"])
        ):
            raise ValueError("Invalid local raid selection")
        if MANIFEST_KEYS <= selection.keys():
            validate_manifest(selection)
        return selection
    return None


def find_season(catalog, season_id):
    if integer(season_id):
        for season in catalog["seasons"]:
            if season["season_id"] == season_id:
                return season
    raise ValueError("Unknown local raid season; use raid-season list")


def select_season(references, season_id):
    from .raid_static import prepare

    season = find_season(load_catalog(references), season_id)
    previous = load_selection(references)
    manifest = prepare(references, season, (previous or {}).get("static_data_revision", 0))
    # Publish the immutable static body before atomically switching selection.
    # The client must reload its tables; SQLite and global time are untouched.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=references.directory, prefix=".raid-", delete=False
        ) as stream:
            temporary = stream.name
            json.dump({"client": CLIENT, "season_id": season_id, **manifest}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, references.directory / SELECTION)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return season


def utc_now():
    return datetime.now(timezone.utc)


def local_context(account):
    if account.needs_prologue() or own_guild(account, None)["Guild"] is None:
        raise ValueError("Local raid reads require completed prologue and owned guild membership")
    return load_catalog(account.references)


def fresh_profile(account):
    profile = account.profile()
    saved = profile.get("UserRaid")
    if saved is not None and (not isinstance(saved, dict) or saved.get("Raid") is not None):
        raise ValueError(
            "Preserved raid progress needs its own validated contract; it is not reset"
        )
    return profile


def menu_read(account, route, request):
    if route == UPDATE_STATUS:
        if request is not None and (not isinstance(request, dict) or request):
            raise ValueError("Local raid status refresh accepts no parameters")
        catalog = local_context(account)
        selected_season(account.references, catalog)
        fresh_profile(account)
        return {"FeverBossIdx": 0, "Round": 1, "RoundExp": 0}
    if route not in (BATTLE_STATUS, LATEST_RECORDS):
        raise ValueError("Unsupported local raid menu read")
    keys = {"SeasonId", "Count"} if route == LATEST_RECORDS else {"SeasonId"}
    if (
        not isinstance(request, dict)
        or set(request) != keys
        or not integer(request["SeasonId"])
        or route == LATEST_RECORDS
        and not integer(request["Count"], 0)
    ):
        raise ValueError("Local raid history requires a season ID and native integer count")
    find_season(local_context(account), request["SeasonId"])
    # These are lists, not a synthetic completed fight or a profile resource.
    return {"Records": []} if route == BATTLE_STATUS else {"BattleRecords": []}


def rankings(account, route, request):
    if (
        route not in RANKING_ROUTES
        or not isinstance(request, dict)
        or set(request) != {"SeasonId"}
        or not integer(request["SeasonId"])
    ):
        raise ValueError("Local raid rankings require a catalogued integer SeasonId")
    # A timed refresh may still carry an earlier selection cached by the client.
    # Accept any known season without changing selection or emitting resources.
    find_season(local_context(account), request["SeasonId"])
    if route == GUILD_RANKINGS:
        # Native CutOff is Dictionary<int32, int64>, not a list or null.
        return {"Rankings": [], "CutOff": {}}
    return {"Rankings": []}


def enter(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"IsPartial"}
        or type(request["IsPartial"]) is not bool
    ):
        raise ValueError("Local raid entry requires a Boolean IsPartial")
    season = selected_season(account.references, local_context(account))
    profile = fresh_profile(account)
    now = utc_now().astimezone(timezone.utc)
    try:
        next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    except OverflowError as exc:
        raise ValueError("Local raid reset timestamp exceeds its range") from exc
    # The native resource handler populates the existing UserRaid object and
    # replaces only supplied properties. Omit all other-mode currencies/flags.
    return {
        "UserRaid": {
            "UserId": profile["User"]["Id"],
            "Raid": {
                "SeasonId": season["season_id"],
                "TotalDamage": 0,
                "PlayedGuildId": 0,
                "RoundClaimed": 0,
                "NextReset": next_reset.isoformat(),
                "RetryCount": 0,
                "PlayCount": 0,
                "PlayedCharacters": [],
                "PrevDamage": 0,
            },
        },
        "GuildRaidStatus": {
            "SeasonId": season["season_id"],
            "TotalDamage": 0,
            "PrevSeasonId": 0,
            "PrevDamage": 0,
            "RankRecord": 0,
        },
        "GuildRanking": None,
        "FeverBossIdx": 0,
        "Round": 1,
        "RoundExp": 0,
        "AddedItems": [],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Select fresh local raid content without rewards")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("list", "set"):
        command = commands.add_parser(action)
        command.add_argument("--reference-dir", help="Same reference directory as the backend")
        if action == "set":
            command.add_argument("season_id", type=int)
    args = parser.parse_args(argv)
    references = ReferenceData(args.reference_dir)
    try:
        if args.action == "set":
            season = select_season(references, args.season_id)
            result = {
                "selected_season_id": season["season_id"],
                "apply": "Fully close and reopen the game so its static tables reload; reconnect is insufficient",
                "scope": "Selected raid's global calendar is locally active; other modes and global time are preserved; combat is experimental",
            }
        else:
            catalog = load_catalog(references)
            selected = selected_season(references, catalog)["season_id"]
            print("Selected  Season  Boss set  Original global period (UTC)")
            for season in sorted(catalog["seasons"], key=lambda s: s["season_id"]):
                marker = "*" if season["season_id"] == selected else " "
                period = season["period"]
                print(
                    f"{marker:>8}  {season['season_id']:>6}  {season['boss_set']:>8}  "
                    f"{period['from']} - {period['to']}"
                )
            selection = load_selection(references)
            if selection is not None and "static_data_sha256" in selection:
                print("Local calendar prepared. Fully restart the game after each selection.")
            else:
                print("Calendar not prepared. Run raid-season set ID, then fully restart the game.")
            return
    except (ValueError, OSError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
