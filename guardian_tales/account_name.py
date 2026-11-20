# SPDX-License-Identifier: Apache-2.0
"""Free local account renaming with structural validation and atomic retries."""

import json

from .village import MAX_REVISION, integer

ROUTE = "/user/change-name"


def valid_name(name):
    if not isinstance(name, str) or any(ord(c) < 32 or ord(c) == 127 for c in name):
        return False
    try:
        return 2 <= len(name.encode("utf-16le")) // 2 <= 10
    except UnicodeError:
        return False


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS account_name_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


def resource(profile):
    result = {"User": {key: profile["User"][key] for key in ("Id", "Cas", "Name")}}
    if profile.get("GuildMember") is not None:
        result["GuildMember"] = profile["GuildMember"]
    return result


def change(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"Name"}
        or not valid_name(body["Name"])
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Choose a nickname of 2..10 UTF-16 units after completing the prologue")
    profile = account.profile()
    user = profile["User"]
    member = profile.get("GuildMember")
    if (
        not integer(user.get("Id"), minimum=1)
        or not integer(user.get("Cas"), MAX_REVISION)
        or not valid_name(user.get("Name"))
        or member is not None
        and (
            not isinstance(member, dict)
            or type(member.get("UserId")) is not int
            or member["UserId"] != user["Id"]
            or not integer(member.get("Cas"), MAX_REVISION)
            or not isinstance(member.get("Name"), str)
        )
    ):
        raise ValueError("Invalid saved nickname, owner or revision")
    encoded = json.dumps(body, separators=(",", ":"))
    previous = account.db.execute(
        "SELECT request FROM account_name_requests WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if previous:
        if previous[0] != encoded:
            raise ValueError("Nickname request identity was reused with different data")
        # Retries return the current name, including later edits, without another write.
        return resource(profile)
    changed = user["Name"] != body["Name"]
    member_changed = member is not None and member["Name"] != body["Name"]
    if changed or member_changed:
        if (
            changed
            and user["Cas"] == MAX_REVISION
            or member_changed
            and member["Cas"] == MAX_REVISION
        ):
            raise ValueError("Nickname revision overflow")
        if changed:
            user["Name"] = body["Name"]
            user["Cas"] += 1
        if member_changed:
            member["Name"] = body["Name"]
            member["Cas"] += 1
    with account.db:
        if changed or member_changed:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        account.db.execute("INSERT INTO account_name_requests VALUES(?,?)", (operation_id, encoded))
    return resource(profile)
