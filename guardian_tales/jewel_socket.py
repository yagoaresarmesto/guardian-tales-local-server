# SPDX-License-Identifier: Apache-2.0
"""Open Epic relic sockets and attach, replace or recover their jewels."""

import json
from dataclasses import dataclass
from functools import lru_cache

from .jewel_upgrade import owned_inventory, return_one_jewel, target_row
from .raid_static import decode, records
from .summon_payment import spend_gems, spend_tickets
from .village import INT_MAX, MAX_REVISION, integer

ROUTE = "/item/inlaid-jewelslot"
ATTACH = "/item/attach-jewel"
DETACH = "/item/detach-jewel"
ROUTES = (ROUTE, ATTACH, DETACH)


@dataclass(frozen=True)
class SocketRules:
    relics: frozenset[int]
    ticket: int
    prices: tuple[int, ...]
    jewel_groups: dict[int, int]
    detach_cost: int | None


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS jewel_socket_requests "
        "(operation_id TEXT PRIMARY KEY, relic_id INTEGER NOT NULL, "
        "action TEXT NOT NULL DEFAULT '')"
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(jewel_socket_requests)")}
    if "action" not in columns:
        # Receipts from the original inlay-only handler all represent opening a socket.
        db.execute("ALTER TABLE jewel_socket_requests ADD COLUMN action TEXT NOT NULL DEFAULT ''")


@lru_cache(maxsize=2)
def socket_rules(body):
    tables = records(decode(body))[1]
    try:
        items = json.loads(tables["items"][1])
        inlaid = json.loads(tables["inlaid"][1])
        capacity = inlaid["constants"]["InlaidCount"]["KakaoGlobal"]
        if not integer(capacity, 16, 1):
            raise ValueError("Invalid regional relic socket limit")
        costs = {}
        for row in inlaid["InlaidCount"]:
            slot, cost = row["Count"], row["CountUpNeeded"]
            if not integer(slot, minimum=1) or slot in costs or not integer(cost, minimum=1):
                raise ValueError("Invalid relic inlaying cost")
            costs[slot] = cost
        prices = tuple(costs[n] for n in range(1, capacity + 1))
        relics = frozenset(
            r["Id"] for r in items if r["Type"] == "relic" and r.get("OriginRarity") == 4
        )
        jewels = {r["Id"]: r["GroupId"] for r in items if r["Type"] == "jewel"}
        (ticket,) = (
            r["Id"] for r in items if r["Type"] == "ticket" and r["Name"] == "inlaid_ticket"
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Missing or invalid relic inlaying rules in client static data") from error
    if not relics or not all(integer(i, minimum=1) for i in (*relics, ticket)) or ticket in relics:
        raise ValueError("Invalid Epic relic or Inlaying Ticket spec")
    return SocketRules(relics, ticket, prices, jewels, inlaid["constants"].get("DetachCost"))


def request_action(route, body):
    if not isinstance(body, dict) or not integer(body.get("RelicId"), minimum=1):
        raise ValueError("Select an owned relic")
    if route == ROUTE and set(body) == {"RelicId"}:
        return ""
    if not integer(body.get("SlotIndex"), 15):
        raise ValueError("Select a valid relic socket")
    if route == DETACH and set(body) == {"RelicId", "SlotIndex"}:
        return json.dumps([route, body["SlotIndex"]])
    if (
        route == ATTACH
        and set(body)
        in ({"RelicId", "SlotIndex", "JewelId"}, {"RelicId", "SlotIndex", "JewelId", "Destruction"})
        and integer(body["JewelId"], minimum=1)
        and type(body.get("Destruction", False)) is bool
    ):
        return json.dumps(
            [route, body["SlotIndex"], body["JewelId"], body.get("Destruction", False)]
        )
    raise ValueError("Invalid relic socket action")


def change_jewel(route, body, user, inventory, relic, slots, rules):
    index = body["SlotIndex"]
    if index >= len(slots) or len(slots) > len(rules.prices):
        raise ValueError("Open the selected socket before changing its jewel")
    old = slots[index]
    if old and (old not in rules.jewel_groups or relic["Locked"]):
        raise ValueError("Cannot remove a jewel from a locked relic or with an unknown spec")
    if route == DETACH and not old:
        raise ValueError("The selected socket is empty")

    replacement = 0
    if route == ATTACH:
        stack = target_row(user, inventory, body["JewelId"], "ItemStackables")
        replacement = stack["ItemId"]
        if stack["Locked"] or replacement not in rules.jewel_groups or replacement == old:
            raise ValueError("Select a different unlocked jewel from your inventory")
        if any(
            rules.jewel_groups.get(j) == rules.jewel_groups[replacement]
            for n, j in enumerate(slots)
            if n != index and j
        ):
            raise ValueError("A jewel of this group is already attached")
        stack["Amount"] -= 1

    counters = []
    if old and not body.get("Destruction", False):
        spend_gems(user, rules.detach_cost)
        return_one_jewel(user, inventory, old)
        counters.append("DetachJewelCount")
    if replacement:
        counters.append("AttachJewelCount")
    slots[index] = replacement
    return counters


def handle(account, body, operation_id, route):
    action = request_action(route, body)
    if (
        not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Inlaying requires an owned relic ID and a request identity")
    relic_id = body["RelicId"]
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user, record = profile["User"], profile["UserRecord"]
        previous = db.execute(
            "SELECT relic_id,action FROM jewel_socket_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if previous:
            if previous != (relic_id, action):
                raise ValueError("Socket request identity already belongs to another action")
            return {"User": user, "UserRecord": record}

        rules = socket_rules(account.references.read_bytes("static_data_get.bin"))
        inventory = owned_inventory(user)
        relic = target_row(user, inventory, relic_id, "ItemMiscs")
        if relic["ItemId"] not in rules.relics or relic["Amount"] != 1:
            raise ValueError("Only an owned Epic relic can be inlaid")
        slots = relic.get("JewelSlots")
        if slots is None:
            slots = []
        if not isinstance(slots, list) or any(not integer(jewel) for jewel in slots):
            raise ValueError("Invalid saved relic sockets")
        if record.get("Misc") is None:
            record["Misc"] = {}
        misc = record["Misc"]
        if (
            not isinstance(misc, dict)
            or not integer(record.get("Cas"), MAX_REVISION - 1)
            or not integer(user.get("Cas"), MAX_REVISION - 1)
        ):
            raise ValueError("Invalid saved inlaying count or revision")
        if route == ROUTE:
            if len(slots) >= len(rules.prices):
                raise ValueError("This relic already has its maximum number of sockets")
            spend_tickets(user, rules.ticket, rules.prices[len(slots)])
            relic["JewelSlots"] = [*slots, 0]
            counters = ["InlaidCount"]
        else:
            counters = change_jewel(route, body, user, inventory, relic, slots, rules)
        for name in counters:
            value = misc.get(name, 0)
            if not integer(value, INT_MAX - 1):
                raise ValueError("Invalid saved relic forge counter")
            misc[name] = value + 1
        user["Cas"] += 1
        record["Cas"] += 1
        db.execute(
            "UPDATE local_account SET profile=? WHERE id=1",
            (json.dumps(profile, separators=(",", ":")),),
        )
        db.execute(
            "INSERT INTO jewel_socket_requests(operation_id,relic_id,action) VALUES(?,?,?)",
            (operation_id, relic_id, action),
        )
    return {"User": user, "UserRecord": record}
