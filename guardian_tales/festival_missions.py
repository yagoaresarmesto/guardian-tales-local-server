# SPDX-License-Identifier: Apache-2.0
"""Claim completed Festival Pass mission tiers from the saved season."""

import json
from functools import lru_cache

from .raid_static import decode, records
from .village import INT_MAX, MAX_REVISION, integer

ROUTE = "/festival-pass/claim-missions"


@lru_cache(maxsize=1)
def mission_rules(body, season_id):
    tables = records(decode(body))[1]
    try:
        catalog = json.loads(tables["festivalpass"][1])
        sets = [row["MissionSet"] for row in catalog["Seasons"] if row["Id"] == season_id]
        if len(sets) != 1 or not integer(sets[0], minimum=1):
            raise ValueError("Missing Festival Pass season")
        rules = {}
        for row in catalog["Missions"]:
            if row["SetId"] != sets[0]:
                continue
            ident, group, target, xp = (
                row[k] for k in ("Id", "GroupId", "Value", "PassExperience")
            )
            if ident in rules or not all(integer(n, minimum=1) for n in (ident, group, target, xp)):
                raise ValueError("Invalid Festival mission tier")
            rules[ident] = (str(group), target, xp)
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid Festival mission catalog") from exc
    return rules


def claim(account, request):
    if not isinstance(request, dict) or set(request) != {"missionIds"} or account.needs_prologue():
        raise ValueError("Festival mission claims require missionIds after the prologue")
    ids = request["missionIds"]
    if not isinstance(ids, list) or len(ids) > 512 or not all(integer(i, minimum=1) for i in ids):
        raise ValueError("Invalid Festival mission IDs")

    body = account.references.read_bytes("static_data_get.bin")
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        festival = profile["UserFestivalPass"]
        if (
            not integer(festival.get("SeasonId"), minimum=1)
            or not integer(festival.get("Experience"))
            or not integer(festival.get("Cas"), MAX_REVISION)
            or not isinstance(festival.get("Missions"), dict)
        ):
            raise ValueError("Invalid saved Festival Pass progress")
        rules = mission_rules(body, festival["SeasonId"])
        earned = 0
        for ident in dict.fromkeys(ids):
            if ident not in rules:
                raise ValueError("Unknown mission for the saved Festival season")
            group, target, xp = rules[ident]
            progress = festival["Missions"].get(group)
            if not isinstance(progress, dict) or not integer(progress.get("Value")):
                raise ValueError("Missing saved Festival mission progress")
            rewarded = progress.get("RewardedIds")
            if rewarded is not None and not isinstance(rewarded, list):
                raise ValueError("Invalid Festival mission claim history")
            if progress.get("Rewarded") is True or (rewarded is not None and ident in rewarded):
                continue
            if progress["Value"] < target:
                raise ValueError("Festival mission target has not been reached")
            if rewarded is None:
                progress["RewardedIds"] = [ident]
            else:
                rewarded.append(ident)
            earned += xp
        if earned:
            if festival["Experience"] + earned > INT_MAX or festival["Cas"] == MAX_REVISION:
                raise ValueError("Festival Pass experience or revision overflow")
            festival["Experience"] += earned
            festival["Cas"] += 1
            db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"UserFestivalPass": festival}
