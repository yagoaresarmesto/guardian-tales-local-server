# SPDX-License-Identifier: Apache-2.0
"""Validate client-managed badge selection without rewriting the saved account."""

from .cosmetic_items import cosmetic_specs
from .village import integer

ROUTE = "/user/set-profile-badge"


def select(account, body):
    if (
        not isinstance(body, dict)
        or set(body) != {"BadgeId"}
        or (body["BadgeId"] is not None and not integer(body["BadgeId"], minimum=1))
        or account.needs_prologue()
    ):
        raise ValueError("Select one owned badge inventory ID, or null, after the prologue")
    user = account.profile()["User"]
    items = user.get("ItemMiscs")
    if (
        not integer(user.get("Id"), minimum=1)
        or not isinstance(items, list)
        or any(
            not isinstance(item, dict)
            or any(not integer(item.get(key), minimum=1) for key in ("Id", "ItemId"))
            or not integer(item.get("Amount"))
            for item in items
        )
        or len({item["Id"] for item in items}) != len(items)
    ):
        raise ValueError("Invalid saved badge inventory or owner")
    specs = cosmetic_specs(account.references.read_bytes("static_data_get.bin"), "profilebadge")
    owned = {item["Id"] for item in items if item["Amount"] > 0 and item["ItemId"] in specs}
    if body["BadgeId"] is not None and body["BadgeId"] not in owned:
        raise ValueError("Profile badge must be a positive-amount owned badge inventory item")
    # BadgeSelectPopup.Finish ignores the response body. Its local close
    # callback saves the design ID in PersistentPlayerPrefs and redraws it.
    # An empty acknowledgement cannot replace inventory or revert a later choice.
    return {}
