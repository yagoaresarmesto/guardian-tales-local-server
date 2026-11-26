# SPDX-License-Identifier: Apache-2.0
"""Empty lobby catalogs/read responses for the isolated single-player prototype.

No purchases, reward claims, multiplayer, or village construction mutations are
implemented. Response framing/body kinds follow the reference client contracts.
"""

import json
from datetime import datetime, timedelta, timezone

from guardian_tales.accounts.snapshots import preserved_read
from guardian_tales.content.reference import TEMPLATES, compressed_empty_list
from guardian_tales.runtime.protocol import Packet
from guardian_tales.summons.summon_selection import load_selection_catalog
from guardian_tales.summons.weapon_selection import (
    load_selection_catalog as load_weapon_selection_catalog,
)
from guardian_tales.summons.weapon_selection import selection_checksum

ROOT = TEMPLATES
READ_RESPONSES = json.loads((ROOT / "empty_lobby.json").read_text())
LOBBY_ROUTES = tuple(READ_RESPONSES)


def village_shop(db, body, now):
    if body not in (None, {}):
        raise ValueError("Village shop entry accepts no parameters")
    entry = preserved_read(db, "/lobby-village/enter") if db is not None else None
    if entry is None:
        entry = READ_RESPONSES["/lobby-village/enter"]["value"]
    saved = entry.get("UserLobbyVillage")
    if not isinstance(saved, dict):
        raise ValueError("Invalid saved village state")
    village = saved.copy()
    offers = entry.get("LobbyVillageShopItems", [])
    if not isinstance(offers, list) or any(not isinstance(row, dict) for row in offers):
        raise ValueError("Invalid saved village shop offers")
    refresh = village.get("NextShopRefreshTime")
    deadline = datetime.fromisoformat(refresh) if isinstance(refresh, str) else None
    if deadline is None or deadline.utcoffset() is None or deadline <= now:
        # The popup automatically requests entry again when its countdown expires.
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        village["NextShopRefreshTime"] = midnight.isoformat()
    return {"LobbyVillageShopItems": offers, "UserLobbyVillage": village}


def respond(request, references=None, db=None, request_body=None):
    template = READ_RESPONSES[request["api"]]
    value = template["value"]
    if request["api"] == "/lobby-village/enter-shop":
        value = village_shop(db, request_body, datetime.now(timezone.utc))
    if request["api"] == "/preset/get-presets" and db is not None:
        from guardian_tales.modes.tetis.tetis_presets import group

        value = dict(value, UserCharacterListPreset=group(db))
    if request["api"] == "/content-book/recommend" and db is not None:
        from guardian_tales.modes.tetis.tetis_progress import load_catalog, stored_progress
        from guardian_tales.modes.tetis.tetis_sweep import counter

        progress = stored_progress(db)
        if progress and references is not None:
            catalog = load_catalog(references)
            value = dict(
                value,
                RogueChessFloor=progress["floors"].get(str(catalog.current), 0),
                RogueChessSweepCount=counter(progress, catalog)["PlayCount"],
            )
    if request["api"] in ("/summon/enter", "/summon/on-event"):
        catalog = load_selection_catalog(references)
        weapons = load_weapon_selection_catalog(references)
        if catalog is not None:
            value = dict(value, Checksum=catalog[1])
            if request["api"] == "/summon/on-event":
                value["SelectableCharacter"] = catalog[0]
        if weapons is not None:
            value = dict(value, Checksum=selection_checksum(catalog[0] if catalog else [], weapons))
            if request["api"] == "/summon/on-event":
                value["SelectableWeapon"] = weapons
    if template["body_type"] == 2:
        assert template["value"] == []
        body = compressed_empty_list()
    else:
        body = json.dumps(value, separators=(",", ":")).encode()
    return Packet(
        packet_type=1,
        body_type=template["body_type"],
        sequence_id=request["sequence_id"],
        body=body,
    )
