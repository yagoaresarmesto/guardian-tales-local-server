# SPDX-License-Identifier: Apache-2.0
"""Opt-in fresh raid views, combat-loading trial and external season selection."""

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.content.reference import ReferenceData
from guardian_tales.runtime.state_lock import StateLock

from .guild_menu import own_guild

ENTRY_ROUTE = "/guild-raid2/enter"
START_STAGE = "/guild-raid2/start-stage"
END_STAGE = "/guild-raid2/end-stage"
MAX_STAGE_DAMAGE = 0x7FFFFFFFFFFFFFFF
GUILD_RANKINGS = "/guild-raid2/get-guild-rankings"
MEMBER_RANKINGS = "/guild-raid2/get-member-rankings"
RANKING_ROUTES = (GUILD_RANKINGS, MEMBER_RANKINGS)
UPDATE_STATUS = "/guild-raid2/update-status"
BATTLE_STATUS = "/guild-raid2/get-battle-status"
LATEST_RECORDS = "/guild-raid2/get-battle-records/latest"
BOSS_RECORDS = "/guild-raid2/get-battle-records/boss"
MEMBER_RECORDS = "/guild-raid2/get-battle-records/member"
MENU_READ_ROUTES = (UPDATE_STATUS, BATTLE_STATUS, LATEST_RECORDS, BOSS_RECORDS, MEMBER_RECORDS)
CATALOG = "guild_raid_entry_catalog.json"
SELECTION = "guild_raid_selection.json"
SELECTION_LOCK = ".raid_season.lock"


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
    return find_season(catalog, season_id, selection)


def load_selection(references):
    from .raid_static import MANIFEST_KEYS, validate_manifest

    path = references.directory / SELECTION
    if path.exists():
        if not path.is_file() or path.stat().st_size > 1024:
            raise ValueError("Invalid local raid selection file")
        selection = references.json(SELECTION)
        if (
            not isinstance(selection, dict)
            or set(selection) - {"rotation_tables", "custom_season"}
            not in ({"client", "season_id"}, {"client", "season_id"} | MANIFEST_KEYS)
            or selection["client"] != CLIENT
            or not integer(selection["season_id"])
        ):
            raise ValueError("Invalid local raid selection")
        if MANIFEST_KEYS <= selection.keys():
            validate_manifest(selection)
        if "rotation_tables" in selection and (
            selection["rotation_tables"] is not True or not MANIFEST_KEYS <= selection.keys()
        ):
            raise ValueError("Invalid local Raid rotation flag")
        if "custom_season" in selection:
            custom = selection["custom_season"]
            validate_season(custom)
            if (
                not selection.get("rotation_tables")
                or custom["season_id"] != selection["season_id"]
            ):
                raise ValueError("Invalid local Raid rotation selection")
        return selection
    return None


def find_season(catalog, season_id, selection=None):
    if integer(season_id):
        for season in catalog["seasons"]:
            if season["season_id"] == season_id:
                if selection is not None and selection["season_id"] == season_id:
                    return selection.get("custom_season", season)
                return season
    raise ValueError("Unknown local raid season; use raid-season list")


class RaidSelectionChanged(ValueError):
    """A browser submitted a selection based on an older Raid revision."""


def select_season(
    references, season_id=None, *, lineup=None, hp_per_bar=None, expected_revision=None
):
    if hp_per_bar is not None and (lineup is None or not integer(hp_per_bar)):
        raise ValueError("Custom Raid HP per bar must be a positive 32-bit integer")
    catalog = load_catalog(references)
    if lineup is None:
        season = find_season(catalog, season_id)
    else:
        season = min(catalog["seasons"], key=lambda s: s["season_id"])
    with StateLock(references.directory, filename=SELECTION_LOCK):
        previous = load_selection(references) or {}
        if expected_revision is not None and expected_revision != previous.get(
            "static_data_revision", 0
        ):
            raise RaidSelectionChanged(
                "The Raid selection changed. Reload the panel before applying."
            )
        return publish_selection(references, season, lineup, hp_per_bar, previous)


def publish_selection(references, season, lineup, hp_per_bar, previous):
    from .raid_static import atomic_replace, prepare

    manifest = prepare(
        references,
        season,
        previous.get("static_data_revision", 0),
        lineup=lineup,
        rotation_tables=previous.get("rotation_tables", False),
        hp_per_bar=hp_per_bar,
    )
    # Publish the immutable static body before atomically switching selection.
    # The client must reload its tables; SQLite and global time are untouched.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=references.directory, prefix=".raid-", delete=False
        ) as stream:
            temporary = stream.name
            json.dump({"client": CLIENT, "season_id": season["season_id"], **manifest}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace(temporary, references.directory / SELECTION)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return manifest.get("custom_season", season)


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


def start_stage(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"BossIdx", "IsFever"}
        or not integer(request["BossIdx"])
        or request["BossIdx"] > 4
        or type(request["IsFever"]) is not bool
    ):
        raise ValueError("Local raid stage entry requires boss slot 1-4 and Boolean IsFever")
    season = selected_season(account.references, local_context(account))
    fresh_profile(account)
    if not any(b["slot"] == request["BossIdx"] for b in season["bosses"]):
        raise ValueError("Requested raid boss slot is not configured")
    # Native success uses its existing boss, round and party to load the stage
    # when Cancelled is false. This trial has no cost or persisted attempt.
    return {"Cancelled": False}


def end_stage(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"Damages"}
        or not isinstance(request["Damages"], list)
        or len(request["Damages"]) > 4
        or any(
            type(value) is not int or not 0 <= value <= MAX_STAGE_DAMAGE
            for value in request["Damages"]
        )
        or sum(request["Damages"]) > MAX_STAGE_DAMAGE
    ):
        raise ValueError("Local raid completion requires up to four nonnegative int64 damages")
    selected_season(account.references, local_context(account))
    fresh_profile(account)
    # Native end success passes AddedItems to the result event. An empty list
    # closes the free trial without inventory, attempts or raid-progress updates.
    return {"Cancelled": False, "AddedItems": []}


def menu_read(account, route, request):
    if route == UPDATE_STATUS:
        if request is not None and (not isinstance(request, dict) or request):
            raise ValueError("Local raid status refresh accepts no parameters")
        catalog = local_context(account)
        selected_season(account.references, catalog)
        fresh_profile(account)
        return {"FeverBossIdx": 0, "Round": 1, "RoundExp": 0}
    keys = {
        BATTLE_STATUS: {"SeasonId"},
        LATEST_RECORDS: {"SeasonId", "Count"},
        BOSS_RECORDS: {"SeasonId", "BossId"},
        MEMBER_RECORDS: {"SeasonId", "Day", "UserId"},
    }.get(route)
    if keys is None:
        raise ValueError("Unsupported local raid menu read")
    if (
        not isinstance(request, dict)
        or set(request) != keys
        or any(
            not integer(value, 0 if key in ("Count", "Day") else 1)
            for key, value in request.items()
        )
    ):
        raise ValueError("Local raid history requires exact native integer fields")
    season = find_season(
        local_context(account), request["SeasonId"], load_selection(account.references)
    )
    if route == BOSS_RECORDS and request["BossId"] not in {b["id"] for b in season["bosses"]}:
        raise ValueError("Requested raid boss must belong to the requested season")
    if route == MEMBER_RECORDS and request["UserId"] != account.profile()["User"]["Id"]:
        raise ValueError("Local raid member history is available only for the saved local user")
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
    for action in ("list", "set", "custom"):
        command = commands.add_parser(action)
        command.add_argument("--reference-dir", help="Same reference directory as the backend")
        if action == "set":
            command.add_argument("season_id", type=int)
        elif action == "custom":
            command.add_argument("lineup", help="Four comma-separated boss and element pairs")
            command.add_argument(
                "--hp-per-bar", type=int, help="Practice HP per bar for all four bosses"
            )
    args = parser.parse_args(argv)
    references = ReferenceData(args.reference_dir)
    try:
        if args.action in ("set", "custom"):
            from .guild_war_static import SELECTION as WAR_SELECTION

            if args.action == "custom":
                from .raid_custom import parse_lineup

                lineup = parse_lineup(args.lineup)
                season = select_season(references, lineup=lineup, hp_per_bar=args.hp_per_bar)
            else:
                season = select_season(references, args.season_id)
            result = {
                "selected_season_id": season["season_id"],
                "apply": "Fully close and reopen the game so its static tables reload; reconnect is insufficient",
                "scope": "Selected raid's global calendar is locally active; other modes and global time are preserved; combat is experimental",
            }
            if (references.directory / WAR_SELECTION).exists():
                result["scope"] = "Selected lineup is available for off-season Raid practice"
                result["visibility"] = (
                    "Open Guild Raid from the Guild menu while Guild War is active"
                )
            if args.action == "custom":
                result["lineup"] = [
                    f"{boss.title()} ({element.title()})" for boss, element in lineup
                ]
                result["hp_per_bar"] = season["first_round"]["boss_hp_bar"]
        else:
            catalog = load_catalog(references)
            selection = load_selection(references)
            selected = selection["season_id"] if selection else catalog["default_season_id"]
            find_season(catalog, selected)
            print("Selected  Season  Boss set  Original global period (UTC)")
            for season in sorted(catalog["seasons"], key=lambda s: s["season_id"]):
                marker = "*" if season["season_id"] == selected else " "
                if marker == "*" and selection and "custom_season" in selection:
                    season = selection["custom_season"]
                    marker = "* custom"
                period = season["period"]
                print(
                    f"{marker:>8}  {season['season_id']:>6}  {season['boss_set']:>8}  "
                    f"{period['from']} - {period['to']}"
                )
            if selection is not None and "static_data_sha256" in selection:
                print("Local calendar prepared. Fully restart the game after each selection.")
            else:
                print("Calendar not prepared. Run raid-season set ID, then fully restart the game.")
            return
    except (ValueError, OSError, TypeError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
