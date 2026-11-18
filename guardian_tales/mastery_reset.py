# SPDX-License-Identifier: Apache-2.0
"""Atomic mastery redistribution with catalog costs and a persisted cooldown."""

import json
import time
from datetime import datetime, timedelta, timezone

from .campaign import FREE_GEMS
from .mastery import MASTERY_POINTS, load_catalog, saved_mastery
from .snapshots import CLIENT
from .stamina_regen import TIMESTAMP
from .village import INT_MAX, MAX_REVISION, MAX_TIME, current_village, integer

ROUTE = "/user/reset-guardian-mastery-level"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS mastery_reset_requests "
        "(operation_id TEXT PRIMARY KEY, refund INTEGER NOT NULL, "
        "gem_cost INTEGER NOT NULL, next_reset TEXT NOT NULL)"
    )


def load_reset_catalog(references):
    path = references.directory / "guardian_mastery_reset_catalog.json"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Mastery reset requires a matching external reset catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "resource_id", "cost", "cooldown_seconds"}
        or value["client"] != CLIENT
        or type(value["resource_id"]) is not int
        or value["resource_id"] != FREE_GEMS
        or not integer(value["cost"], minimum=1)
        or not integer(value["cooldown_seconds"], 31536000, 1)
    ):
        raise ValueError("Invalid guardian mastery reset catalog")
    return value


def reset(account, body, operation_id, now=None):
    if (
        body not in (None, {})
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Mastery reset accepts no parameters after the prologue")
    profile = account.profile()
    user = profile["User"]
    previous = account.db.execute(
        "SELECT 1 FROM mastery_reset_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        return {"User": user}
    catalog = load_catalog(account.references)
    policy = load_reset_catalog(account.references)
    levels, total = saved_mastery(user, current_village(account.db), catalog)
    if not total or all(levels.get(k, 0) == len(catalog["level_costs"]) for k in catalog["skills"]):
        raise ValueError("Empty or fully maximized mastery cannot be reset")
    now = int(time.time()) if now is None else now
    if not integer(now, MAX_TIME - policy["cooldown_seconds"], 1):
        raise ValueError("Invalid mastery reset clock")
    mastery = user["Options"]["GuardianMastery"]
    if "SkillNextResetTime" not in mastery:
        raise ValueError("Missing saved mastery reset time")
    next_reset = mastery["SkillNextResetTime"]
    if next_reset is not None:
        if not isinstance(next_reset, str) or not TIMESTAMP.fullmatch(next_reset):
            raise ValueError("Invalid saved mastery reset time")
        try:
            due = (
                datetime.fromisoformat(next_reset).astimezone(timezone.utc)
                - datetime(1970, 1, 1, tzinfo=timezone.utc)
            ) // timedelta(seconds=1)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError("Invalid saved mastery reset time") from exc
        # The APK compares DateTimeOffset.ToUnixTimeSeconds, including for a
        # seven-digit .NET fractional timestamp. Equality permits a new reset.
        if now < due:
            raise ValueError("Guardian mastery reset is still on cooldown")
    assets = user.get("Assets")
    rows = (
        {
            item: [a for a in assets if isinstance(a, dict) and a.get("Id") == item]
            for item in (MASTERY_POINTS, FREE_GEMS)
        }
        if isinstance(assets, list)
        else {}
    )
    if not rows or any(
        len(matches) != 1
        or not integer(matches[0].get("Amount"))
        or not integer(matches[0].get("Spent"), INT_MAX, -INT_MAX - 1)
        for matches in rows.values()
    ):
        raise ValueError("Invalid mastery reset currency balances")
    points, gems = rows[MASTERY_POINTS][0], rows[FREE_GEMS][0]
    # Refund the configured investment in the current skill map, never the
    # historical counter wholesale. Signed counter offsets survive the refund.
    refund = sum(sum(catalog["level_costs"][:level]) for level in levels.values())
    cost = policy["cost"]
    if (
        refund > INT_MAX - points["Amount"]
        or points["Spent"] - refund < -INT_MAX - 1
        or gems["Amount"] < cost
        or gems["Spent"] > INT_MAX - cost
        or not integer(user.get("Cas"), MAX_REVISION - 1)
    ):
        raise ValueError("Insufficient reset gems or mastery refund/counter/revision overflow")
    next_reset = datetime.fromtimestamp(now + policy["cooldown_seconds"], timezone.utc).isoformat()
    points["Amount"] += refund
    points["Spent"] -= refund
    gems["Amount"] -= cost
    gems["Spent"] += cost
    levels.clear()
    mastery["SkillNextResetTime"] = next_reset
    user["GuardianMasteryLevel"] = 0
    user["Cas"] += 1
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO mastery_reset_requests VALUES(?,?,?,?)",
            (operation_id, refund, cost, next_reset),
        )
    return {"User": user}
