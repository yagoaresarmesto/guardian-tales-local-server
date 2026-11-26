# SPDX-License-Identifier: Apache-2.0
"""Extract a native equipment-ID batch without granting Magic Metal or rewards."""

from guardian_tales.settlement.village import integer

from .item_lock import MAX_BATCH
from .item_sell import EXTRACT, dispose

ROUTE = EXTRACT


def extract(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"ItemIds"}
        or not isinstance(body["ItemIds"], list)
        or not 1 <= len(body["ItemIds"]) <= MAX_BATCH
        or any(not integer(ident, minimum=1) for ident in body["ItemIds"])
        or len(set(body["ItemIds"])) != len(body["ItemIds"])
    ):
        raise ValueError("Extract a bounded batch of distinct owned equipment inventory IDs")
    return dispose(
        account,
        {"SellItems": {str(ident): 1 for ident in body["ItemIds"]}},
        operation_id,
        route=ROUTE,
        native_request={"ItemIds": sorted(body["ItemIds"])},
    )
