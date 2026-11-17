# SPDX-License-Identifier: Apache-2.0
"""Preserve imported event coupons during the automatic summon entry check.

The local server has no pickup seasons or conversion catalog. Imported coupons
are therefore retained as opaque historical state, with no executed conversions.
This implements entry compatibility, not redemption or expiration processing.
"""

from .snapshots import is_imported


def check_pickup_exchange(account, request):
    if request not in (None, {}):
        raise ValueError("Pickup ticket exchange check accepts no parameters")
    shop = account.profile()["UserShop"]
    counters = [shop["SummonPickUpTickets"], shop["CollaborationPickUpTickets"]]
    for values in counters:
        if not isinstance(values, dict):
            raise ValueError("Invalid saved pickup coupon map")
        for key, amount in values.items():
            if (
                not isinstance(key, str)
                or not key.isascii()
                or not key.isdecimal()
                or key.startswith("0")
                or len(key) > 10
                or int(key) > 0x7FFFFFFF
                or type(amount) is not int
                or not 0 <= amount <= 0x7FFFFFFFFFFFFFFF
            ):
                raise ValueError("Invalid saved pickup coupon counter")
    if any(counters) and not is_imported(account.db):
        raise ValueError("Exchange of existing local event pickup tickets is not implemented")
    # Returning the current shop preserves every imported counter and revision.
    # Empty result maps mean no conversion occurred; no coupons are cleared and
    # no replacement items, currency or synthetic receipts are created.
    return {
        "UserShop": shop,
        "ExchangeSummonPickUpTickets": {},
        "ExchangeCollaborationPickUpTickets": {},
    }
