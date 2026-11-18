# SPDX-License-Identifier: Apache-2.0
"""Free relic option proposals using public per-source, per-slot option pools."""

import copy
import json
from secrets import randbelow

from .snapshots import CLIENT
from .village import MAX_REVISION, integer
from .weapon_enhance import decimal_id
from .weapon_options import encode

CHANGE = "/item/change-relic-options/v2"
APPLY = "/item/apply-relic-options"
MAX_LEVEL = 1000000


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS relic_option_proposals "
        "(item_id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, spec_id INTEGER NOT NULL, "
        "option_type INTEGER NOT NULL, before_options TEXT NOT NULL, after_options TEXT NOT NULL, "
        "option_pools TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS relic_option_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL, "
        "proposal_id TEXT NOT NULL, result_options TEXT NOT NULL)"
    )


def valid_pools(value):
    if not isinstance(value, dict) or set(value) != {"1", "2"}:
        return False
    for pools in value.values():
        if not isinstance(pools, list) or len(pools) > 16:
            return False
        for pool in pools:
            if (
                not isinstance(pool, dict)
                or not 1 <= len(pool) <= 256
                or any(
                    not decimal_id(k)
                    or not isinstance(bounds, list)
                    or len(bounds) != 2
                    or any(not integer(n, MAX_LEVEL) for n in bounds)
                    or bounds[0] > bounds[1]
                    for k, bounds in pool.items()
                )
            ):
                return False
    return any(value.values())


def load_catalog(references):
    path = references.directory / "relic_option_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Relic option changes require an explicit free relic catalog")
    value = references.json(path.name)
    if (
        not isinstance(value, dict)
        or set(value) != {"client", "free", "relics"}
        or value["client"] != CLIENT
        or value["free"] is not True
        or not isinstance(value["relics"], dict)
        or not 1 <= len(value["relics"]) <= 4096
        or any(not decimal_id(k) or not valid_pools(p) for k, p in value["relics"].items())
    ):
        raise ValueError("Invalid free relic option catalog")
    return value


def valid_rows(rows):
    # Repeated option IDs are legitimate in different relic slots.
    return (
        isinstance(rows, list)
        and 1 <= len(rows) <= 32
        and all(
            isinstance(r, dict)
            and set(r) == {"OptionId", "Level", "Locked", "OptionSource"}
            and integer(r["OptionId"], minimum=1)
            and integer(r["Level"], MAX_LEVEL)
            and type(r["Locked"]) is bool
            and integer(r["OptionSource"], 2, 1)
            for r in rows
        )
    )


def rows_match_pools(rows, pools):
    if not valid_rows(rows) or not valid_pools(pools):
        return False
    counts = {"1": 0, "2": 0}
    for row in rows:
        source = str(row["OptionSource"])
        index = counts[source]
        if index >= len(pools[source]):
            return False
        bounds = pools[source][index].get(str(row["OptionId"]))
        if not bounds or not bounds[0] <= row["Level"] <= bounds[1]:
            return False
        counts[source] += 1
    return all(counts[s] == len(pools[s]) for s in counts)


def target_item(user, item_id):
    items = user.get("ItemMiscs")
    if not isinstance(items, list):
        raise ValueError("Invalid saved relic inventory")
    matches = [r for r in items if isinstance(r, dict) and r.get("Id") == item_id]
    if len(matches) != 1:
        raise ValueError("Relic changes require one owned miscellaneous inventory item")
    target = matches[0]
    if (
        not integer(target.get("Id"), minimum=1)
        or not integer(target.get("ItemId"), minimum=1)
        or not integer(target.get("Amount"), 1, 1)
        or type(target.get("Locked")) is not bool
        or not valid_rows(target.get("RelicOptions"))
        or not integer(user.get("Cas"), MAX_REVISION)
    ):
        raise ValueError("Unsupported saved relic, option rows or user revision")
    return target


def proposal_options(pending, target):
    request_id, spec_id, option_type, before, after, pools = pending
    before, after, pools = json.loads(before), json.loads(after), json.loads(pools)
    if (
        not isinstance(request_id, str)
        or not 1 <= len(request_id) <= 200
        or not integer(spec_id, minimum=1)
        or spec_id != target["ItemId"]
        or not integer(option_type, 2, 1)
        or not rows_match_pools(before, pools)
        or not rows_match_pools(after, pools)
        or before != target["RelicOptions"]
    ):
        raise ValueError("Pending relic proposal no longer matches the saved relic")
    for old, new in zip(before, after):
        expected = dict(old)
        if old["OptionSource"] == option_type and not old["Locked"]:
            expected.update(OptionId=new["OptionId"], Level=new["Level"])
        if new != expected:
            raise ValueError("Relic proposal changes an unselected group, locked row or metadata")
    return after


def change_or_apply(account, body, operation_id, route):
    keys = {"ItemId", "OptionType"} if route == CHANGE else {"ItemId", "Apply"}
    if (
        route not in (CHANGE, APPLY)
        or not isinstance(body, dict)
        or set(body) != keys
        or not integer(body["ItemId"], minimum=1)
        or route == CHANGE
        and not integer(body["OptionType"], 2, 1)
        or route == APPLY
        and type(body["Apply"]) is not bool
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid relic option request or identity")
    encoded = encode(body)
    profile = account.profile()
    user = profile["User"]
    receipt = account.db.execute(
        "SELECT route,request FROM relic_option_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if receipt and receipt != (route, encoded):
        raise ValueError("Relic option retry differs from the saved request")
    if receipt and route == APPLY:
        return {"User": user}
    target = target_item(user, body["ItemId"])
    pending = account.db.execute(
        "SELECT request_id,spec_id,option_type,before_options,after_options,option_pools "
        "FROM relic_option_proposals WHERE item_id=?",
        (body["ItemId"],),
    ).fetchone()
    if receipt:
        options = proposal_options(pending, target) if pending else target["RelicOptions"]
    elif route == CHANGE:
        pools = load_catalog(account.references)["relics"].get(str(target["ItemId"]))
        if not pools or not rows_match_pools(target["RelicOptions"], pools):
            raise ValueError("Saved relic options do not match the public slot pools")
        if not any(
            r["OptionSource"] == body["OptionType"] and not r["Locked"]
            for r in target["RelicOptions"]
        ):
            raise ValueError("Selected relic group requires an unlocked existing slot")
        options = copy.deepcopy(target["RelicOptions"])
        counts = {"1": 0, "2": 0}
        for option in options:
            source = str(option["OptionSource"])
            pool = pools[source][counts[source]]
            counts[source] += 1
            if option["OptionSource"] == body["OptionType"] and not option["Locked"]:
                ids = sorted(pool, key=int)
                key = ids[randbelow(len(ids))]
                low, high = pool[key]
                option.update(OptionId=int(key), Level=low + randbelow(high - low + 1))
        with account.db:
            account.db.execute(
                "INSERT OR REPLACE INTO relic_option_proposals VALUES(?,?,?,?,?,?,?)",
                (
                    body["ItemId"],
                    operation_id,
                    target["ItemId"],
                    body["OptionType"],
                    encode(target["RelicOptions"]),
                    encode(options),
                    encode(pools),
                ),
            )
            account.db.execute(
                "INSERT INTO relic_option_requests VALUES(?,?,?,?,?)",
                (operation_id, route, encoded, operation_id, encode(options)),
            )
    else:
        if not pending:
            raise ValueError("No pending relic proposal for this item")
        options = proposal_options(pending, target)
        if body["Apply"]:
            if not integer(user["Cas"], MAX_REVISION - 1):
                raise ValueError("User revision exceeds the supported range")
            target["RelicOptions"] = options
            user["Cas"] += 1
        with account.db:
            if body["Apply"]:
                account.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1", (encode(profile),)
                )
            account.db.execute(
                "DELETE FROM relic_option_proposals WHERE item_id=?", (body["ItemId"],)
            )
            account.db.execute(
                "INSERT INTO relic_option_requests VALUES(?,?,?,?,?)",
                (operation_id, route, encoded, pending[0], encode(target["RelicOptions"])),
            )
    # Every asset, ticket and material is retained throughout this explicit free policy.
    response = {"User": user}
    if route == CHANGE:
        response["NewRelicOptions"] = [
            {k: r[k] for k in ("OptionId", "Level", "OptionSource")} for r in options
        ]
    return response
