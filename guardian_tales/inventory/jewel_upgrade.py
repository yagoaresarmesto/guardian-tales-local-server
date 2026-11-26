# SPDX-License-Identifier: Apache-2.0
"""Guaranteed, free one-grade jewel upgrades for owned stacks and relic sockets."""

import json

from guardian_tales.accounts.snapshots import CLIENT
from guardian_tales.rewards.challenges import allocate_reward_item
from guardian_tales.settlement.village import INT_MAX, MAX_REVISION, integer

from .weapon_enhance import decimal_id

LOOSE = "/item/upgrade-jewel"
RELIC = "/item/upgrade-jewel-from-relic"
ROUTES = (LOOSE, RELIC)


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS jewel_upgrade_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL, "
        "before_spec INTEGER NOT NULL, after_spec INTEGER NOT NULL)"
    )


def load_catalog(references):
    path = references.directory / "jewel_upgrade_mock_catalog.json"
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Jewel upgrades require an explicit guaranteed free-upgrade catalog")
    catalog = references.json(path.name)
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"client", "free", "always_succeed", "slot_count", "relic_ids", "jewels"}
        or catalog["client"] != CLIENT
        or catalog["free"] is not True
        or catalog["always_succeed"] is not True
        or not integer(catalog["slot_count"], 16, 1)
        or not isinstance(catalog["relic_ids"], list)
        or not 1 <= len(catalog["relic_ids"]) <= 4096
        or any(not integer(v, minimum=1) for v in catalog["relic_ids"])
        or len(set(catalog["relic_ids"])) != len(catalog["relic_ids"])
        or not isinstance(catalog["jewels"], dict)
        or not 1 <= len(catalog["jewels"]) <= 30000
    ):
        raise ValueError("Invalid guaranteed free jewel-upgrade policy")
    jewels = catalog["jewels"]
    for key, row in jewels.items():
        if (
            not decimal_id(key)
            or not isinstance(row, dict)
            or set(row) != {"grade", "group_id", "evolve_to", "powder_full"}
            or not integer(row["grade"], 100, 1)
            or not integer(row["group_id"], minimum=1)
            or not integer(row["evolve_to"])
            or not integer(row["powder_full"])
            or (row["evolve_to"] == 0) != (row["powder_full"] == 0)
            or int(key) in catalog["relic_ids"]
        ):
            raise ValueError("Invalid jewel upgrade grade or next spec")
    for row in jewels.values():
        if row["evolve_to"]:
            target = jewels.get(str(row["evolve_to"]))
            if (
                target is None
                or target["grade"] != row["grade"] + 1
                or target["group_id"] != row["group_id"]
            ):
                raise ValueError("Jewel upgrades require a closed, consecutive same-group graph")
    return catalog


def owned_inventory(user):
    kinds = ("ItemWeapons", "ItemMiscs", "ItemStackables")
    if any(
        not isinstance(user.get(k), list) or any(not isinstance(r, dict) for r in user[k])
        for k in kinds
    ):
        raise ValueError("Invalid saved jewel or relic inventory")
    return [r for k in kinds for r in user[k]]


def target_row(user, inventory, item_id, kind):
    matches = [r for r in inventory if r.get("Id") == item_id]
    if (
        len(matches) != 1
        or not any(matches[0] is r for r in user[kind])
        or not integer(matches[0].get("Id"), minimum=1)
        or not integer(matches[0].get("ItemId"), minimum=1)
        or not integer(matches[0].get("Amount"), minimum=1)
        or type(matches[0].get("Locked")) is not bool
    ):
        raise ValueError("Jewel upgrades require one unambiguous owned target")
    return matches[0]


def return_one_jewel(user, inventory, spec_id, *, locked=False):
    destinations = [r for r in user["ItemStackables"] if r.get("ItemId") == spec_id]
    if len(destinations) > 1:
        raise ValueError("Jewel destination stack is ambiguous")
    if not destinations:
        destination = allocate_reward_item(user, spec_id)
        destination["Locked"] = locked
        user["ItemStackables"].append(destination)
        return
    destination = destinations[0]
    if (
        not integer(destination.get("Id"), minimum=1)
        or not integer(destination.get("ItemId"), minimum=1)
        or sum(r.get("Id") == destination["Id"] for r in inventory) != 1
        or type(destination.get("Locked")) is not bool
        or not integer(destination.get("Amount"), INT_MAX - 1)
    ):
        raise ValueError("Invalid jewel destination or stack overflow")
    destination["Amount"] += 1


def upgrade(account, body, operation_id, route):
    fields = (
        {"RelicId", "SlotIndex", "UseJewelPowder"}
        if route == RELIC
        else {"JewelId", "UseJewelPowder"}
    )
    if (
        route not in ROUTES
        or not isinstance(body, dict)
        or set(body) != fields
        or not integer(body["UseJewelPowder"], minimum=1)
        or not integer(body["RelicId"] if route == RELIC else body["JewelId"], minimum=1)
        or (route == RELIC and not integer(body["SlotIndex"], 15))
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid jewel upgrade request, route or identity")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    profile = account.profile()
    previous = account.db.execute(
        "SELECT route,request FROM jewel_upgrade_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous != (route, encoded):
            raise ValueError("Jewel upgrade identity already belongs to another operation")
        return {"User": profile["User"], "Succeeded": True}
    catalog = load_catalog(account.references)
    user = profile["User"]
    inventory = owned_inventory(user)
    if not integer(user.get("Cas"), MAX_REVISION - 1):
        raise ValueError("Invalid jewel upgrade revision or overflow")
    if route == RELIC:
        target = target_row(user, inventory, body["RelicId"], "ItemMiscs")
        slots = target.get("JewelSlots")
        if (
            target["ItemId"] not in catalog["relic_ids"]
            or target["Amount"] != 1
            or not isinstance(slots, list)
            or not 1 <= len(slots) <= catalog["slot_count"]
            or any(not integer(v) for v in slots)
            or not 0 <= body["SlotIndex"] < len(slots)
        ):
            raise ValueError("Jewel upgrade requires an owned configured relic and valid socket")
        before = slots[body["SlotIndex"]]
    else:
        target = target_row(user, inventory, body["JewelId"], "ItemStackables")
        before = target["ItemId"]
    row = catalog["jewels"].get(str(before))
    if row is None or not row["evolve_to"]:
        raise ValueError("Jewel is unknown, socket is empty or the grade is already maximal")
    if body["UseJewelPowder"] > row["powder_full"]:
        raise ValueError("Selected jewel powder exceeds the native full-success quantity")
    after = row["evolve_to"]
    if route == RELIC:
        slots[body["SlotIndex"]] = after
    else:
        return_one_jewel(user, inventory, after, locked=target["Locked"])
        # One owned jewel changes grade; no extra source jewels are sacrificed.
        # Keep a zero source row so the native resource can clear its old count.
        target["Amount"] -= 1
    user["Cas"] += 1
    with account.db:
        account.db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        account.db.execute(
            "INSERT INTO jewel_upgrade_requests VALUES(?,?,?,?,?)",
            (operation_id, route, encoded, before, after),
        )
    return {"User": user, "Succeeded": True}
