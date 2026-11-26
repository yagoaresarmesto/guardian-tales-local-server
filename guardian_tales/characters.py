# SPDX-License-Identifier: Apache-2.0
"""Look up owned heroes and construct their initial progression and equipment."""

from contextlib import contextmanager

from .village import integer


@contextmanager
def hero_transaction(db):
    """Commit a standalone upgrade, or keep it inside a larger atomic hero edit."""
    if not db.in_transaction:
        with db:
            db.execute("BEGIN IMMEDIATE")
            yield
        return
    db.execute("SAVEPOINT hero_upgrade")
    try:
        yield
    except BaseException:
        db.execute("ROLLBACK TO hero_upgrade")
        raise
    finally:
        db.execute("RELEASE hero_upgrade")


def hero_resource(user, *payment_fields):
    # User.Apply merges supplied collections. Include the full roster and any
    # payment collections, even when spending the last stack leaves an empty list.
    resource = {key: user[key] for key in ("Id", "Cas", "Characters")}
    resource.update((key, user[key]) for key in payment_fields if key in user)
    return resource


def owned_character(user, ident):
    roster = user.get("Characters")
    if not isinstance(roster, list) or any(
        not isinstance(hero, dict) or not integer(hero.get("Id"), minimum=1) for hero in roster
    ):
        raise ValueError("Invalid saved hero roster")
    matches = [hero for hero in roster if hero["Id"] == ident]
    if len(matches) != 1:
        raise ValueError("Select one owned hero")
    return matches[0]


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
