# SPDX-License-Identifier: Apache-2.0
"""Guild Raid catalog and selection adapter."""

import hashlib
import json
from functools import lru_cache

from ... import guild_raid, raid_custom, raid_static

BOSS_NAMES = {stage: name for name, stage in raid_custom.BOSS_STAGES.items()}
ELEMENT_NAMES = {values[0]: name for name, values in raid_custom.ELEMENTS.items()}


@lru_cache(maxsize=2)
def encounter_elements(body):
    tables = raid_static.records(raid_static.decode(body))[1]
    raid = json.loads(tables["guildraid2"][1])
    monsters = json.loads(tables["monsters"][1]) if "monsters" in tables else []
    elements = {row["Id"]: ELEMENT_NAMES.get(row.get("ElementalType")) for row in monsters}
    return {row["Id"]: elements.get(row.get("MonsterId")) for row in raid["BossDetails"]}


def season_view(season, elements):
    return {
        "id": season["season_id"],
        "hpPerBar": season["first_round"]["boss_hp_bar"],
        "bosses": [
            {
                "stage": row["stage_id"],
                "boss": BOSS_NAMES.get(row["stage_id"]),
                "element": elements.get(row["id"]),
            }
            for row in sorted(season["bosses"], key=lambda row: row["slot"])
        ],
    }


def map_image(references):
    return references.directory.parent / "resources/files/media/guildraid/raid_bg_02.png"


def state(references):
    catalog = guild_raid.load_catalog(references)
    saved = guild_raid.load_selection(references) or {}
    ident = saved.get("season_id", catalog["default_season_id"])
    active = guild_raid.find_season(catalog, ident, saved or None)
    stock = guild_raid.find_season(catalog, ident)
    elements = encounter_elements(references.read_bytes("static_data_get.bin"))
    active_elements = elements
    custom = "custom_season" in saved
    if custom:
        # Resolve the exact published snapshot, including selections from older CLIs.
        digest = saved["static_data_sha256"]
        body = references.read_bytes(f"guild_raid_static_{digest}.bin")
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("The prepared Raid tables do not match the active selection")
        active_elements = encounter_elements(body)
    return {
        "active": season_view(active, active_elements),
        "custom": custom,
        "customHp": custom and active["round_set"] != stock["round_set"],
        "prepared": "static_data_revision" in saved,
        "revision": saved.get("static_data_revision", 0),
        "seasons": [
            season_view(s, elements)
            for s in sorted(catalog["seasons"], key=lambda s: s["season_id"])
        ],
        "bossNames": list(raid_custom.BOSS_STAGES),
        "elementNames": list(raid_custom.ELEMENTS),
        "hasMap": map_image(references).is_file(),
    }


def apply(references, body):
    if not isinstance(body, dict) or not guild_raid.integer(body.get("revision"), 0):
        raise ValueError("A current Raid revision is required")
    revision = body["revision"]
    if body.get("mode") == "stock" and body.keys() == {"mode", "revision", "season"}:
        guild_raid.select_season(references, body["season"], expected_revision=revision)
    elif body.get("mode") == "custom" and body.keys() == {"mode", "revision", "lineup", "hpPerBar"}:
        lineup = raid_custom.validate_lineup(body["lineup"])
        guild_raid.select_season(
            references, lineup=lineup, hp_per_bar=body["hpPerBar"], expected_revision=revision
        )
    else:
        raise ValueError("Choose an original season or a four-boss custom lineup")
