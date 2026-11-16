# SPDX-License-Identifier: Apache-2.0
"""Empty lobby catalogs/read responses for the isolated single-player prototype.

No purchases, reward claims, multiplayer, or village construction mutations are
implemented. Response framing/body kinds follow the reference client contracts.
"""

import json
from pathlib import Path

from .protocol import Packet
from .reference import compressed_empty_list

ROOT = Path(__file__).resolve().parent / "templates"
READ_RESPONSES = json.loads((ROOT / "empty_lobby.json").read_text())
LOBBY_ROUTES = tuple(READ_RESPONSES)


def respond(request):
    template = READ_RESPONSES[request["api"]]
    if template["body_type"] == 2:
        assert template["value"] == []
        body = compressed_empty_list()
    else:
        body = json.dumps(template["value"], separators=(",", ":")).encode()
    return Packet(
        packet_type=1,
        body_type=template["body_type"],
        sequence_id=request["sequence_id"],
        body=body,
    )
