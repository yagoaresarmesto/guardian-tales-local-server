# SPDX-License-Identifier: Apache-2.0
"""Read saved Training Room slots without changing assignments, boosts or cooldowns."""

from datetime import datetime

from guardian_tales.inventory.weapon_enhance import decimal_id
from guardian_tales.settlement.village import MAX_REVISION, integer

ROUTE = "/training-room/enter"
BOOST_FIELDS = (
    "IsEvolve",
    "IsAwakening",
    "IsLimitBreak",
    "IsWeaponOption",
    "IsEvolveOnly",
    "IsLevel",
    "IsBlessing",
    "IsEngraving",
    "IsMyth",
)


def enter(account, request):
    if request is not None and (not isinstance(request, dict) or request):
        raise ValueError("Training Room entry accepts no parameters")
    if account.needs_prologue():
        raise ValueError("Complete the prologue before entering the Training Room")
    user = account.profile()["User"]
    slots = user.get("TrainingSlots")
    if (
        not integer(user.get("Id"), minimum=1)
        or not integer(user.get("Cas"), MAX_REVISION)
        or not isinstance(slots, dict)
    ):
        raise ValueError("Invalid saved Training Room owner, revision or slot map")
    for key, slot in slots.items():
        if (
            not decimal_id(key)
            or not isinstance(slot, dict)
            or not integer(slot.get("Id"), minimum=1)
            or str(slot["Id"]) != key
            or not integer(slot.get("CharacterId", 0))
            or not integer(slot.get("ItemId", 0))
            or any(name in slot and type(slot[name]) is not bool for name in BOOST_FIELDS)
        ):
            raise ValueError("Invalid saved Training Room slot or assignment")
        stamp = slot.get("NextReactivateTime")
        if stamp is not None:
            try:
                if not isinstance(stamp, str) or datetime.fromisoformat(stamp).utcoffset() is None:
                    raise ValueError("Training Room cooldown must have an explicit timezone")
            except (ValueError, TypeError, OverflowError) as error:
                raise ValueError("Invalid saved Training Room cooldown") from error
    # The native callback only opens the scene. Shared User.Apply refreshes this
    # slot map, retaining absent inventory/equipment and other account fields.
    # Expired cooldowns, active assignments and future fields are returned verbatim.
    return {"User": {key: user[key] for key in ("Id", "Cas", "TrainingSlots")}}
