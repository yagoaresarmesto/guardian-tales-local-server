# SPDX-License-Identifier: Apache-2.0
"""Opt-in Guild War menu trial and reversible calendar activation commands."""

import argparse
import base64
import json
from datetime import datetime, timedelta

from .guild_menu import own_guild
from .guild_war_static import (
    FEATURE_ID,
    PHASES,
    ROUND_MODES,
    SELECTION,
    castle_specs,
    cooperative_stage_ids,
    defense_stage_ids,
    enable,
    load_selection,
    offense_stage_ids,
    utc_now,
)
from .presets import owned_party_preset
from .reference import ReferenceData

ROUTE = "/guild-war/enter"
CASTLES = "/guild-war/get-all-castle-simple-infos"
CASTLE_DETAIL = "/guild-war/get-castle-detail-info"
GUILD_SUMMARY = "/guild/get-guild-summary"
RECORDS = "/guild-war/get-battle-records"
RANKING = "/guild-war/get-ranking"
COIN_RANKING = "/guild-war/get-guild-coin-ranking"
START_COOP = "/guild-war/start-coop-stage"
END_COOP = "/guild-war/end-coop-stage/v2"
START_MULTI = "/guild-war/start-multi-stage"
END_MULTI = "/guild-war/end-multi-stage/v2"
ABANDON = "/guild-war/abandon-stage"
MAX_DAMAGE = 0x7FFFFFFFFFFFFFFF
UNLOCK = "/user/claim-unlock-feature-rewards"
LOBBY_GUIDE_PHASES = {2025: 3, 2026: 3, 2028: 4, 2029: 4}


def unlock(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"Feature"}
        or type(request["Feature"]) is not int
        or request["Feature"] != FEATURE_ID
        or load_selection(account.references) is None
    ):
        raise ValueError("Only the enabled local GuildWarSingle feature can be acknowledged")
    profile = account.profile()
    saved = profile["UserClaimedReward"]
    if (
        saved.get("UserId") != profile["User"]["Id"]
        or not isinstance(saved.get("UnlockFeature"), str)
        or len(saved["UnlockFeature"]) > 16384
    ):
        raise ValueError("Invalid saved feature-reward resource")
    bits = bytearray(base64.b64decode(saved["UnlockFeature"], validate=True))
    bits.extend(b"\0" * max(0, FEATURE_ID // 8 + 1 - len(bits)))
    bits[FEATURE_ID // 8] |= 1 << (FEATURE_ID % 8)
    # Client-only acknowledgment: no reward, database flag or fake stage clear.
    return {
        "UserClaimedReward": {
            "UserId": profile["User"]["Id"],
            "UnlockFeature": base64.b64encode(bits).decode(),
        },
        "AddedItems": [],
    }


def enter(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"isPartial"}
        or type(request["isPartial"]) is not bool
    ):
        raise ValueError("Guild War entry requires Boolean isPartial")
    selection = load_selection(account.references)
    if selection is None:
        raise ValueError("Activate the local trial with guild-war enable and restart the game")
    start, end = (datetime.fromisoformat(selection["period"][key]) for key in ("from", "to"))
    now = utc_now()
    if not start <= now < end:
        raise ValueError("Restart the game to refresh its Guild War calendar")
    defense_castle = selection.get("defend_castle", 0)
    attack_castle = selection.get("attack_castle", 0)
    if any(
        value and value not in castle_specs(account.references, selection)
        for value in (defense_castle, attack_castle)
    ):
        raise ValueError("The local trial castle is not in the enabled deployment")
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering Guild War")
    guild = own_guild(account, None)["Guild"]
    if guild is None:
        raise ValueError("Guild War requires owned guild membership")
    profile = account.profile()
    saved = profile.get("UserRaid")
    if saved is not None and (not isinstance(saved, dict) or saved.get("GuildWar") is not None):
        raise ValueError("Saved Guild War progression cannot be replaced by a fresh menu")
    next_update = min(
        (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0), end
    ).isoformat()
    # Native phases 1/2 select Coop and 3/4 select Multi. Cross-phase native
    # scene initialization can throw, so the trial phase is an explicit choice.
    return {
        "UserRaid": {
            "UserId": profile["User"]["Id"],
            "GuildWar": {
                "SeasonId": 1,
                "NextUpdateTime": next_update,
                "RewardedIds": [],
                "RetryCount": 0,
                "PlayCount": 0,
                "PlayedCharacters": [],
                "GuildWarCoin": 0,
                "PurchaseCounter": {},
            },
        },
        "GuildWarInfo": {
            "SeasonId": 1,
            "Phase": selection.get("phase", 1),
            "NextUpdateTime": next_update,
            "CanRewards": [],
            "CoopOffenseDamage": 0,
            "CoopDefenseDamage": 0,
            "MarkedCastleId": attack_castle,
            "CapturedCastleId": defense_castle,
            "LatestBattleCastleId": 0,
            "BuffIds": [],
            "GuildWarPoint": 0,
            "DailyAddedPoint": 0,
            "BattleStatus": {},
            "SeasonEnd": int(end.timestamp()),
        },
        "AddedItems": [],
    }


def lobby_guide_ids(account, tutorial_ids):
    requested = {
        value for value in tutorial_ids if type(value) is int and value in LOBBY_GUIDE_PHASES
    }
    if not requested:
        return set()
    phase = enter(account, {"isPartial": True})["GuildWarInfo"]["Phase"]
    if any(LOBBY_GUIDE_PHASES[value] != phase for value in requested):
        raise ValueError("Guild War lobby guides require their matching enabled local phase")
    # Matching tutorial2 groups only narrate/focus lobby UI. Acknowledgment
    # records seen help, without executing actions or validating a battle.
    return requested


def season_read_context(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"seasonId"}
        or type(request["seasonId"]) is not int
        or request["seasonId"] != 1
    ):
        raise ValueError("Guild War reads require native seasonId 1")
    return enter(account, {"isPartial": True})


def castle_infos(account, request):
    view = season_read_context(account, request)
    if view["GuildWarInfo"]["Phase"] not in (3, 4):
        return {"CastleSimpleInfos": []}
    specs = castle_specs(account.references, load_selection(account.references))
    castle = view["GuildWarInfo"]["CapturedCastleId"]
    owner = own_guild(account, None)["Guild"]["Id"] if castle else 0
    marked = view["GuildWarInfo"]["MarkedCastleId"]
    # Native Multi lobby needs a row for each selectable castle. The map comes
    # from the matching static deployment. Only an explicit defense selection
    # supplies local ownership; it never persists a captured castle.
    return {
        "CastleSimpleInfos": [
            {
                "CastleId": value,
                "CaptureGuildId": owner if value == castle else 0,
                "MarkingCount": int(value == marked),
                "CaptureDays": 0,
            }
            for value in specs
        ]
    }


def castle_detail(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"castleId"}
        or type(request["castleId"]) is not int
    ):
        raise ValueError("Guild War castle details require native castleId")
    view = enter(account, {"isPartial": True})
    if view["GuildWarInfo"]["Phase"] not in (3, 4):
        raise ValueError("Select a Dispute phase and reopen its lobby")
    specs = castle_specs(account.references, load_selection(account.references))
    if request["castleId"] not in specs:
        raise ValueError("Select a castle in the enabled Guild War deployment")
    owner = (
        own_guild(account, None)["Guild"]["Id"]
        if request["castleId"] == view["GuildWarInfo"]["CapturedCastleId"]
        else 0
    )
    # Native detail callback consumes int[], battle-detail[] and a dictionary
    # keyed by int64. The local ownership view carries no completed battle history.
    return {
        "CastleId": request["castleId"],
        "CaptureGuildId": owner,
        "CaptureDays": 0,
        "DefenseBuffIds": [],
        "TodayBattleStatus": [],
        "BattleHistory": {},
        "NotExistCastleData": False,
    }


def guild_summary(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"GuildId"}
        or type(request["GuildId"]) is not int
    ):
        raise ValueError("The local castle summary requires native GuildId")
    view = enter(account, {"isPartial": True})
    guild = own_guild(account, None)
    if not view["GuildWarInfo"]["CapturedCastleId"] or request["GuildId"] != guild["Guild"]["Id"]:
        raise ValueError("Only the enabled defense trial's owned guild summary is available")
    return {
        "GuildSummary": {
            "Guild": guild["Guild"],
            "GuildMembers": guild["GuildMembers"],
            "TotalDamage": None,
            "Rank": None,
        }
    }


def battle_records(account, request):
    season_read_context(account, request)
    # Native result-to-lobby synchronization consumes three arrays, including
    # daily status. This stateless trial has no saved battles or guild rankings.
    return {"LatestBattleRecords": [], "CoopDefenseInGuildRanking": [], "DailyBattleStatus": []}


def rankings(account, request):
    season_read_context(account, request)
    # Native fields are Int32 and RankingGuildEntry[]. Zero is the client's
    # untouched rank value; this local trial has no ranked defense results.
    return {"CoopDefenseMyGuildRank": 0, "CoopDefenseTopRanking": []}


def coin_rankings(account, request):
    season_read_context(account, request)
    # Native coin-rank synchronization consumes GuildWarCoinRewardRecord[].
    # No local battle points, settlement records or coin rewards are generated.
    return {"GuildCoinRanking": []}


def abandon_stage(account, request):
    if request is not None and (not isinstance(request, dict) or request):
        raise ValueError("Guild War abandonment accepts no parameters")
    enter(account, {"isPartial": True})
    # The native routine sends a parameterless request and yields it without
    # consuming response resources. The stateless trial has nothing to refund,
    # unlock or delete, and abandonment must not record a completed battle.
    return {}


def start_coop(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"stageId", "presetId"}
        or type(request["stageId"]) is not int
        or type(request["presetId"]) is not int
        or not 700 <= request["presetId"] < 800
    ):
        raise ValueError("Guild War cooperative entry requires native stageId and owned presetId")
    view = enter(account, {"isPartial": True})
    if view["GuildWarInfo"]["Phase"] not in (1, 2):
        raise ValueError("Select a cooperative Guild War phase and reopen its lobby")
    selection = load_selection(account.references)
    if request["stageId"] not in cooperative_stage_ids(account.references, selection):
        raise ValueError("Select a cooperative stage in the enabled Guild War season")
    owned_party_preset(account.db, account.profile(), request["presetId"])
    # The native success callback directly creates GuildWarStage and consumes
    # no response fields. This only acknowledges loading: no battle result,
    # attempt, character lock, selection, resource or progression is recorded.
    return {}


def check_result_request(request):
    if (
        not isinstance(request, dict)
        or set(request) != {"stageId", "damages", "additionalDamage"}
        or type(request["stageId"]) is not int
        or not isinstance(request["damages"], list)
        or len(request["damages"]) > 4
        or any(type(v) is not int or not 0 <= v <= MAX_DAMAGE for v in request["damages"])
        or type(request["additionalDamage"]) is not int
        or not 0 <= request["additionalDamage"] <= MAX_DAMAGE
        or sum(request["damages"]) + request["additionalDamage"] > MAX_DAMAGE
    ):
        raise ValueError("Guild War exit requires a stage and nonnegative int64 damages")


def end_coop(account, request):
    check_result_request(request)
    view = enter(account, {"isPartial": True})
    if view["GuildWarInfo"]["Phase"] not in (1, 2):
        raise ValueError("Select a cooperative Guild War phase and reopen its lobby")
    selection = load_selection(account.references)
    if request["stageId"] not in cooperative_stage_ids(account.references, selection):
        raise ValueError("Select a cooperative stage in the enabled Guild War season")
    # The native result callback refreshes GuildWarInfo and consumes AddedItems.
    # A free trial exit acknowledges the result without validating/persisting
    # damage, recording attempts/clears or granting rewards.
    return {"Cancelled": False, "GuildWarInfo": view["GuildWarInfo"], "AddedItems": []}


def multi_context(account, stage_id):
    view = enter(account, {"isPartial": True})
    selection = load_selection(account.references)
    stages = (
        offense_stage_ids(account.references, selection)
        if view["GuildWarInfo"]["Phase"] == 3
        else defense_stage_ids(account.references, selection)
    )
    if stage_id not in stages:
        raise ValueError("Select a native Fortress stage for the enabled local phase")
    return view


def start_multi(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"stageId", "presetId"}
        or type(request["stageId"]) is not int
        or type(request["presetId"]) is not int
        or not 700 <= request["presetId"] < 800
    ):
        raise ValueError("Fortress entry requires native stageId and owned presetId")
    multi_context(account, request["stageId"])
    owned_party_preset(account.db, account.profile(), request["presetId"])
    # Native Multi entry reads two int arrays before loading the local stage.
    # No trial guild/castle upgrades or buffs are manufactured.
    return {"GuildBuffIds": [], "CastleBuffIds": []}


def end_multi(account, request):
    check_result_request(request)
    view = multi_context(account, request["stageId"])
    # Acknowledge the local result without validating/storing damage, captures,
    # attempts or locks. Policy 5 also suppresses client-added coin/medal items.
    return {"Cancelled": False, "GuildWarInfo": view["GuildWarInfo"], "AddedItems": []}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Enable/disable the local Guild War season-1 menu trial"
    )
    parser.add_argument("action", choices=("enable", "disable", "status"))
    parser.add_argument("--reference-dir", help="Same reference directory as the backend")
    parser.add_argument(
        "--phase",
        choices=PHASES,
        help="Local trial phase; existing choice is retained when omitted",
    )
    parser.add_argument(
        "--defend-castle",
        type=int,
        help="Present one native castle as locally owned in multi-defense; 0 clears the mock",
    )
    parser.add_argument(
        "--attack-castle",
        type=int,
        help="Mark one native siege target in multi-offense without saving guild progress; 0 clears it",
    )
    parser.add_argument(
        "--round",
        dest="round_mode",
        choices=ROUND_MODES,
        help="Multi round timing: auto follows source hours; prep/combat select a local round",
    )
    parser.add_argument(
        "--skip-basic",
        action="store_true",
        help="Temporarily waive the basic-course prerequisite without recording stage clears",
    )
    args = parser.parse_args(argv)
    references = ReferenceData(args.reference_dir)
    try:
        if args.action == "enable":
            selection = enable(
                references,
                skip_basic=args.skip_basic,
                phase=PHASES[args.phase] if args.phase else None,
                defend_castle=args.defend_castle,
                attack_castle=args.attack_castle,
                round_mode=args.round_mode,
            )
        elif args.action == "disable":
            (references.directory / SELECTION).unlink(missing_ok=True)
            selection = None
        else:
            selection = load_selection(references)
        print(
            json.dumps(
                {
                    "enabled": selection is not None,
                    "season_id": selection["season_id"] if selection else None,
                    "skip_basic_requirement": (
                        selection.get("skip_basic", False) if selection else False
                    ),
                    "period": selection["period"] if selection else None,
                    "phase": selection.get("phase", 1) if selection else None,
                    "phase_name": (
                        next(
                            name
                            for name, value in PHASES.items()
                            if value == selection.get("phase", 1)
                        )
                        if selection
                        else None
                    ),
                    "local_defense_castle": selection.get("defend_castle", 0) if selection else 0,
                    "local_attack_castle": selection.get("attack_castle", 0) if selection else 0,
                    "round_mode": selection.get("round_mode", "auto") if selection else None,
                    "scope": "Experimental menus; free cooperative and Fortress siege/selected-castle defense entry/exit; persistent progression, score and rewards are not implemented",
                    "apply": "Fully close and reopen the game after enable/disable; Raid selection and saved account are retained",
                },
                indent=2,
            )
        )
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
