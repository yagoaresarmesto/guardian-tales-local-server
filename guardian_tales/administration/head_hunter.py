# SPDX-License-Identifier: Apache-2.0
"""Offline, backed-up creation/removal of additional level-150 Head Hunters."""

import argparse
import copy
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from guardian_tales.content.reference import ReferenceData
from guardian_tales.inventory.item_sell import EQUIPMENT_FIELDS, protected_ids
from guardian_tales.inventory.weapon_engrave import load_catalog as engraving_catalog
from guardian_tales.inventory.weapon_enhance import load_catalog
from guardian_tales.rewards.challenges import allocate_reward_item
from guardian_tales.settlement.village import integer

from .admin import validate_grant_parameters
from .admin_test_items import account_connection, backup_and_begin, save_profile
from .head_hunter_static import MAX_GRANTS, SOURCE, TABLE, VARIANT, prepare, weapon_spec

COLUMNS = "operation_id,inventory_id,source_item_id,owner_id,source_sha256,reason,created_at,backup_path,removed_at,removal_backup_path"


def exists(db):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone()


def receipt(db, operation_id):
    if not exists(db):
        return None
    row = db.execute(
        f"SELECT {COLUMNS} FROM {TABLE} WHERE operation_id=?", (operation_id,)
    ).fetchone()
    return dict(zip(COLUMNS.split(","), row)) if row else None


def result(value, profile, status):
    return {
        "result": status,
        **value,
        "spec_id": VARIANT,
        "visible_level": 150,
        "four_crystal_bonus_percent": 25,
        "present": any(
            r["Id"] == value["inventory_id"] and r["ItemId"] == VARIANT
            for r in profile["User"]["ItemWeapons"]
        ),
    }


def grant(data_dir, reference_dir, operation_id, reason, source_item_id=None):
    reason = validate_grant_parameters(1, operation_id, reason, 1)
    if source_item_id is not None and not integer(source_item_id, minimum=1):
        raise ValueError("Source item must identify one owned original Head Hunter")
    references = ReferenceData(reference_dir)
    with account_connection(data_dir) as (database, db, original, profile):
        previous = receipt(db, operation_id)
        if previous:
            if previous["owner_id"] != profile["User"]["Id"]:
                raise ValueError("Head Hunter grant belongs to another saved owner")
            if (
                previous["reason"] != reason
                or source_item_id is not None
                and previous["source_item_id"] != source_item_id
            ):
                raise ValueError("Operation ID was used with different Head Hunter parameters")
            return result(previous, profile, "already_applied")
        count = db.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] if exists(db) else 0
        if count >= MAX_GRANTS:
            raise ValueError("Head Hunter grant history has reached its bounded limit")
        body = references.read_bytes("static_data_get.bin")
        spec = weapon_spec(body)
        prepare(body, spec)
        user = profile["User"]
        sources = [
            r
            for r in user["ItemWeapons"]
            if r.get("ItemId") == SOURCE and (source_item_id is None or r["Id"] == source_item_id)
        ]
        if len(sources) != 1:
            raise ValueError("Select exactly one owned original Head Hunter with --source-item-id")
        source = sources[0]
        definition = json.loads(spec)
        engraving = source.get("EngraveOptions")
        tiers = definition.get("EngraveRandomOptions", [])
        if (
            not integer(source.get("Amount"), 1, 1)
            or not integer(source.get("Id"), minimum=1)
            or not integer(source.get("Experience"))
            or source.get("LimitBreaks") != 5
            or not integer(source.get("EngraveCeiling"), 5, 1)
            or not isinstance(engraving, list)
            or len(engraving) != 1
            or not isinstance(engraving[0], dict)
            or not any(
                all(engraving[0].get(k) == t.get(k) for k in ("OptionId", "Level")) for t in tiers
            )
            or source.get("JewelSlots") is not None
            and (not isinstance(source["JewelSlots"], list) or any(source["JewelSlots"]))
        ):
            raise ValueError(
                "Use a fully limit-broken, engraved Head Hunter without socketed jewels"
            )
        catalog = load_catalog(references)
        engraving_data = engraving_catalog(references)
        if (
            engraving_data["engrave_coef"] != 15
            or engraving_data["required_limit_breaks"] != 5
            or engraving_data["weapons"].get(str(SOURCE), {}).get("options")
            != [{k: tier[k] for k in ("OptionId", "Level")} for tier in tiers]
        ):
            raise ValueError("Head Hunter requires the matching native engraving catalog")
        cap = user.get("Unlocked", {}).get("MaxLevel", {}).get("Weapon")
        if (
            not integer(cap, 999, 1)
            or catalog["limit_break_coef"] != 3
            or catalog["myth_coef"] != 20
            or catalog["max_limit_breaks"] != 5
            or catalog["weapons"].get(str(SOURCE)) != 4
            or len(catalog["level_total_exps"]) < 149
            or cap + 15 + 15 + 20 < 149
        ):
            raise ValueError(
                "The matching weapon/story level catalog must support visible level 150"
            )
        row = copy.deepcopy(source)
        allocated = allocate_reward_item(user, VARIANT)
        row.update(
            Id=allocated["Id"],
            ItemId=VARIANT,
            Experience=catalog["level_total_exps"][148],
            Locked=True,
        )
        user["ItemWeapons"].append(row)
        backup = backup_and_begin(database, db, original, "grant", label="head-hunter")
        db.execute(
            f"CREATE TABLE IF NOT EXISTS {TABLE} (operation_id TEXT PRIMARY KEY, inventory_id INTEGER NOT NULL UNIQUE, source_item_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, source_sha256 TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, backup_path TEXT NOT NULL, removed_at TEXT, removal_backup_path TEXT)"
        )
        value = dict(
            operation_id=operation_id,
            inventory_id=row["Id"],
            source_item_id=source["Id"],
            owner_id=user["Id"],
            source_sha256=hashlib.sha256(body).hexdigest(),
            reason=reason,
            created_at=datetime.now(timezone.utc).isoformat(),
            backup_path=backup,
            removed_at=None,
            removal_backup_path=None,
        )
        save_profile(db, profile)
        db.execute(
            f"INSERT INTO {TABLE} VALUES({','.join('?' for _ in value)})", tuple(value.values())
        )
        db.execute("COMMIT")
        return result(value, profile, "applied")


def remove(data_dir, operation_id):
    validate_grant_parameters(1, operation_id, "Remove Head Hunter trial", 1)
    with account_connection(data_dir) as (database, db, original, profile):
        value = receipt(db, operation_id)
        if value is None:
            raise ValueError("No Head Hunter grant exists for this operation ID")
        user = profile["User"]
        if value["owner_id"] != user["Id"]:
            raise ValueError("Head Hunter grant belongs to another saved owner")
        rows = [r for r in user["ItemWeapons"] if r["Id"] == value["inventory_id"]]
        if value["removed_at"] is not None:
            if rows:
                raise ValueError("A retired Head Hunter unexpectedly exists again")
            return result(value, profile, "already_removed")
        if (
            len(rows) > 1
            or rows
            and (rows[0].get("ItemId") != VARIANT or rows[0].get("Amount") != 1)
        ):
            raise ValueError("The generated ID no longer identifies its trial Head Hunter")
        if rows:
            if rows[0].get("JewelSlots") and any(rows[0]["JewelSlots"]):
                raise ValueError("Remove socketed jewels before retiring the trial weapon")
            if value["inventory_id"] in protected_ids(db, user):
                raise ValueError("Remove this trial weapon from presets and Training Room first")
            user["ItemWeapons"].remove(rows[0])
            for hero in user["Characters"]:
                for field in EQUIPMENT_FIELDS:
                    if hero.get(field) == value["inventory_id"]:
                        hero[field] = None
        backup = backup_and_begin(database, db, original, "remove", label="head-hunter")
        if rows:
            save_profile(db, profile)
        for table in ("weapon_option_proposals", "relic_option_proposals"):
            db.execute(f"DELETE FROM {table} WHERE item_id=?", (value["inventory_id"],))
        value.update(removed_at=datetime.now(timezone.utc).isoformat(), removal_backup_path=backup)
        db.execute(
            f"UPDATE {TABLE} SET removed_at=?,removal_backup_path=? WHERE operation_id=?",
            (value["removed_at"], backup, operation_id),
        )
        db.execute("COMMIT")
        return result(value, profile, "removed")


def history(data_dir):
    database = Path(data_dir).resolve() / "server.sqlite3"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        if not exists(db):
            return []
        profile = json.loads(
            db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
        )
        return [
            result(dict(zip(COLUMNS.split(","), row)), profile, "recorded")
            for row in db.execute(f"SELECT {COLUMNS} FROM {TABLE} ORDER BY rowid DESC")
        ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("grant", "remove", "list"))
    parser.add_argument("--data-dir", type=Path, default=Path("local/state"))
    parser.add_argument("--reference-dir", type=Path, default=Path("local/client-data/reference"))
    parser.add_argument("--operation-id")
    parser.add_argument("--source-item-id", type=int)
    parser.add_argument("--reason", default="Experimental Head Hunter Myth copy")
    args = parser.parse_args(argv)
    try:
        if args.action == "grant":
            value = grant(
                args.data_dir,
                args.reference_dir,
                args.operation_id,
                args.reason,
                args.source_item_id,
            )
        elif args.action == "remove":
            value = remove(args.data_dir, args.operation_id)
        else:
            value = history(args.data_dir)
        print(json.dumps(value, indent=2))
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        parser.exit(2, str(error) + "\n")
