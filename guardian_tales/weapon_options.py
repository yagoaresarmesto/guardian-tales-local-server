# SPDX-License-Identifier: Apache-2.0
"""Free local option-value proposals with persistent apply/discard and retries."""

import copy
import json
from secrets import randbelow

from .snapshots import CLIENT
from .village import MAX_REVISION, integer
from .weapon_enhance import decimal_id

CHANGE = "/item/change-options"
APPLY = "/item/apply-options"
MAX_LEVEL = 1000


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_option_proposals "
        "(item_id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, spec_id INTEGER NOT NULL, "
        "before_options TEXT NOT NULL, after_options TEXT NOT NULL, option_ranges TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_option_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL, "
        "proposal_id TEXT NOT NULL, result_options TEXT NOT NULL)"
    )


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def valid_options(rows):
    return (
        isinstance(rows, list)
        and 1 <= len(rows) <= 32
        and all(
            isinstance(r, dict)
            and set(r) == {"OptionId", "Level", "Locked", "OptionSource"}
            and integer(r["OptionId"], minimum=1)
            and integer(r["Level"], MAX_LEVEL)
            and type(r["Locked"]) is bool
            and integer(r["OptionSource"], 0)
            for r in rows
        )
        and len({r["OptionId"] for r in rows}) == len(rows)
    )


def valid_ranges(options):
    return (
        isinstance(options, dict)
        and 1 <= len(options) <= 32
        and all(
            decimal_id(key)
            and isinstance(bounds, list)
            and len(bounds) == 2
            and all(integer(n, MAX_LEVEL) for n in bounds)
            and bounds[0] <= bounds[1]
            for key, bounds in options.items()
        )
    )


def load_catalog(references):
    path = references.directory / "weapon_option_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Option changes require an explicit free option-value mock catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "free", "weapons"}
        or value["client"] != CLIENT
        or value["free"] is not True
        or not isinstance(value["weapons"], dict)
        or not 1 <= len(value["weapons"]) <= 30000
    ):
        raise ValueError("Invalid free equipment option catalog")
    for spec, options in value["weapons"].items():
        if not decimal_id(spec) or not valid_ranges(options):
            raise ValueError("Invalid public weapon option ranges")
    return value


def target_item(user, item_id):
    weapons = user.get("ItemWeapons")
    if not isinstance(weapons, list):
        raise ValueError("Invalid saved equipment inventory")
    rows = [r for r in weapons if isinstance(r, dict) and r.get("Id") == item_id]
    if len(rows) != 1:
        raise ValueError("Option changes require one owned equipment item")
    target = rows[0]
    if (
        not integer(target.get("Id"), minimum=1)
        or not integer(target.get("ItemId"), minimum=1)
        or not integer(target.get("Amount"), 1, 1)
        or type(target.get("Locked")) is not bool
        or target.get("EngraveOptions") not in (None, [])
        or not valid_options(target.get("Options"))
        or not integer(user.get("Cas"), MAX_REVISION)
    ):
        raise ValueError("Unsupported saved equipment, options, engraving or user revision")
    return target


def proposal_options(row, target):
    request_id, spec, before, after, ranges = row
    before, after = json.loads(before), json.loads(after)
    ranges = json.loads(ranges)
    if (
        not isinstance(request_id, str)
        or not 1 <= len(request_id) <= 200
        or not integer(spec, minimum=1)
        or spec != target["ItemId"]
        or not valid_options(before)
        or not valid_options(after)
        or before != target["Options"]
        or len(before) != len(after)
        or not valid_ranges(ranges)
    ):
        raise ValueError("Pending option proposal no longer matches the saved equipment")
    for old, new in zip(before, after):
        expected = dict(old, Level=new["Level"] if not old["Locked"] else old["Level"])
        bounds = ranges.get(str(new["OptionId"]))
        if new != expected or not bounds or not bounds[0] <= new["Level"] <= bounds[1]:
            raise ValueError(
                "Pending proposal changes option identities, locks, metadata or bounds"
            )
    return after


def change_or_apply(account, body, operation_id, route):
    keys = {"ItemId"} if route == CHANGE else {"ItemId", "Apply"}
    if (
        route not in (CHANGE, APPLY)
        or not isinstance(body, dict)
        or set(body) != keys
        or not integer(body["ItemId"], minimum=1)
        or route == APPLY
        and type(body["Apply"]) is not bool
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid equipment option request or identity")
    encoded = encode(body)
    profile = account.profile()
    user = profile["User"]
    receipt = account.db.execute(
        "SELECT route,request FROM weapon_option_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if receipt and receipt != (route, encoded):
        raise ValueError("Option retry differs from the saved request")
    if receipt and route == APPLY:
        return {"User": user}
    target = target_item(user, body["ItemId"])
    pending = account.db.execute(
        "SELECT request_id,spec_id,before_options,after_options,option_ranges "
        "FROM weapon_option_proposals WHERE item_id=?",
        (body["ItemId"],),
    ).fetchone()
    if receipt:
        # A delayed change retry displays the latest proposal or current options;
        # it never resurrects an older roll or overwrites a later user's choice.
        options = proposal_options(pending, target) if pending else target["Options"]
    elif route == CHANGE:
        catalog = load_catalog(account.references)
        ranges = catalog["weapons"].get(str(target["ItemId"]))
        if not ranges or not any(not r["Locked"] for r in target["Options"]):
            raise ValueError("Target requires configured options and at least one unlocked option")
        options = copy.deepcopy(target["Options"])
        for option in options:
            bounds = ranges.get(str(option["OptionId"]))
            if not bounds or not bounds[0] <= option["Level"] <= bounds[1]:
                raise ValueError("Saved option does not match the configured public range")
            if not option["Locked"]:
                option["Level"] = bounds[0] + randbelow(bounds[1] - bounds[0] + 1)
        with account.db:
            account.db.execute(
                "INSERT OR REPLACE INTO weapon_option_proposals VALUES(?,?,?,?,?,?)",
                (
                    body["ItemId"],
                    operation_id,
                    target["ItemId"],
                    encode(target["Options"]),
                    encode(options),
                    encode(ranges),
                ),
            )
            account.db.execute(
                "INSERT INTO weapon_option_requests VALUES(?,?,?,?,?)",
                (operation_id, route, encoded, operation_id, encode(options)),
            )
    else:
        if not pending:
            raise ValueError("No pending option proposal for this equipment")
        options = proposal_options(pending, target)
        if body["Apply"]:
            if not integer(user["Cas"], MAX_REVISION - 1):
                raise ValueError("User revision exceeds the supported range")
            target["Options"] = options
            user["Cas"] += 1
        with account.db:
            if body["Apply"]:
                account.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1", (encode(profile),)
                )
            account.db.execute(
                "DELETE FROM weapon_option_proposals WHERE item_id=?", (body["ItemId"],)
            )
            account.db.execute(
                "INSERT INTO weapon_option_requests VALUES(?,?,?,?,?)",
                (operation_id, route, encoded, pending[0], encode(target["Options"])),
            )
    # No option stones, lock stones, currency, buffs or mission credit are consumed.
    response = {"User": user}
    if route == CHANGE:
        response["NewOptions"] = [{"OptionId": r["OptionId"], "Level": r["Level"]} for r in options]
    return response
