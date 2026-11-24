# SPDX-License-Identifier: Apache-2.0
"""Read the native list of hero rosters, including Tetis and Champion Arena."""

import json

from .snapshots import preserved_read

SAVE = "/preset/set-character-list-preset"
DELETE = "/preset/delete-character-list-preset"


def group(db):
    row = db.execute("SELECT value FROM character_list_preset_state WHERE id=1").fetchone()
    if row:
        return json.loads(row[0])
    captured = preserved_read(db, "/preset/get-presets") or {}
    return captured.get("UserCharacterListPreset", {"Cas": 0, "Presets": []})
