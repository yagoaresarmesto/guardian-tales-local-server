# SPDX-License-Identifier: Apache-2.0
"""Adapt a preserved permanent Kama-ZONE rotation to the installed Events lobby."""

import json

from . import kamazone
from .kamazone_themes import old_season_label
from .village import integer


def catalog(tables):
    if "kamazonland" not in tables:
        return {}
    old = json.loads(tables["kamazonland"][1])
    calendar = json.loads(tables["seasondate"][1])["EventPeriod"]
    events = json.loads(tables["kamazonland2"][1])["Seasons"]
    event_ids = {s["Id"] for s in events}
    event_calendars = {s["SeasonDateId"] for s in events}
    result = {}
    for season in old["Seasons"]:
        ident, calendar_id = season["Id"], season["SeasonDateId"]
        if not integer(ident, minimum=1) or not integer(calendar_id, minimum=1):
            raise ValueError("Invalid permanent Kama-ZONE season identity")
        period = kamazone.one(calendar, "Id", calendar_id)
        if kamazone.REGION not in period["From"]:
            continue
        if ident in result or ident in event_ids or calendar_id in event_calendars:
            raise ValueError("Conflicting permanent Kama-ZONE season or calendar")
        dates = {field: period[field][kamazone.REGION] for field in kamazone.FIELDS}
        # The permanent mode has no post-event reward window. Its placeholder
        # RewardUntil can legitimately be years earlier than its active dates.
        if kamazone.timestamp(dates["From"]) >= kamazone.timestamp(dates["To"]):
            raise ValueError("Invalid permanent Kama-ZONE calendar")
        result[ident] = dict(
            season_id=ident,
            name=old_season_label(season),
            name_key="ancientmall",
            calendar_id=calendar_id,
            original_period=dates,
        )
        event_calendars.add(calendar_id)
    return result


def event_mode(tables, season_id):
    archive = json.loads(tables["kamazonland"][1])
    event = json.loads(tables["kamazonland2"][1])
    original = kamazone.one(archive["Seasons"], "Id", season_id)
    dates = json.loads(tables["seasondate"][1])["EventPeriod"]
    if kamazone.REGION not in kamazone.one(dates, "Id", original["SeasonDateId"])["From"]:
        raise ValueError("Permanent Kama-ZONE rotation is unavailable on Global")
    shell = next(
        (
            s
            for s in event["Seasons"]
            if kamazone.REGION in kamazone.one(dates, "Id", s["SeasonDateId"])["From"]
        ),
        None,
    )
    if shell is None or any(s["Id"] == season_id for s in event["Seasons"]):
        raise ValueError("Permanent Kama-ZONE requires a distinct Global event lobby")
    # The Events lobby needs its NPC, ticket pool and currency even for practice.
    # Old GachaId refers to a different bottle-cap shop, not this ticket pool.
    # Use a separate banner URL so the client cannot cache a modern season's art.
    languages = shell["Banner"]
    if isinstance(languages, str):
        languages = json.loads(languages)
    season = {**shell, **{key: value for key, value in original.items() if key != "GachaId"}}
    season.update(
        SeasonName="ancientmall",
        Banner=json.dumps(
            {
                lang: f"media/kamazon_land/v0.{season_id}_kamazon_land_event_banner_{lang}.png"
                for lang in languages
            },
            separators=(",", ":"),
        ),
        ArtifactsException=original.get("ArtifactsException") or [],
    )
    event["Seasons"].append(season)
    # The lobby looks up the active NPC's likeability thresholds by season ID.
    # Link its display rows to the practice season as well. Practice grants no
    # likeability points, claims, or account inventory.
    if "PointRewards" in event:
        event["PointRewards"] += [
            dict(row, SeasonId=season_id)
            for row in event["PointRewards"]
            if row["SeasonId"] == shell["Id"]
        ]

    # The client calculates MiniSeasonId as group * 100 + round. Use the first
    # original round and its element restrictions throughout the practice window.
    group = season["MiniSeasonGroupId"]
    first = kamazone.one(archive["MiniSeasonsNew"], "Id", group * 100 + 1)
    if first["MiniSeasonGroupId"] != group:
        raise ValueError("Mismatched permanent Kama-ZONE mini-season group")
    event["MiniSeasons"] = [r for r in event["MiniSeasons"] if r["MiniSeasonGroupId"] != group] + [
        first
    ]

    for key in (
        "FloorPresets",
        "BattlePresets",
        "Monsters",
        "Trials",
        "Artifacts",
        "Benefits",
        "SpecialEvents",
        "SpecialEventChoices",
        "RandomConclusions",
    ):
        old_rows = archive[key]
        if key == "Benefits":
            old_rows = [
                dict(r, OpenValues=[r["OpenValue"]] if r["OpenValue"] else None) for r in old_rows
            ]
        # Keep modern-only definitions for references elsewhere in the Events
        # data while giving the original encounters their own effects and odds.
        rows = {r["Id"]: r for r in event[key]}
        rows.update((r["Id"], r) for r in old_rows)
        event[key] = list(rows.values())

    # Keep the original enemy levels for every archived difficulty. The modern
    # currencies do not represent old bottle caps and are unused in practice.
    event["Difficulty"] = [
        {
            **{
                k: r[k]
                for k in ("Id", "Floor", "Difficulty", "NormalLevel", "EliteLevel", "BossLevel")
            },
            "SeasonPoint": 0,
            "SeasonPointSpecial": 0,
            "TicketReward": 0,
        }
        for r in archive["Difficulty"]
    ]
    # Preserve the Events round length for its single practice mini-season.
    for key in (event["Constants"].keys() & archive["Constants"].keys()) - {"RoundPeriod"}:
        event["Constants"][key] = archive["Constants"][key]
    return event
