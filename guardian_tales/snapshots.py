# SPDX-License-Identifier: Apache-2.0
"""Validate and import a private account snapshot into a new local state directory."""

import argparse
import base64
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .state_lock import StateLock

FORMAT = "guardian-tales-account-snapshot"
CLIENT = {"version": "3.57.0", "version_code": 431, "region": "eu"}
MAX_SNAPSHOT = 32 * 1024 * 1024
PRESET_OVERLAYS = (
    ("party_preset_state", "UserPartyPreset2"),
    ("character_list_preset_state", "UserCharacterListPreset"),
    ("multi_party_preset_state", "UserMultiPartyPreset"),
    ("coop_expedition_slots_state", "CoopExpeditionSlots"),
)
STARTUP_READS = frozenset(
    (
        "/collection/list-all",
        "/pasture/collection-all",
        "/lobby-village/enter",
        "/preset/get-presets",
    )
)
IMPORTED_MUTATIONS = frozenset(
    (
        "/collection/claim-hero-knowledge-all",
        "/colosseum/save-formation",
        "/colosseum/set-defense-party-formation",
        "/colosseum/set-defense-party-preset",
        "/item/enhance-weapon",
        "/merch/enhance-merch/v2",
        "/item/decompose-jewel",
        "/item/inlaid-jewelslot",
        "/item/attach-jewel",
        "/item/detach-jewel",
        "/item/upgrade-jewel",
        "/item/upgrade-jewel-from-relic",
        "/item/engrave-weapon",
        "/item/extract",
        "/item/change-options",
        "/item/change-lock-options",
        "/item/change-relic-options/v2",
        "/item/apply-relic-options",
        "/item/apply-options",
        "/item/limitbreak-weapon/v2",
        "/item/lock",
        "/item/sell",
        "/item/unlock",
        "/summon/set-select-character",
        "/summon/set-select-weapon",
        "/summon/select-character",
        "/summon/select-weapon",
        "/summon/character",
        "/summon/weapon",
        "/tower-infinity/end-stage",
        "/tower-infinity/save-formation",
        "/preset/set-selected-preset",
        "/preset/set-presets",
        "/preset/set-character-list-preset",
        "/preset/delete-character-list-preset",
        "/preset/delete-preset",
        "/preset/delete-multi-party-preset",
        "/preset/set-multi-party-preset",
        "/preset/reorder-preset",
        "/user/charge-stamina",
        "/user/add-character-experience",
        "/user/bless-character",
        "/user/bless-character-all",
        "/user/recall-character-growth/v2",
        "/mission/claim-challenge-all",
        "/mission/claim-challenge-all-step",
        "/user/charge-stamina-by-gem",
        "/user/claim-daily-attendance",
        "/user/evolve-character/v2",
        "/user/expand-inventory",
        "/user/limitbreak-character/v2",
        "/user/myth-character/v2",
        "/user/open-awakening-node-all",
        "/lobby-village/harvest-all",
        "/lobby-village/harvest-basecamp",
        "/lobby-village/prepare-dispatch",
        "/lobby-village/receive-gift",
        "/lobby-village/remove-obstacle",
        "/user/guardian-mastery-level-up",
        "/user/reset-guardian-mastery-level",
        "/user/save-party-member/v2",
        "/user/change-weapons",
        "/user/change-accessory",
        "/user/change-costume",
        "/user/change-equip-costume",
        "/user/change-orb",
        "/user/change-merch",
        "/user/change-relic",
        "/user/select-representative-character",
        "/user/change-name",
        "/user/set-portrait-frame",
        "/user/mark-tutorial",
    )
)
ACCOUNT_READS = frozenset(
    (
        "/auth/fetch-account",
        "/user/get-user-profile-card",
        "/colosseum/enter",
        "/colosseum/get-opponents",
        "/colosseum/refresh-opponents",
        "/colosseum/get-my-ranking",
        "/colosseum/get-rankings",
        "/colosseum/get-battle-records",
        "/colosseum/get-battle-infos",
        "/colosseum/get-defense-party",
        "/colosseum/start-stage/v2",
        "/colosseum/end-stage/v3",
        "/my-room/enter",
        "/training-room/enter",
        # The client persists its own badge preference; the server only validates it.
        "/user/set-profile-badge",
        "/guild/list-item-request",
        "/guild/get-my-guild",
        "/guild/red-dot",
        "/guild/claim-guild-daily-attendance",
        "/guild-meteor/enter",
        "/guild-war/enter",
        "/guild-war/abandon-stage",
        "/guild-war/get-all-castle-simple-infos",
        "/guild-war/get-castle-detail-info",
        "/guild/get-guild-summary",
        "/guild-war/start-coop-stage",
        "/guild-war/end-coop-stage/v2",
        "/guild-war/start-multi-stage",
        "/guild-war/end-multi-stage/v2",
        "/guild-war/get-battle-records",
        "/guild-war/get-ranking",
        "/guild-war/get-guild-coin-ranking",
        "/user/claim-unlock-feature-rewards",
        "/guild-raid2/reset",
        "/guild-raid2/enter",
        "/guild-raid2/start-stage",
        "/guild-raid2/end-stage",
        "/guild-raid2/update-status",
        "/guild-raid2/get-battle-status",
        "/guild-raid2/get-battle-records/latest",
        "/guild-raid2/get-battle-records/boss",
        "/guild-raid2/get-battle-records/member",
        "/guild-raid2/get-guild-rankings",
        "/guild-raid2/get-member-rankings",
        "/chat/guild-history/v2",
        "/chat/listen-channel",
        "/collection/list-all",
        "/collection/list-new",
        "/heavenholdfarm/collection-all",
        "/pasture/collection-all",
        "/friend2/enter",
        "/friend2/recommend",
        "/friend2/has-changes",
        "/mission/get-user-mission",
        "/ad/init-inbox",
        "/guardian-pass/enter",
        "/festival-pass/enter",
        "/live-event/enter",
        "/user/exchange-summon-pickup-ticket",
    )
)


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS imported_account "
        "(id INTEGER PRIMARY KEY CHECK(id=1), source_sha256 TEXT NOT NULL, "
        "imported_at TEXT NOT NULL, startup_reads TEXT NOT NULL, stage_progresses TEXT NOT NULL)"
    )


def is_imported(db):
    return db.execute("SELECT 1 FROM imported_account WHERE id=1").fetchone() is not None


def preserved_read(db, route):
    row = db.execute("SELECT startup_reads FROM imported_account WHERE id=1").fetchone()
    if row is None:
        return None
    reads = json.loads(row[0])
    if route == "/collection/list-new":
        collection = reads["/collection/list-all"]["value"]
        return {
            key: collection[key] for key in ("NewItems", "NewCustomCollections", "NewItemMastery")
        }
    if route not in reads:
        return None
    value = reads[route]["value"]
    overlays = {
        "/preset/get-presets": PRESET_OVERLAYS,
        "/lobby-village/enter": (("village_state", "UserLobbyVillage"),),
    }
    for table, resource in overlays.get(route, ()):
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            current = db.execute("SELECT value FROM " + table + " WHERE id=1").fetchone()
            if current:
                value = dict(value, **{resource: json.loads(current[0])})
    return value


def validate_preserved_request(route, body):
    if body in (None, {}):
        return
    if (
        route != "/lobby-village/enter"
        or not isinstance(body, dict)
        or set(body) != {"isPartial", "lastLobbyShopUpdated"}
        or type(body["isPartial"]) is not bool
    ):
        raise ValueError("Unsupported parameters for a preserved startup read")
    # A clean installation has no shop cache. Both cache hints still receive the
    # preserved full village; they never initialize or refresh shop state.
    timestamp = body["lastLobbyShopUpdated"]
    if timestamp is None:
        return
    if not isinstance(timestamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})",
        timestamp,
    ):
        raise ValueError("Unsupported parameters for a preserved startup read")
    try:
        datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValueError("Invalid village shop cache timestamp") from error
    # These are native cache hints. This imported account returns its preserved
    # full village state with its current harvest clocks, without refreshing the shop.


def _private_field(key):
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(
        part in normalized
        for part in ("token", "password", "secret", "linkcode", "authorization", "cookie")
    ) or normalized in {
        "myuserkey",
        "sessionkey",
        "auth",
        "authentication",
        "email",
        "emailaddress",
        "phone",
        "phonenumber",
        "deviceid",
        "advertisingid",
        "signature",
    }


def _check_tree(value, depth=0):
    if depth > 64:
        raise ValueError("Snapshot nesting exceeds the supported limit")
    if isinstance(value, dict):
        for key, item in value.items():
            if _private_field(key):
                raise ValueError("Snapshot contains an excluded authentication or contact field")
            _check_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_tree(item, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Snapshot contains a non-finite number")


def _integer(value, label, minimum=0):
    if type(value) is not int or not minimum <= value <= 0x7FFFFFFFFFFFFFFF:
        raise ValueError("Invalid snapshot " + label)
    return value


def _rows(value, label):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Invalid snapshot " + label)
    ids = [_integer(row.get("Id"), label + " identifier", 1) for row in value]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate snapshot " + label + " identifiers")
    return set(ids)


def validate_snapshot(value):
    if not isinstance(value, dict) or value.get("format") != FORMAT:
        raise ValueError("Unsupported account snapshot format")
    if type(value.get("format_version")) is not int or value["format_version"] != 1:
        raise ValueError("Unsupported account snapshot version")
    if value.get("client") != CLIENT or type(value["client"].get("version_code")) is not int:
        raise ValueError("Snapshot must match the 3.57.0 European Android client")
    _check_tree(value)
    template = json.loads((Path(__file__).parent / "templates/new_guest_profile.json").read_text())
    profile = value.get("profile")
    if not isinstance(profile, dict) or set(profile) != set(template):
        raise ValueError("Snapshot must contain every expected profile section")
    for key, section in profile.items():
        if not isinstance(section, dict) and not (key == "GuildMember" and section is None):
            raise ValueError("Invalid snapshot profile section")
        if isinstance(template[key], dict) and not set(template[key]).issubset(section):
            raise ValueError("Snapshot profile section is incomplete")
    user = profile["User"]
    user_id = _integer(user.get("Id"), "account identifier", 1)
    if not isinstance(user.get("Name"), str) or not user["Name"]:
        raise ValueError("Snapshot must contain an existing character name")
    for section in profile.values():
        if isinstance(section, dict) and "UserId" in section:
            if type(section["UserId"]) is not int or section["UserId"] != user_id:
                raise ValueError("Snapshot profile identifiers do not agree")
    character_ids = _rows(user.get("Characters"), "character")
    if not character_ids:
        raise ValueError("Snapshot must contain a completed-prologue character roster")
    for hero in user["Characters"]:
        _integer(hero.get("CharacterId"), "character specification", 1)
        _integer(hero.get("Experience"), "character experience")
    assets = user.get("Assets")
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        raise ValueError("Invalid snapshot asset list")
    asset_ids = set()
    for asset in assets:
        asset_id = _integer(asset.get("Id"), "asset specification", 1)
        if asset_id in asset_ids:
            raise ValueError("Duplicate snapshot asset specifications")
        asset_ids.add(asset_id)
        _integer(asset.get("Amount"), "asset amount")
        # Preserve observed signed counters; their mutation rules are separate
        # from importing an unchanged account snapshot.
        _integer(asset.get("Spent"), "asset spending", -(1 << 63))
    item_ids = set()
    for key in ("ItemWeapons", "ItemStackables", "ItemMiscs"):
        ids = _rows(user.get(key), "inventory")
        if item_ids.intersection(ids):
            raise ValueError("Snapshot inventory identifiers overlap")
        item_ids.update(ids)
        for item in user[key]:
            _integer(item.get("ItemId"), "item specification", 1)
            _integer(item.get("Amount"), "item amount")
    if _integer(user.get("CharacterIdCounter"), "character counter") < max(character_ids):
        raise ValueError("Snapshot character counter precedes owned characters")
    if _integer(user.get("ItemIdCounter"), "inventory counter") < max(item_ids, default=0):
        raise ValueError("Snapshot inventory counter precedes owned items")
    party = user.get("Party")
    if not isinstance(party, dict) or not isinstance(party.get("Characters"), list):
        raise ValueError("Invalid snapshot party")
    for character in party["Characters"]:
        if character is not None and (type(character) is not int or character not in character_ids):
            raise ValueError("Snapshot party references an unowned character")
    for hero in user["Characters"]:
        for key in (
            "Weapon1",
            "Weapon2",
            "Accessory1",
            "Costume",
            "Orb1",
            "Orb2",
            "Merch",
            "Relic",
        ):
            reference = hero.get(key)
            if reference is not None and (type(reference) is not int or reference not in item_ids):
                raise ValueError("Snapshot equipment references an unowned item")
    reads = value.get("startup_reads")
    if not isinstance(reads, dict) or set(reads) != STARTUP_READS:
        raise ValueError("Snapshot must contain all four preserved startup reads")
    for response in reads.values():
        if (
            not isinstance(response, dict)
            or set(response) != {"body_type", "value"}
            or type(response["body_type"]) is not int
            or response["body_type"] != 1
            or not isinstance(response["value"], dict)
        ):
            raise ValueError("Invalid preserved startup response")
    collection = reads["/collection/list-all"]["value"]
    if any(
        not isinstance(collection.get(key), list)
        for key in ("NewItems", "NewCustomCollections", "NewItemMastery")
    ):
        raise ValueError("Snapshot collection is missing its new-entry lists")
    if reads["/lobby-village/enter"]["value"].get("User") not in (None, {}):
        raise ValueError("Village read contains an unapplied account delta")
    progresses = value.get("stage_progresses")
    if not isinstance(progresses, dict):
        raise ValueError("Invalid preserved stage progress map")
    for stage, encoded in progresses.items():
        if (
            not stage.isdecimal()
            or int(stage) <= 0
            or (encoded is not None and not isinstance(encoded, str))
        ):
            raise ValueError("Invalid preserved stage progress entry")
        if encoded is None:
            continue
        try:
            base64.b64decode(encoded, validate=True)
        except (ValueError, UnicodeError) as error:
            raise ValueError("Invalid preserved stage progress encoding") from error
    return value


def load_snapshot(path):
    def pairs(entries):
        result = {}
        for key, item in entries:
            if key in result:
                raise ValueError("Duplicate JSON key in account snapshot")
            result[key] = item
        return result

    def constant(value):
        raise ValueError("Non-finite JSON number in account snapshot")

    with Path(path).open("rb") as source:
        raw = source.read(MAX_SNAPSHOT + 1)
    if len(raw) > MAX_SNAPSHOT:
        raise ValueError("Account snapshot exceeds the supported size")
    try:
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant
        )
        validate_snapshot(value)
    except (UnicodeError, RecursionError, KeyError, TypeError) as error:
        raise ValueError("Invalid account snapshot structure") from error
    return value, hashlib.sha256(raw).hexdigest()


def summary(value, digest):
    user = value["profile"]["User"]
    return {
        "result": "PASS",
        "source_sha256": digest,
        "profile_sections": len(value["profile"]),
        "characters": len(user["Characters"]),
        "inventory_rows": sum(
            len(user[key]) for key in ("ItemWeapons", "ItemStackables", "ItemMiscs")
        ),
        "startup_reads": len(value["startup_reads"]),
        "preserved_stage_progresses": len(value["stage_progresses"]),
        "enabled_mutation_routes": sorted(IMPORTED_MUTATIONS),
        "scope": "Imported profile/startup reads with configured hero draws/wishlists, Orbital presets, stamina and village harvesting",
    }


def import_snapshot(path, data_dir):
    value, digest = load_snapshot(path)
    directory = Path(data_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with StateLock(directory):
        if any(item.name != ".state.lock" for item in directory.iterdir()):
            raise ValueError("Snapshot import requires an empty state directory")
        temporary = None
        db = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".snapshot-", suffix=".pending", dir=directory, delete=False
            ) as handle:
                temporary = Path(handle.name)
            db = sqlite3.connect(temporary)
            from .bootstrap import GuestStore

            GuestStore(db)
            with db:
                db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1",
                    (json.dumps(value["profile"], separators=(",", ":")),),
                )
                db.execute(
                    "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                    (
                        digest,
                        datetime.now(timezone.utc).isoformat(),
                        json.dumps(value["startup_reads"], separators=(",", ":")),
                        json.dumps(value["stage_progresses"], separators=(",", ":")),
                    ),
                )
            db.close()
            db = None
            # A hard link publishes the completed database without replacing an
            # existing file, including one created by an incompatible old server.
            os.link(temporary, directory / "server.sqlite3")
        finally:
            if db is not None:
                db.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
                Path(str(temporary) + "-journal").unlink(missing_ok=True)
    return dict(
        summary(value, digest), imported=True, network_mutations_enabled=bool(IMPORTED_MUTATIONS)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    inspect = commands.add_parser(
        "inspect", help="Validate a private snapshot without writing state"
    )
    inspect.add_argument("--input", type=Path, required=True)
    importer = commands.add_parser(
        "import", help="Import into an explicitly selected empty state directory"
    )
    importer.add_argument("--input", type=Path, required=True)
    importer.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "inspect":
            value, digest = load_snapshot(args.input)
            result = summary(value, digest)
        else:
            result = import_snapshot(args.input, args.data_dir)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        parser.exit(2, "Error: " + str(error) + "\n")
    print(json.dumps(result, indent=2))
