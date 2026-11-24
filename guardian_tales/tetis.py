# SPDX-License-Identifier: Apache-2.0
"""Native Tetis (RogueChess3) lobby, stage and progression requests."""

import json
from datetime import datetime, timezone

from .story_quests import grant, save_profile
from .tetis_progress import load_catalog, read_progress, save_progress, set_abilities, set_loadout
from .village import integer

BASE = "/rogue-chess3/"
ENTER = BASE + "enter"
START = BASE + "start-stage"
END = BASE + "end-stage"
RANK = BASE + "get-rank"
ABILITY = BASE + "set-ability"
LOADOUT = BASE + "set-artifact-spell"
MARK = BASE + "mark-narrative"
REWARD = BASE + "reward-narrative"
SWEEP = BASE + "sweep/v2"
EXCHANGE = "/exchange/rogue-chess"
ROUTES = (ENTER, START, END, RANK, ABILITY, LOADOUT, MARK, REWARD, SWEEP, EXCHANGE)


def fields(body, required=(), optional=()):
    if not isinstance(body, dict) or not set(required) <= body.keys() <= set(required) | set(
        optional
    ):
        raise ValueError("Unexpected Tetis request fields")


def resource(account, catalog, state, season, now):
    from .tetis_presets import group
    from .tetis_sweep import counter

    # The character-list editor numbers its slots 1700..1714. The mode's
    # legacy preset resource iterates the same list from 1 to 15.
    presets = {}
    for row in group(account.db)["Presets"]:
        if integer(row.get("Id"), minimum=1700, maximum=1714):
            ident = row["Id"] - 1699
            presets[str(ident)] = dict(row, Id=ident)
    # The client selects a spell and an artifact without giving a season ID.
    # It retains that same loadout when starting a floor in an older episode.
    season_data = state["seasonData"][str(season)].copy()
    loadout = state["seasonData"][str(catalog.current)]
    for key in ("SpellId", "ArtifactId", "Artifacts"):
        season_data[key] = loadout[key]
    return {
        "Presets": presets,
        "Floors": state["floors"],
        "SeasonId": season,
        "SeasonData": season_data,
        "Narratives": state["narratives"],
        "SweepCounter": counter(state, catalog, now),
    }


def stage(account, catalog, state, profile, route, body):
    key = "StartStageInfo" if route == START else "EndStageInfo"
    fields(body, (key,))
    info = body[key]
    if route == START:
        fields(info, ("SeasonId", "Floor"), ("ArtifactId", "SpellId"))
    else:
        fields(info, ("SeasonId", "Floor", "IsCleared"))
        if type(info["IsCleared"]) is not bool:
            raise ValueError("Tetis stage result requires IsCleared")
    season, floor = info["SeasonId"], info["Floor"]
    if not integer(season, minimum=1):
        raise ValueError("Invalid Tetis season")
    spec = catalog.floor_spec(season, floor)
    season_key = str(season)
    cleared = state["floors"][season_key]
    attempt = {"season": season, "floor": floor}
    if route == START:
        if floor > cleared + 1:
            raise ValueError("Clear the preceding Tetis floor first")
        set_loadout(
            catalog,
            state["seasonData"][str(catalog.current)],
            info.get("SpellId"),
            info.get("ArtifactId"),
        )
        state["active"] = attempt
        return season, {}
    if state["active"] != attempt:
        raise ValueError("Start this Tetis floor before reporting its result")
    state["active"] = None
    extra = {"AddedItems": [], "Exp": 0, "ArtifactIds": []}
    if info["IsCleared"] and floor > cleared:
        state["floors"][season_key] = floor
        # The client reuses floor layouts beyond the authored map. Their
        # original one-time prizes belong only to the actual authored floor.
        if floor in catalog.floors[season]:
            extra.update(grant(account, profile, spec.get("AchieveRewards") or []))
            data = state["seasonData"][season_key]
            xp = min(spec.get("PointReward", 0), catalog.max_experience - data["Exp"])
            data["Exp"] += xp
            extra["Exp"] = xp
    return season, extra


def narratives(account, catalog, state, profile, route, body):
    fields(body, ("NarrativeIds",))
    ids = body["NarrativeIds"]
    known = {n["Id"]: n for n in catalog.data["Narratives"]}
    if (
        not isinstance(ids, list)
        or len(ids) > len(known)
        or not all(integer(i, minimum=1) and i in known for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Choose known, distinct Tetis narratives")
    records = state["narratives"]
    rewards = []
    for ident in ids:
        key = str(ident)
        spec = known[ident]
        if route == MARK:
            if spec.get("UnlockFloor", 0) > state["floors"][str(spec["SeasonId"])] + 1:
                raise ValueError("This Tetis narrative is still locked")
            records.setdefault(key, 0)
        elif key not in records:
            raise ValueError("View the Tetis narrative before claiming its reward")
        elif not records[key]:
            records[key] = 1
            rewards.extend(catalog.data["Constants"]["RecordReward"])
    return grant(account, profile, rewards)


def mutate(account, catalog, state, profile, route, body, now):
    from .tetis_sweep import exchange, sweep

    season = catalog.current
    if route in (START, END):
        return stage(account, catalog, state, profile, route, body)
    if route in (MARK, REWARD):
        if state["active"]:
            season = state["active"]["season"]
        return season, narratives(account, catalog, state, profile, route, body)
    if route == ABILITY:
        fields(body, ("Abilities",))
        picks = body["Abilities"]
        if (
            not isinstance(picks, list)
            or len(picks) > len(catalog.nodes[season])
            or not all(integer(i) for i in picks)
        ):
            raise ValueError("Invalid Tetis ability selections")
        points = catalog.unpacked(picks)
        if len(points) != len(picks):
            raise ValueError("Duplicate Tetis ability")
        data = state["seasonData"][str(season)]
        set_abilities(catalog, data, season, data["Exp"], points)
        return season, {}
    if route == LOADOUT:
        fields(body, optional=("SpellId", "ArtifactId"))
        set_loadout(
            catalog, state["seasonData"][str(season)], body.get("SpellId"), body.get("ArtifactId")
        )
        return season, {}
    if route == SWEEP:
        fields(body, ("Count",))
        return season, sweep(account, profile, state, catalog, body["Count"], now)
    fields({} if body is None else body)
    return season, exchange(account, profile, state, catalog)


def handle(account, route, body, operation_id):
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering Tetis")
    catalog = load_catalog(account.references)
    now = datetime.now(timezone.utc)
    if route == RANK:
        fields(body, ("SeasonId",))
        if not integer(body["SeasonId"], minimum=1) or body["SeasonId"] not in catalog.seasons:
            raise ValueError("Unknown Tetis ranking season")
        return {"Rankings": [], "Mine": None}
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        state = read_progress(db, catalog)
        db.execute(
            "CREATE TABLE IF NOT EXISTS tetis_requests "
            "(id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL, "
            "season INTEGER NOT NULL, response TEXT NOT NULL, user_changed INTEGER NOT NULL)"
        )
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
        prior = db.execute(
            "SELECT route,request,season,response,user_changed FROM tetis_requests WHERE id=?",
            (operation_id,),
        ).fetchone()
        if prior:
            if prior[:2] != (route, encoded):
                raise ValueError("Tetis request sequence reused with different data")
            season, result, user_updated = prior[2], json.loads(prior[3]), prior[4]
            if user_updated:
                result["User"] = account.profile()["User"]
        else:
            if route == ENTER:
                fields(body, ("IsPartial",))
                if type(body["IsPartial"]) is not bool:
                    raise ValueError("Tetis entry expects an IsPartial cache hint")
                # A fresh map entry abandons an interrupted run; replaying an old
                # request must not cancel a subsequent attempt.
                if state["active"]:
                    state["active"] = None
                    save_progress(db, state)
                season, result = catalog.current, {"IsPartial": False}
            else:
                profile = account.profile()
                user_revision = profile["User"]["Cas"]
                season, result = mutate(account, catalog, state, profile, route, body, now)
                save_progress(db, state)
                if profile["User"]["Cas"] != user_revision:
                    save_profile(account, profile)
                    result["User"] = profile["User"]
            # Keep only the per-operation awards. Reconstruct mutable resources
            # on retries so an older packet cannot undo a newer edit on the client.
            extras = {k: v for k, v in result.items() if k != "User"}
            db.execute(
                "INSERT INTO tetis_requests VALUES(?,?,?,?,?,?)",
                (
                    operation_id,
                    route,
                    encoded,
                    season,
                    json.dumps(extras, separators=(",", ":")),
                    "User" in result,
                ),
            )
        result["UserRogueChess"] = resource(account, catalog, state, season, now)
        return result
