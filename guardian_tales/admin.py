# SPDX-License-Identifier: Apache-2.0
"""Audited offline grants and history for the existing single local player."""

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .campaign import FREE_GEMS
from .state_lock import StateLock

MAX_GEMS = 0x7FFFFFFF
AUDIT_COLUMNS = "operation_id,amount,balance_before,balance_after,reason,created_at"


def validate_grant_parameters(amount, operation_id, reason, maximum):
    if type(amount) is not int or not 1 <= amount <= maximum:
        raise ValueError(f"Amount must be between 1 and {maximum}")
    if not isinstance(operation_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", operation_id
    ):
        raise ValueError(
            "Operation ID must contain 1..128 letters, digits, underscores, dots, colons or hyphens"
        )
    if (
        not isinstance(reason, str)
        or not 1 <= len(reason.strip()) <= 200
        or any(ord(c) < 32 or ord(c) == 127 for c in reason)
    ):
        raise ValueError(
            "Provide a nonempty reason up to 200 characters without control characters"
        )
    return reason.strip()


def grant_gems(data_dir, amount, operation_id, reason):
    reason = validate_grant_parameters(amount, operation_id, reason, MAX_GEMS)
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
                raise ValueError("Complete the prologue before granting gems")
            profile = json.loads(saved[1])
            user = profile["User"]
            matches = [a for a in user["Assets"] if a["Id"] == FREE_GEMS]
            if (
                len(matches) != 1
                or type(matches[0]["Amount"]) is not int
                or not 0 <= matches[0]["Amount"] <= MAX_GEMS
                or type(user["Cas"]) is not int
                or not 0 <= user["Cas"] < MAX_GEMS
            ):
                raise ValueError("Invalid saved free-gem balance or user revision")
            asset = matches[0]
            db.execute(
                "CREATE TABLE IF NOT EXISTS admin_gem_grants (operation_id TEXT PRIMARY KEY, "
                "amount INTEGER NOT NULL, balance_before INTEGER NOT NULL, balance_after INTEGER NOT NULL, "
                "reason TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            previous = db.execute(
                f"SELECT {AUDIT_COLUMNS} FROM admin_gem_grants WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if previous is not None:
                if previous[1] != amount or previous[4] != reason:
                    raise ValueError(
                        "Operation ID was already used with a different amount or reason"
                    )
                receipt = dict(zip(AUDIT_COLUMNS.split(","), previous))
                result = "already_applied"
            else:
                before = asset["Amount"]
                after = before + amount
                if after > MAX_GEMS:
                    raise ValueError(f"Resulting gem balance would exceed {MAX_GEMS}")
                receipt = dict(
                    operation_id=operation_id,
                    amount=amount,
                    balance_before=before,
                    balance_after=after,
                    reason=reason,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                asset["Amount"] = after
                user["Cas"] += 1
                db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(profile, separators=(",", ":")),),
                )
                db.execute(
                    "INSERT INTO admin_gem_grants VALUES(?,?,?,?,?,?)", tuple(receipt.values())
                )
                result = "applied"
            db.execute("COMMIT")
            return {"result": result, **receipt, "current_balance": asset["Amount"]}
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()


def gem_history(data_dir, limit=20):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("History limit must be between 1 and 1000")
    database = Path(data_dir).resolve() / "server.sqlite3"
    if not database.is_file():
        raise ValueError("No existing server.sqlite3 in the selected data directory")
    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_gem_grants'"
        ).fetchone():
            return []
        return [
            dict(zip(AUDIT_COLUMNS.split(","), row))
            for row in db.execute(
                f"SELECT {AUDIT_COLUMNS} FROM admin_gem_grants ORDER BY rowid DESC LIMIT ?",
                (limit,),
            )
        ]
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    grant = commands.add_parser(
        "grant-gems", help="Add free gems once to an existing stopped account"
    )
    grant.add_argument("amount", type=int)
    grant.add_argument("--data-dir", type=Path, required=True)
    grant.add_argument("--operation-id", required=True)
    grant.add_argument("--reason", required=True)
    history = commands.add_parser("gem-history", help="Read administrative gem grant receipts")
    history.add_argument("--data-dir", type=Path, required=True)
    history.add_argument("--limit", type=int, default=20)
    festival = commands.add_parser(
        "grant-festival-points", help="Add points once to an existing active Festival season"
    )
    festival.add_argument("amount", type=int)
    festival.add_argument("--season-id", type=int, required=True)
    festival.add_argument("--data-dir", type=Path, required=True)
    festival.add_argument("--operation-id", required=True)
    festival.add_argument("--reason", required=True)
    festival_history = commands.add_parser(
        "festival-point-history", help="Read administrative Festival point receipts"
    )
    festival_history.add_argument("--data-dir", type=Path, required=True)
    festival_history.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if args.action == "grant-gems":
            result = grant_gems(args.data_dir, args.amount, args.operation_id, args.reason)
        elif args.action == "gem-history":
            result = gem_history(args.data_dir, args.limit)
        else:
            from .admin_festival import festival_point_history, grant_festival_points

            if args.action == "grant-festival-points":
                result = grant_festival_points(
                    args.data_dir, args.amount, args.season_id, args.operation_id, args.reason
                )
            else:
                result = festival_point_history(args.data_dir, args.limit)
    except (ValueError, RuntimeError, OSError, sqlite3.Error, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
