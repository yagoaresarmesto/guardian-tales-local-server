# SPDX-License-Identifier: Apache-2.0
"""Free ordinary option locking, with atomic receipts and stale-proposal removal."""

import json

from .village import MAX_REVISION, integer
from .weapon_options import encode, load_catalog, target_item

ROUTE = "/item/change-lock-options"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS weapon_option_lock_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL, result_options TEXT NOT NULL)"
    )


def change_locks(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"ItemId", "OptionIds", "DoLock"}
        or not integer(body["ItemId"], minimum=1)
        or type(body["DoLock"]) is not bool
        or not isinstance(body["OptionIds"], list)
        or not 1 <= len(body["OptionIds"]) <= 32
        or any(not integer(i, minimum=1) for i in body["OptionIds"])
        or len(set(body["OptionIds"])) != len(body["OptionIds"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid option-lock request or identity")
    encoded = encode(dict(body, OptionIds=sorted(body["OptionIds"])))
    profile = account.profile()
    user = profile["User"]
    previous = account.db.execute(
        "SELECT request FROM weapon_option_lock_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Option-lock retry differs from the saved request")
        return {"User": user}
    target = target_item(user, body["ItemId"], account.references)
    catalog = load_catalog(account.references)
    ranges = catalog["weapons"].get(str(target["ItemId"]))
    if not ranges or any(
        str(r["OptionId"]) not in ranges
        or not ranges[str(r["OptionId"])][0] <= r["Level"] <= ranges[str(r["OptionId"])][1]
        for r in target["Options"]
    ):
        raise ValueError("Saved options do not match configured public weapon ranges")
    selected = set(body["OptionIds"])
    if not selected <= {r["OptionId"] for r in target["Options"]}:
        raise ValueError("Option locks must identify existing ordinary options on the owned item")
    changed = any(
        r["Locked"] != body["DoLock"] for r in target["Options"] if r["OptionId"] in selected
    )
    if changed:
        if not integer(user["Cas"], MAX_REVISION - 1):
            raise ValueError("User revision exceeds the supported range")
        for option in target["Options"]:
            if option["OptionId"] in selected:
                option["Locked"] = body["DoLock"]
        user["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute("UPDATE local_account SET profile=? WHERE id=1", (encode(profile),))
            # A previously rolled proposal must not undo a newly chosen lock.
            account.db.execute(
                "DELETE FROM weapon_option_proposals WHERE item_id=?", (body["ItemId"],)
            )
        account.db.execute(
            "INSERT INTO weapon_option_lock_requests VALUES(?,?,?)",
            (operation_id, encoded, json.dumps(target["Options"], separators=(",", ":"))),
        )
    # Explicit shared free policy: no locking stones, other materials or gold are spent.
    return {"User": user}
