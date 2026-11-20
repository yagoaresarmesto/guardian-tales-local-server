# SPDX-License-Identifier: Apache-2.0
"""Empty lobby catalogs/read responses for the isolated single-player prototype.

No purchases, reward claims, multiplayer, or village construction mutations are
implemented. Response framing/body kinds follow the reference client contracts.
"""

import json
from pathlib import Path

from .protocol import Packet
from .reference import compressed_empty_list
from .summon_selection import load_selection_catalog
from .weapon_selection import load_selection_catalog as load_weapon_selection_catalog
from .weapon_selection import selection_checksum

ROOT = Path(__file__).resolve().parent / "templates"
READ_RESPONSES = json.loads((ROOT / "empty_lobby.json").read_text())
LOBBY_ROUTES = tuple(READ_RESPONSES)


def respond(request, references=None):
    template = READ_RESPONSES[request["api"]]
    value = template["value"]
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
