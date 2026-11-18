# SPDX-License-Identifier: Apache-2.0
"""Opt-in jewel decomposition grants public powder yields while preserving source stacks."""

import json

from .snapshots import CLIENT
from .village import INT_MAX, MAX_REVISION, integer
from .weapon_enhance import decimal_id

ROUTE = "/item/decompose-jewel"
POWDER = 70028


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS jewel_decompose_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, powder INTEGER NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / "jewel_decompose_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Jewel decomposition requires an explicit source-preserving catalog")
    catalog = references.json(path.name)
    if (
        not isinstance(catalog, dict)
        or set(catalog)
        != {"client", "preserve_sources", "powder_asset_id", "grade_yields", "jewels"}
        or catalog["client"] != CLIENT
        or catalog["preserve_sources"] is not True
        or type(catalog["powder_asset_id"]) is not int
        or catalog["powder_asset_id"] != POWDER
        or not isinstance(catalog["grade_yields"], dict)
        or not 1 <= len(catalog["grade_yields"]) <= 100
        or any(
            not decimal_id(key) or not integer(amount, minimum=1)
            for key, amount in catalog["grade_yields"].items()
        )
        or not isinstance(catalog["jewels"], dict)
        or not 1 <= len(catalog["jewels"]) <= 30000
        or any(
            not decimal_id(key)
            or not integer(grade, 100, 1)
            or str(grade) not in catalog["grade_yields"]
            or int(key) == POWDER
            for key, grade in catalog["jewels"].items()
        )
    ):
        raise ValueError("Invalid source-preserving jewel catalog")
    return catalog


def decompose(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"Jewels"}
        or not isinstance(body["Jewels"], dict)
        or not 1 <= len(body["Jewels"]) <= 256
        or any(not decimal_id(k) or not integer(v, minimum=1) for k, v in body["Jewels"].items())
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid jewel decomposition batch or request identity")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    previous = account.db.execute(
        "SELECT request FROM jewel_decompose_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Jewel decomposition retry differs from its saved request")
        return {"User": profile["User"]}

    catalog = load_catalog(account.references)
    user = profile["User"]
    kinds = ("ItemWeapons", "ItemMiscs", "ItemStackables")
    if any(
        not isinstance(user.get(kind), list) or any(not isinstance(r, dict) for r in user[kind])
        for kind in kinds
    ):
        raise ValueError("Invalid saved jewel inventory")
    inventory = [r for kind in kinds for r in user[kind]]
    gained, count = 0, 0
    for key, amount in body["Jewels"].items():
        matches = [r for r in inventory if r.get("Id") == int(key)]
        if len(matches) != 1 or not any(matches[0] is r for r in user["ItemStackables"]):
            raise ValueError("Decomposition requires unambiguous owned jewel stack IDs")
        source = matches[0]
        grade = catalog["jewels"].get(str(source.get("ItemId")))
        if (
            not integer(source.get("Id"), minimum=1)
            or not integer(source.get("ItemId"), minimum=1)
            or grade is None
            or not integer(source.get("Amount"), minimum=amount)
            or source.get("Locked") is not False
        ):
            raise ValueError("Unknown, locked or insufficient owned jewel stack")
        gained += catalog["grade_yields"][str(grade)] * amount
        count += amount
    if not integer(gained, minimum=1) or not integer(count, minimum=1):
        raise ValueError("Jewel decomposition total exceeds native Int32 bounds")
    assets = user.get("Assets")
    if not isinstance(assets, list) or any(not isinstance(a, dict) for a in assets):
        raise ValueError("Invalid saved jewel powder assets")
    powders = [a for a in assets if a.get("Id") == POWDER]
    if (
        len(powders) != 1
        or not integer(powders[0].get("Amount"), INT_MAX - gained)
        or not integer(user.get("Cas"), MAX_REVISION - 1)
    ):
        raise ValueError("Invalid powder balance, overflow or account revision")
    powders[0]["Amount"] += gained
    user["Cas"] += 1
    # This explicit mock changes only powder and the User revision. Selected
    # stacks, equipment sockets, spending and activity counters remain intact.
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO jewel_decompose_requests VALUES(?,?,?)", (operation_id, encoded, gained)
        )
    # The native forge builds its result notice from the selected quantities and
    # grade drops. It consumes the current User resource, not AddedItems.
    return {"User": user}
