# SPDX-License-Identifier: Apache-2.0
"""Acknowledge an available princess gift without any reward or reward notice."""

import json
import time
from datetime import datetime, timedelta, timezone

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.rewards.stamina_regen import TIMESTAMP

from .village import MAX_REVISION, current_village, integer

ROUTE = "/lobby-village/receive-gift"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS village_gift_mock_requests "
        "(operation_id TEXT PRIMARY KEY, next_gift_time TEXT)"
    )


def load_catalog(references):
    path = references.directory / "village_gift_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Village gifts require an explicit no-reward mock catalog")
    catalog = references.json(path.name)
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"client", "cooldown_seconds"}
        or catalog["client"] != CLIENT
        or not integer(catalog["cooldown_seconds"], 31536000, 1)
    ):
        raise ValueError("Invalid village gift mock catalog")
    return catalog


def receive(account, body, operation_id, now=None):
    if (
        body not in (None, {})
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Village gift mock accepts no parameters after the prologue")
    village = current_village(account.db)
    if account.db.execute(
        "SELECT 1 FROM village_gift_mock_requests WHERE operation_id=?", (operation_id,)
    ).fetchone():
        return {"UserLobbyVillage": village}
    catalog = load_catalog(account.references)
    if (
        not integer(village.get("UserId"), MAX_REVISION, 1)
        or village["UserId"] != account.profile()["User"].get("Id")
        or "NextGiftTime" not in village
    ):
        raise ValueError("Invalid village gift owner or saved timer")
    now = datetime.fromtimestamp(time.time(), timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Village gift clock must have a timezone")
    now = now.astimezone(timezone.utc)
    stamp = village["NextGiftTime"]
    due = None
    if stamp is not None:
        if not isinstance(stamp, str) or not TIMESTAMP.fullmatch(stamp):
            raise ValueError("Invalid saved village gift timer")
        try:
            due = datetime.fromisoformat(stamp).astimezone(timezone.utc)
            # Preserve a seventh .NET fraction digit in the eligibility check.
            fraction = TIMESTAMP.fullmatch(stamp).group(1) or ""
            due += timedelta(microseconds=len(fraction) == 7 and fraction[-1] != "0")
        except (ValueError, OverflowError) as exc:
            raise ValueError("Invalid saved village gift timer") from exc
    changed = due is not None and now >= due
    if changed:
        if not integer(village.get("Cas"), MAX_REVISION - 1):
            raise ValueError("Invalid village gift revision")
        try:
            next_time = now + timedelta(seconds=catalog["cooldown_seconds"])
        except OverflowError as exc:
            raise ValueError("Village gift timer overflow") from exc
        village["NextGiftTime"] = next_time.isoformat(timespec="microseconds")
        village["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "INSERT INTO village_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(village, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO village_gift_mock_requests VALUES(?,?)",
            (operation_id, village["NextGiftTime"]),
        )
    # The native success callback skips its reward notice when AddedItems is
    # absent. Do not manufacture a placeholder item or mutate the user profile.
    return {"UserLobbyVillage": village}
