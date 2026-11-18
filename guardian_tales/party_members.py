# SPDX-License-Identifier: Apache-2.0
"""Persist an ordered normal-party roster without changing heroes, gear or presets."""

import json

from .village import MAX_REVISION, integer

ROUTE = "/user/save-party-member/v2"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS party_member_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


def resource(user):
    # Native User.Apply preserves missing inventory/hero/preset fields. PartyInfo
    # resolves these inventory IDs using the client's existing owned-hero registry.
    return {key: user[key] for key in ("Id", "Cas", "Party")}


def save(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"CharacterIds"}
        or not isinstance(body["CharacterIds"], list)
        or not 1 <= len(body["CharacterIds"]) <= 4
        or any(not integer(i, minimum=1) for i in body["CharacterIds"])
        or len(set(body["CharacterIds"])) != len(body["CharacterIds"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Save an ordered party of one to four distinct owned character IDs")
    encoded = json.dumps(body, separators=(",", ":"))
    profile = account.profile()
    user = profile["User"]
    previous = account.db.execute(
        "SELECT request FROM party_member_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Party-member request identity was reused for another formation")
        return {"User": resource(user)}
    characters, party, revision = user.get("Characters"), user.get("Party"), user.get("Cas")
    if (
        not isinstance(characters, list)
        or any(not isinstance(c, dict) or not integer(c.get("Id"), minimum=1) for c in characters)
        or not integer(revision, MAX_REVISION)
        or not isinstance(party, dict)
        or type(party.get("Id")) is not int
        or party["Id"] != 0
        or not isinstance(party.get("Characters"), list)
        or len(party["Characters"]) > 4
        or any(not integer(i, minimum=1) for i in party["Characters"])
    ):
        raise ValueError("Invalid saved normal party, owned roster or revision")
    owned = {c["Id"] for c in characters}
    if (
        len(owned) != len(characters)
        or len(set(party["Characters"])) != len(party["Characters"])
        or any(i not in owned for i in party["Characters"] + body["CharacterIds"])
    ):
        raise ValueError("Party members must identify unambiguous owned inventory heroes")
    changed = party["Characters"] != body["CharacterIds"]
    if changed:
        if revision == MAX_REVISION:
            raise ValueError("Party-member revision overflow")
        # Preserve order: the first member is the leader. A shorter list clears
        # old trailing slots in the native PartyInfo.Apply implementation.
        party["Characters"] = list(body["CharacterIds"])
        user["Cas"] += 1
    with account.db:
        if changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute("INSERT INTO party_member_requests VALUES(?,?)", (operation_id, encoded))
    return {"User": resource(user)}
