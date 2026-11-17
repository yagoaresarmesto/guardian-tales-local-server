# SPDX-License-Identifier: Apache-2.0
"""Natural stamina ticks from the saved timer; no gem purchases or reserve transfers."""

import json
import re
from datetime import datetime, timedelta, timezone

from .campaign import CHARGED_STAMINA
from .snapshots import CLIENT

MAX_REVISION = 0x7FFFFFFFFFFFFFFF
TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.([0-9]{1,7}))?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)


def load_catalog(references):
    path = references.directory / "stamina_regen_catalog.json"
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Natural stamina recharge requires a matching external catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "base_max", "interval_minutes"}
        or value["client"] != CLIENT
        or type(value["base_max"]) is not int
        or not 1 <= value["base_max"] <= 1000000
        or type(value["interval_minutes"]) is not int
        or not 1 <= value["interval_minutes"] <= 1440
    ):
        raise ValueError("Invalid natural stamina recharge catalog")
    return value


def recharge_user(user, catalog, now):
    """Update a detached profile value; the caller owns the atomic database write."""
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Natural stamina clock must have a timezone")
    now = now.astimezone(timezone.utc)
    assets = user.get("Assets")
    rows = (
        [row for row in assets if isinstance(row, dict) and row.get("Id") == CHARGED_STAMINA]
        if isinstance(assets, list)
        else []
    )
    if len(rows) != 1:
        raise ValueError("Natural stamina recharge needs one charged-stamina asset")
    stamina = rows[0]
    amount, adjustment = stamina.get("Amount"), stamina.get("MaxAdj")
    if (
        type(amount) is not int
        or not 0 <= amount <= 0x7FFFFFFF
        or type(adjustment) is not int
        or not -0x80000000 <= adjustment <= 0x7FFFFFFF
        or not 1 <= catalog["base_max"] + adjustment <= 0x7FFFFFFF
        or "NextCharge" not in stamina
    ):
        raise ValueError("Invalid saved natural stamina balance or maximum")
    maximum = catalog["base_max"] + adjustment
    timestamp = stamina["NextCharge"]
    anchor, extra_digit = None, 0
    if timestamp is not None:
        match = TIMESTAMP.fullmatch(timestamp) if isinstance(timestamp, str) else None
        if match is None:
            raise ValueError("Invalid natural stamina recharge time")
        fraction = match.group(1) or ""
        extra_digit = int(fraction[-1]) if len(fraction) == 7 else 0
        try:
            anchor = datetime.fromisoformat(timestamp).astimezone(timezone.utc)
        except (ValueError, OverflowError) as error:
            raise ValueError("Invalid natural stamina recharge time") from error
    if amount >= maximum or anchor is None:
        return False
    try:
        # .NET timestamps can have a seventh fractional digit. Python clocks
        # use microseconds: round only the due comparison upward, preserving
        # the original sub-microsecond digit when advancing the saved anchor.
        due = anchor + timedelta(microseconds=bool(extra_digit))
        if now < due:
            return False
        interval = timedelta(minutes=catalog["interval_minutes"])
        ticks = 1 + (now - due) // interval
        next_charge = (anchor + ticks * interval).isoformat(timespec="microseconds")
        if extra_digit:
            next_charge = next_charge[:-6] + str(extra_digit) + "+00:00"
    except (ValueError, OverflowError) as error:
        raise ValueError("Natural stamina recharge time exceeds the supported range") from error
    revision = user.get("Cas")
    if type(revision) is not int or not 0 <= revision < MAX_REVISION:
        raise ValueError("Invalid account revision for natural stamina recharge")
    stamina["Amount"] = min(maximum, amount + ticks)
    stamina["NextCharge"] = next_charge
    user["Cas"] += 1
    return True


def charge_stamina(account, body, now=None):
    if body not in (None, {}) or account.needs_prologue():
        raise ValueError("Natural stamina recharge accepts no parameters after the prologue")
    catalog = load_catalog(account.references)
    profile = account.profile()
    if recharge_user(
        profile["User"], catalog, now if now is not None else datetime.now(timezone.utc)
    ):
        with account.db:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"User": profile["User"]}
