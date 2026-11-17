# SPDX-License-Identifier: Apache-2.0
"""Construct a new owned level-one hero with empty optional equipment/progression."""


def new_character(inventory_id, spec_id, weapon1=None, weapon2=None):
    return dict(
        Id=inventory_id,
        CharacterId=spec_id,
        Experience=0,
        LimitBreaks=0,
        Weapon1=weapon1,
        Weapon2=weapon2,
        Accessory1=None,
        Costume=None,
        Orb1=None,
        Orb2=None,
        Merch=None,
        Relic=None,
        EquipCostumes={},
        AwakeningTree="",
        Knowledge=0,
        RankUpgrade=0,
        SpriteRank=None,
        BlessLevel=0,
        AwakeningTreeGold=0,
        Flag=0,
    )
