# SPDX-License-Identifier: Apache-2.0
"""Read cosmetic eligibility from the matching external client item definitions."""

import json
from functools import lru_cache

from .raid_static import decode, records
from .village import integer


@lru_cache(maxsize=2)
def cosmetic_specs(body, item_type):
    _, tables = records(decode(body))
    if "items" not in tables:
        raise ValueError("Cosmetic selection requires the matching external items table")
    items = json.loads(tables["items"][1])
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= 100000
        or any(
            not isinstance(item, dict)
            or not integer(item.get("Id"), minimum=1)
            or not isinstance(item.get("Type"), str)
            for item in items
        )
        or len({item["Id"] for item in items}) != len(items)
    ):
        raise ValueError("Invalid cosmetic item definitions")
    return frozenset(item["Id"] for item in items if item["Type"] == item_type)
