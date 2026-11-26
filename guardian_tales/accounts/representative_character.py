# SPDX-License-Identifier: Apache-2.0
"""Select an owned profile portrait without changing the hero or other progress."""

import json

from guardian_tales.settlement.village import MAX_REVISION, integer

ROUTE = "/user/select-representative-character"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS representative_character_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


def resource(user):
    # The native callback reads no response fields. The shared User.Apply
    # handler updates this nullable Int32 inventory ID and retains absent data.
    return {key: user[key] for key in ("Id", "Cas", "RepresentativeCharacterId")}


def select(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"CharacterId"}
        or not integer(body["CharacterId"], minimum=1)
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Select one owned character ID after completing the prologue")
    profile = account.profile()
    user = profile["User"]
    characters = user.get("Characters")
    revision = user.get("Cas")
    current = user.get("RepresentativeCharacterId")
    if (
        not integer(user.get("Id"), minimum=1)
        or not integer(revision, MAX_REVISION)
        or not isinstance(characters, list)
        or not characters
        or "RepresentativeCharacterId" not in user
        or any(not isinstance(c, dict) or not integer(c.get("Id"), minimum=1) for c in characters)
        or (current is not None and not integer(current))
    ):
        raise ValueError("Invalid saved representative character, owned roster or revision")
    owned = {c["Id"] for c in characters}
    if len(owned) != len(characters) or (current not in (None, 0) and current not in owned):
        raise ValueError("Saved representative character must identify an unambiguous owned hero")
    encoded = json.dumps(body, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM representative_character_requests WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError(
                "Representative-character request identity was reused with different data"
            )
        # An old retry must return the current selection, never restore an old
        # portrait or an old copy of inventory, equipment or other profile data.
        return {"User": resource(user)}
    if body["CharacterId"] not in owned:
        raise ValueError("Representative character must be an owned inventory hero")
    changed = current != body["CharacterId"]
    if changed:
        if revision == MAX_REVISION:
            raise ValueError("Representative-character revision overflow")
        user["RepresentativeCharacterId"] = body["CharacterId"]
        user["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute(
            "INSERT INTO representative_character_requests VALUES(?,?)", (operation_id, encoded)
        )
    return {"User": resource(user)}
