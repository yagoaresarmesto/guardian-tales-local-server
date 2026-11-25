# SPDX-License-Identifier: Apache-2.0
"""Share the verified source tables used by hero progression rules."""

from functools import lru_cache

from .raid_static import decode, records

GROWTH_TABLES = {
    "heroes",
    "items",
    "constants",
    "exps2",
    "unlockfeature",
    "awakeningnodedata",
    "awakeningnodelayout",
    "awakeningnodelayout_client",
    "awakeningtreenodes",
    "charactertreeconfig",
}


@lru_cache(maxsize=1)
def growth_tables(body):
    _, tables = records(decode(body))
    return {name: row[1] for name, row in tables.items() if name in GROWTH_TABLES}


def warm_growth_tables(references):
    """Decode the optional catalog before the backend starts accepting requests."""
    try:
        growth_tables(references.read_bytes("static_data_get.bin"))
    except (OSError, ValueError):
        # A missing or invalid optional pack is reported when a route requires it.
        pass
