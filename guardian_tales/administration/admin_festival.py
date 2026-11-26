# SPDX-License-Identifier: Apache-2.0
"""Season-bound, audited Festival point grants for an existing stopped account."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from guardian_tales.runtime.state_lock import StateLock

from .admin import validate_grant_parameters

MAX_POINTS = 0x7FFFFFFF
AUDIT_COLUMNS = "operation_id,season_id,amount,balance_before,balance_after,reason,created_at"


def grant_festival_points(data_dir, amount, season_id, operation_id, reason):
    reason = validate_grant_parameters(amount, operation_id, reason, MAX_POINTS)
    if type(season_id) is not int or not 1 <= season_id <= 0x7FFFFFFF:
        raise ValueError("Provide a positive existing Festival season ID")
    database = Path(data_dir).resolve() / "server.sqlite3"
    if not database.is_file():
        raise ValueError("No existing server.sqlite3 in the selected data directory")
    with StateLock(database.parent):
        db = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            saved = db.execute(
                "SELECT schema_version,profile FROM local_account WHERE id=1"
            ).fetchone()
            if saved is None or saved[0] != 3:
                raise ValueError(
                    "An existing schema-3 local account is required; no migration was performed"
                )
            if not db.execute("SELECT 1 FROM prologue_selection WHERE id=1").fetchone():
                raise ValueError("Complete the prologue before granting Festival points")
            profile = json.loads(saved[1])
            festival = profile["UserFestivalPass"]
            if type(festival["SeasonId"]) is not int or festival["SeasonId"] != season_id:
                raise ValueError(
                    "The requested Festival season does not match the saved active season"
                )
            if (
                type(festival["Point"]) is not int
                or not 0 <= festival["Point"] <= MAX_POINTS
                or type(festival["Cas"]) is not int
                or not 0 <= festival["Cas"] < MAX_POINTS
            ):
                raise ValueError("Invalid saved Festival point balance or revision")
            db.execute(
                "CREATE TABLE IF NOT EXISTS admin_festival_point_grants ("
                "operation_id TEXT PRIMARY KEY, season_id INTEGER NOT NULL, amount INTEGER NOT NULL, "
                "balance_before INTEGER NOT NULL, balance_after INTEGER NOT NULL, "
                "reason TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            previous = db.execute(
                f"SELECT {AUDIT_COLUMNS} FROM admin_festival_point_grants WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if previous is not None:
                if previous[1] != season_id or previous[2] != amount or previous[5] != reason:
                    raise ValueError(
                        "Operation ID was already used with a different season, amount or reason"
                    )
                receipt = dict(zip(AUDIT_COLUMNS.split(","), previous))
                result = "already_applied"
            else:
                before = festival["Point"]
                after = before + amount
                if after > MAX_POINTS:
                    raise ValueError(f"Resulting Festival point balance would exceed {MAX_POINTS}")
                receipt = dict(
                    operation_id=operation_id,
                    season_id=season_id,
                    amount=amount,
                    balance_before=before,
                    balance_after=after,
                    reason=reason,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                festival["Point"] = after
                festival["Cas"] += 1
                db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
                db.execute(
                    "INSERT INTO admin_festival_point_grants VALUES(?,?,?,?,?,?,?)",
                    tuple(receipt.values()),
                )
                result = "applied"
            db.execute("COMMIT")
            return {"result": result, **receipt, "current_balance": festival["Point"]}
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()


def festival_point_history(data_dir, limit=20):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("History limit must be between 1 and 1000")
    database = Path(data_dir).resolve() / "server.sqlite3"
    if not database.is_file():
        raise ValueError("No existing server.sqlite3 in the selected data directory")
    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_festival_point_grants'"
        ).fetchone():
            return []
        return [
            dict(zip(AUDIT_COLUMNS.split(","), row))
            for row in db.execute(
                f"SELECT {AUDIT_COLUMNS} FROM admin_festival_point_grants ORDER BY rowid DESC LIMIT ?",
                (limit,),
            )
        ]
    finally:
        db.close()
