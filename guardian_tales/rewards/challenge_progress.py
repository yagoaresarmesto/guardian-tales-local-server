# SPDX-License-Identifier: Apache-2.0
"""Saved progress for challenge types verified against the matching native helper."""

from guardian_tales.campaigns.campaign import CHARGED_STAMINA, RESERVE_STAMINA

MAX_INT = 0x7FFFFFFF
MAX_LONG = 0x7FFFFFFFFFFFFFFF
RECORD_FIELDS = {
    "SummonCharacter": "SummonCharacterCount",
    "SummonEquip": "SummonWeaponCount",
    "Attendance": "LoginDayCount",
    "EvolveCharacters": "EvolveCharacterCount",
    "LimitBreak": "LimitBreakCharacterCount",
    "CraftMerch": "CraftMerchCount",
}
MISC_FIELDS = {
    "BlessCharacters": "BlessCharacterCount",
    "EngraveWeapons": "EngraveWeaponCount",
    "MythCharacters": "MythCharacterCount",
    "DecomposeJewel": "DecomposeJewelCount",
    "LobbyComplaintClear": "ComplaintClear",
}
CONDITIONS = (
    frozenset(RECORD_FIELDS)
    | frozenset(MISC_FIELDS)
    | {"CollectHero", "CollectGold", "UseStamina", "TowerInfinityClear"}
)


def integer(value, maximum=MAX_INT):
    return type(value) is int and 0 <= value <= maximum


def progress_value(profile, condition):
    user, record = profile["User"], profile["UserRecord"]
    if condition in RECORD_FIELDS:
        value = record.get(RECORD_FIELDS[condition], 0)
    elif condition in MISC_FIELDS:
        misc = record.get("Misc")
        if misc is not None and not isinstance(misc, dict):
            raise ValueError("Invalid saved miscellaneous challenge counters")
        value = (misc or {}).get(MISC_FIELDS[condition], 0)
    elif condition == "CollectHero":
        characters = user.get("Characters")
        if not isinstance(characters, list):
            raise ValueError("Invalid saved hero collection")
        value = len(characters)
    elif condition == "TowerInfinityClear":
        tower = profile["UserProgress"].get("TowerInfinity")
        if not isinstance(tower, dict):
            raise ValueError("Invalid saved Orbital progress")
        value = tower.get("Floor", 0)
    elif condition in ("CollectGold", "UseStamina"):
        ids = (70001,) if condition == "CollectGold" else (CHARGED_STAMINA, RESERVE_STAMINA)
        values = []
        for asset_id in ids:
            matches = [a for a in user["Assets"] if a.get("Id") == asset_id]
            if len(matches) != 1 or not integer(matches[0].get("Spent"), MAX_LONG):
                raise ValueError("Invalid saved asset spending for challenge progress")
            asset = matches[0]
            value = asset["Spent"]
            if condition == "CollectGold":
                if not integer(asset.get("Amount")):
                    raise ValueError("Invalid saved gold balance")
                value += asset["Amount"]
            values.append(value)
        value = sum(values)
        if condition == "CollectGold":
            value = min(value, MAX_INT)
    else:
        raise ValueError("Challenge condition does not have a verified saved-state evaluator")
    if not integer(value):
        raise ValueError("Invalid saved challenge progress or native Int32 overflow")
    return value
