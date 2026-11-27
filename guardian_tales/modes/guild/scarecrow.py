# SPDX-License-Identifier: Apache-2.0
"""Single-player Guild Castle scarecrow battles and elemental personal bests."""

import json
from datetime import datetime, timezone

from guardian_tales.campaigns.story_quests import save_profile
from guardian_tales.heroes.characters import owned_character
from guardian_tales.settlement.village import integer
from guardian_tales.teams.presets import GEAR_FIELDS, owned_party_preset

from .guild_menu import SCARECROW_RECORDS, castle_user, saved_member
from .guild_raid import MAX_STAGE_DAMAGE, party_damage_total

START = "/guild-castle/start-scarecrow/v2"
FINISH = "/guild-castle/finish-scarecrow/v3"
ROUTES = (START, FINISH)
ELEMENT_NAMES = ("None", "Fire", "Ice", "Earth", "Light", "Darkness")


def create_tables(db):
    # Only the live fight needs a party snapshot. Finished runs retain a small receipt.
    db.execute(
        "CREATE TABLE IF NOT EXISTS scarecrow_runs (epoch TEXT NOT NULL, start_seq INTEGER NOT NULL,"
        " target INTEGER NOT NULL, element INTEGER NOT NULL, preset INTEGER, start_reply TEXT,"
        " finish_seq INTEGER, damages TEXT, old_record INTEGER,"
        " PRIMARY KEY(epoch,start_seq), UNIQUE(epoch,finish_seq))"
    )


def battle_user(account, profile, preset):
    user = profile["User"]
    if preset:
        members = owned_party_preset(account.db, profile, preset)["Characters"]
        heroes = []
        for member in members:
            hero = dict(owned_character(user, member["Id"]))
            for field in GEAR_FIELDS:
                hero["Accessory1" if field == "Accessory" else field] = member.get(field) or None
            heroes.append(hero)
    else:
        ids = (user.get("Party") or {}).get("Characters")
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 4
            or not all(integer(i, minimum=1) for i in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Choose an owned party for the scarecrow")
        heroes = [owned_character(user, i) for i in ids]
    visitor = castle_user(user, heroes)
    for key in (
        "Options",
        "GuardianExperience",
        "GuardianMasteryLevel",
        "Unlocked",
        "TrainingSlots",
    ):
        if key in user:
            visitor[key] = user[key]
    return visitor


def start(account, profile, body, epoch, seq):
    element = body.get("elementalType")
    if isinstance(element, str) and element in ELEMENT_NAMES:
        element = 1 << ELEMENT_NAMES.index(element)
    preset = body.get("presetId")
    if (
        set(body) != {"ScarecrowId", "elementalType", "presetId"}
        or type(element) is not int
        or element not in (1, 2, 4, 8, 16, 32)
        or preset is not None
        and not integer(preset)
    ):
        raise ValueError("Invalid scarecrow element or party preset")
    target = body["ScarecrowId"]
    row = account.db.execute(
        "SELECT start_seq,target,element,preset,start_reply,finish_seq FROM scarecrow_runs "
        "WHERE epoch=? ORDER BY start_seq DESC LIMIT 1",
        (epoch,),
    ).fetchone()
    if row:
        if row[:4] == (seq, target, element, preset) and row[4] is not None:
            return json.loads(row[4])
        if seq <= (row[5] or row[0]):
            raise ValueError("Stale or conflicting scarecrow start")
    reply = {
        "CastleUser": battle_user(account, profile, preset),
        "ScarecrowStartTime": datetime.now(timezone.utc).isoformat(),
    }
    # A fresh start replaces an interrupted battle, including one from an older login.
    account.db.execute("UPDATE scarecrow_runs SET start_reply=NULL WHERE start_reply IS NOT NULL")
    account.db.execute(
        "INSERT INTO scarecrow_runs(epoch,start_seq,target,element,preset,start_reply) VALUES(?,?,?,?,?,?)",
        (epoch, seq, target, element, preset, json.dumps(reply, separators=(",", ":"))),
    )
    return reply


def finish(account, profile, member, body, epoch, seq):
    if set(body) != {"ScarecrowId", "Damages"}:
        raise ValueError("Scarecrow completion requires the target and party damages")
    damage = party_damage_total(body["Damages"])
    target = body["ScarecrowId"]
    damages = json.dumps(body["Damages"], separators=(",", ":"))
    receipt = account.db.execute(
        "SELECT target,damages,old_record FROM scarecrow_runs WHERE epoch=? AND finish_seq=?",
        (epoch, seq),
    ).fetchone()
    if receipt:
        if receipt[:2] != (target, damages):
            raise ValueError("Scarecrow completion conflicts with its receipt")
        return {"OldRecord": receipt[2], "GuildMember": member}
    run = account.db.execute(
        "SELECT start_seq,element FROM scarecrow_runs WHERE epoch=? AND target=? AND start_reply IS NOT NULL",
        (epoch, target),
    ).fetchone()
    if not run or seq <= run[0]:
        raise ValueError("Finish the scarecrow battle that was started")
    key = SCARECROW_RECORDS[run[1].bit_length() - 1]
    records = member.get("UserRecords")
    if records is None:
        records = {}
    if not isinstance(records, dict):
        raise ValueError("Invalid saved scarecrow records")
    best = records.get(key)
    if best is None:
        best = 0
    if not integer(best, maximum=MAX_STAGE_DAMAGE):
        raise ValueError("Invalid saved scarecrow score")
    if damage > best:
        records[key] = damage
        member["UserRecords"] = records
        save_profile(account, profile)
    account.db.execute(
        "UPDATE scarecrow_runs SET start_reply=NULL,finish_seq=?,damages=?,old_record=? WHERE epoch=? AND start_seq=?",
        (seq, damages, best, epoch, run[0]),
    )
    return {"OldRecord": best, "GuildMember": member}


def handle(account, route, body, epoch, seq):
    if not isinstance(body, dict) or not integer(body.get("ScarecrowId")):
        raise ValueError("Invalid scarecrow target")
    with account.db:
        account.db.execute("BEGIN IMMEDIATE")
        if account.db.execute("SELECT epoch FROM client_request_state WHERE id=1").fetchone() != (
            epoch,
        ):
            raise ValueError("Scarecrow request belongs to a previous login")
        profile = account.profile()
        member = saved_member(profile)
        if member is None:
            raise ValueError("Guild Castle requires guild membership")
        if route == START:
            return start(account, profile, body, epoch, seq)
        if route == FINISH:
            return finish(account, profile, member, body, epoch, seq)
        raise ValueError("Unsupported scarecrow operation")
