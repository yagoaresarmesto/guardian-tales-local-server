# SPDX-License-Identifier: Apache-2.0
"""Construct a persistent inventory row with the client's default options."""


def inventory_item(inventory_id, item_id):
    return dict(
        Id=inventory_id,
        ItemId=item_id,
        Amount=1,
        Experience=0,
        EvolveProgress=0,
        Options=None,
        RelicOptions=None,
        LimitBreaks=0,
        Locked=False,
        JewelSlots=None,
        EngraveOptions=None,
        EngraveCeiling=0,
    )
