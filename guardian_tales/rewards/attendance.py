# SPDX-License-Identifier: Apache-2.0
"""Explicit attendance mock: acknowledge the local day without delivering rewards."""

import json
import time
from datetime import datetime, timezone

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.settlement.village import INT_MAX, MAX_REVISION, integer

from .stamina_regen import TIMESTAMP

ROUTE = "/user/claim-daily-attendance"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS attendance_mock_requests "
        "(operation_id TEXT PRIMARY KEY, day TEXT NOT NULL)"
    )


def response(profile):
    return {"User": profile["User"], "UserRecord": profile["UserRecord"], "AddedItems": []}


def load_catalog(references):
    path = references.directory / "attendance_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Imported attendance requires an explicit no-reward mock catalog")
    catalog = references.json(path.name)
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"client", "origin_group", "active_group", "days"}
        or catalog["client"] != CLIENT
        or any(
            not integer(catalog[k], (INT_MAX - 28) // 100, 1)
            for k in ("origin_group", "active_group")
        )
        or type(catalog["days"]) is not int
        or catalog["days"] != 28
    ):
        raise ValueError("Invalid attendance mock catalog")
    return catalog


def claim(account, body, operation_id, now=None):
    if (
        body not in (None, {})
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Attendance mock accepts no parameters after the prologue")
    profile = account.profile()
    if account.db.execute(
        "SELECT 1 FROM attendance_mock_requests WHERE operation_id=?", (operation_id,)
    ).fetchone():
        return response(profile)
    now = datetime.fromtimestamp(time.time(), timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Attendance clock must have a timezone")
    now = now.astimezone(timezone.utc)
    day = now.date().isoformat()
    user, record = profile["User"], profile["UserRecord"]
    stamp = user.get("LastAttendanceDate")
    if not isinstance(stamp, str) or not TIMESTAMP.fullmatch(stamp):
        raise ValueError("Invalid saved attendance date")
    try:
        last = datetime.fromisoformat(stamp).astimezone(timezone.utc).date()
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid saved attendance date") from exc
    if last > now.date():
        raise ValueError("Saved attendance date is in the future")
    saved_day = account.db.execute("SELECT 1 FROM attendance_claims WHERE day=?", (day,)).fetchone()
    eligible = last < now.date() and not saved_day
    if eligible:
        catalog = load_catalog(account.references)
        count = user.get("MonthlyLoginCount")
        if (
            not integer(count)
            or count % 100 > catalog["days"]
            or not integer(user.get("Cas"), MAX_REVISION - 1)
            or not integer(record.get("Cas"), MAX_REVISION - 1)
            or not integer(record.get("LoginDayCount"), INT_MAX - 1)
            or record.get("UserId") != user.get("Id")
        ):
            raise ValueError("Invalid saved attendance counters or owner")
        group = (
            (count // 100 if count >= 100 else catalog["origin_group"])
            if count
            else catalog["active_group"]
        )
        ordinal = count % 100 + 1
        if ordinal > catalog["days"]:
            group, ordinal = catalog["active_group"], 1
        # This opt-in mock deliberately never loads or parses any reward rows.
        # The claimed local day is skipped permanently, with no asset/item grant.
        user.update(
            MonthlyLoginCount=group * 100 + ordinal,
            LastAttendanceDate=now.isoformat(timespec="microseconds"),
        )
        user["Cas"] += 1
        record["LoginDayCount"] += 1
        record["Cas"] += 1
    with account.db:
        if eligible:
            account.db.execute(
                "INSERT INTO attendance_claims VALUES(?,?)", (day, user["MonthlyLoginCount"])
            )
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute("INSERT INTO attendance_mock_requests VALUES(?,?)", (operation_id, day))
    return response(profile)
