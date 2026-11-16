# SPDX-License-Identifier: Apache-2.0
"""Pinned first-phase identifiers and the client's stage progress encoding."""

import base64
import struct

FIRST_CHAPTER_CODE = 10001
FIRST_STAGE_ID = 100010001
FIRST_CHAPTER_STAGES = tuple(range(FIRST_STAGE_ID, FIRST_STAGE_ID + 7))
FIRST_STAGE_STAMINA = 15
FIRST_CLEAR_GEMS = 50
FREE_GEMS = 70003
STAGE_OPENED = 1
STAGE_UNLOCKED = 2
STAGE_CLEARED = 4
CHARGED_STAMINA = 70006
RESERVE_STAMINA = 70032
FIRST_PURPLE_COIN = 71001
FIRST_PURPLE_COIN_KEYS = range(1, 27)
# Native StageProgress uses separate stores for purple coins (2) and star pieces (3).
FIRST_STAGE_PICKUPS = {
    FIRST_PURPLE_COIN: (2, FIRST_PURPLE_COIN_KEYS),
    70005: (3, range(1, 4)),
}
# Public first-phase monster handles, in their tilemap name-table order.
FIRST_MONSTERS = {
    name: index
    for index, name in enumerate(
        (
            "first_goblin_1",
            "first_goblin_2",
            "room3_goblin_1",
            "room3_goblin_2",
            "room3_slime",
            "battle_2_slime_1",
            "battle_2_slime_2",
            "battle_2_goblin_1",
            "battle_2_goblin_2",
            "room_inn_slime_1",
            "room_inn_slime_2",
            "room_inn_slime_3",
            "room_inn_slime_4",
            "battle_2_goblin_big",
        ),
        start=1,
    )
}
# Local provisional rule: one level-1 ExpsData row per new defeated handle.
# Server-side multipliers/random drops have not been reconstructed.
FIRST_MONSTER_EXP = 79
FIRST_MONSTER_GOLD = 87
FIRST_STAGE_ITEMS = {
    "shield": (1, 9080040, "ItemWeapons"),
    "sword": (2, 9010010, "ItemWeapons"),
    "costume": (3, 10048, "ItemMiscs"),
}


def encode_stage_progress(stores):
    """Encode native StageProgress v2 / CustomDataStore values.

    Stores contain byte-indexed booleans or signed 32-bit integers. Integer keys
    also occupy a zero bit in the boolean bitmap. The trailing StonePieces byte
    remains zero; stone-board puzzles are not implemented yet.
    """
    if not stores:
        return ""
    wire = bytearray((2, len(stores)))
    for category, values in sorted(stores.items()):
        if type(category) is not int or not 1 <= category <= 11 or not values:
            raise ValueError("Invalid stage progress category")
        if any(type(key) is not int or not 0 <= key < 255 for key in values):
            raise ValueError("Stage progress keys must fit the native byte count")
        maximum = max(values) + 1
        bits = bytearray((maximum + 7) // 8)
        integers = []
        for key, value in sorted(values.items()):
            if type(value) is bool:
                if value:
                    bits[key // 8] |= 1 << (key % 8)
            elif type(value) is int and -0x80000000 <= value <= 0x7FFFFFFF:
                integers.append((key, value))
            else:
                raise ValueError("Invalid stage progress value")
        wire.extend((category, maximum))
        wire.extend(bits)
        wire.append(len(integers))
        for key, value in integers:
            wire.append(key)
            wire.extend(struct.pack("<i", value))
    wire.append(0)
    return base64.b64encode(wire).decode("ascii")


def initial_stage_progresses(request):
    if not isinstance(request, dict) or type(request.get("ChapterCode")) is not int:
        raise ValueError("Malformed chapter progress request")
    if request["ChapterCode"] != FIRST_CHAPTER_CODE:
        raise ValueError("Chapter progress is implemented only for the first story chapter")
    # ChapterProgress constructs a StageProgress per dictionary entry. Its
    # FromBase64 method accepts an empty string and keeps the initialized empty
    # stores. Missing entries instead return null when the entry UI asks for one.
    return {"StageProgresses": {str(stage): "" for stage in FIRST_CHAPTER_STAGES}}
