# SPDX-License-Identifier: Apache-2.0
"""Offline, backed-up grants and removal of optional fixed-stat test pins."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from guardian_tales.accounts.snapshots import is_imported
from guardian_tales.content.reference import ReferenceData
from guardian_tales.inventory.item_sell import EQUIPMENT_FIELDS, protected_ids
from guardian_tales.rewards.challenges import allocate_reward_item
from guardian_tales.runtime.state_lock import StateLock
from guardian_tales.settlement.village import integer

from .admin import MAX_USER_REVISION, validate_grant_parameters
from .test_item_static import MAX_GRANTS, TABLE, active_specs, has_grants, pin_spec, prepare

COLUMNS = (
    "operation_id,inventory_id,spec_id,defense,attack_percent,spec,reason,created_at,"
    "backup_path,removed_at,removal_backup_path"
)


@contextmanager
def account_connection(data_dir):
    database = Path(data_dir).resolve() / "server.sqlite3"
    if not database.is_file():
        raise ValueError("No existing server.sqlite3 in the selected data directory")
    with (
        StateLock(database.parent),
        closing(
            sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, isolation_level=None)
        ) as db,
    ):
        saved = db.execute("SELECT schema_version,profile FROM local_account WHERE id=1").fetchone()
        if saved is None or saved[0] != 3:
            raise ValueError("An existing schema-3 account is required; no migration was performed")
        imported = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='imported_account'"
        ).fetchone() and is_imported(db)
        if (
            not imported
            and not db.execute("SELECT 1 FROM prologue_selection WHERE id=1").fetchone()
        ):
            raise ValueError(
                "Complete the prologue or import an account before granting test items"
            )
        profile = json.loads(saved[1])
        if not integer(profile["User"].get("Id"), minimum=1) or not integer(
            profile["User"].get("Cas"), MAX_USER_REVISION
        ):
            raise ValueError("Invalid saved owner or revision")
        try:
            yield database, db, saved[1], profile
        finally:
            if db.in_transaction:
                db.execute("ROLLBACK")


def receipt(db, operation_id):
    if not has_grants(db):
        return None
    row = db.execute(
        f"SELECT {COLUMNS} FROM {TABLE} WHERE operation_id=?", (operation_id,)
    ).fetchone()
    return dict(zip(COLUMNS.split(","), row)) if row else None


def response(value, profile, result):
    return {
        "result": result,
        **{k: v for k, v in value.items() if k != "spec"},
        "present": any(
            r["Id"] == value["inventory_id"] and r["ItemId"] == value["spec_id"]
            for r in profile["User"]["ItemWeapons"]
        ),
    }


def backup_and_begin(database, db, original, action, *, label="test-pin"):
    if json.loads(original)["User"]["Cas"] == MAX_USER_REVISION:
        raise ValueError("User revision cannot be incremented")
    directory = database.parent / "backups"
    directory.mkdir(exist_ok=True)
    path = directory / (
        f"before-{label}-{action}-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
        + ".sqlite3"
    )
    with closing(sqlite3.connect(path)) as target:
        db.backup(target)
        if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Test-pin backup failed SQLite integrity checking")
    with path.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    path.with_suffix(".sqlite3.sha256").write_text(checksum + "\n", encoding="ascii")
    db.execute("BEGIN IMMEDIATE")
    if db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0] != original:
        raise ValueError("The account changed during backup; no test-item update was applied")
    return str(path)


def save_profile(db, profile):
    profile["User"]["Cas"] += 1
    db.execute(
        "UPDATE local_account SET profile=? WHERE id=1",
        (json.dumps(profile, separators=(",", ":")),),
    )


def grant_test_pin(data_dir, reference_dir, operation_id, reason, defense=10000, attack_percent=0):
    reason = validate_grant_parameters(defense, operation_id, reason, 10000)
    if not integer(attack_percent, 1000):
        raise ValueError("Attack percent must be an integer between 0 and 1000")
    with account_connection(data_dir) as (database, db, original, profile):
        previous = receipt(db, operation_id)
        if previous is not None:
            if (previous["defense"], previous["attack_percent"], previous["reason"]) != (
                defense,
                attack_percent,
                reason,
            ):
                raise ValueError("Operation ID was already used with different test-pin parameters")
            return response(previous, profile, "already_applied")
        used = [r[0] for r in db.execute(f"SELECT spec_id FROM {TABLE}")] if has_grants(db) else []
        if len(used) >= MAX_GRANTS:
            raise ValueError("The account has reached its test-pin grant limit")
        body = ReferenceData(reference_dir).read_bytes("static_data_get.bin")
        user = profile["User"]
        occupied = used + [
            r["ItemId"]
            for kind in ("ItemWeapons", "ItemMiscs", "ItemStackables")
            for r in user[kind]
        ]
        spec = pin_spec(body, occupied, defense, attack_percent)
        encoded = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
        # Prove the new definition can be serialized before touching the account.
        prepare(body, (*active_specs(db), encoded))
        row = allocate_reward_item(user, spec["Id"])
        row["Locked"] = True
        if attack_percent:
            row["Options"] = [dict(OptionId=10, Level=attack_percent, Locked=True, OptionSource=0)]
        user["ItemWeapons"].append(row)
        backup = backup_and_begin(database, db, original, "grant")
        db.execute(
            f"CREATE TABLE IF NOT EXISTS {TABLE} (operation_id TEXT PRIMARY KEY, "
            "inventory_id INTEGER NOT NULL UNIQUE, spec_id INTEGER NOT NULL UNIQUE, "
            "defense INTEGER NOT NULL, attack_percent INTEGER NOT NULL, spec TEXT NOT NULL, "
            "reason TEXT NOT NULL, created_at TEXT NOT NULL, backup_path TEXT NOT NULL, "
            "removed_at TEXT, removal_backup_path TEXT)"
        )
        value = dict(
            operation_id=operation_id,
            inventory_id=row["Id"],
            spec_id=spec["Id"],
            defense=defense,
            attack_percent=attack_percent,
            spec=encoded,
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
        return response(value, profile, "applied")


def remove_test_pin(data_dir, operation_id):
    validate_grant_parameters(1, operation_id, "Remove test pin", 1)
    with account_connection(data_dir) as (database, db, original, profile):
        value = receipt(db, operation_id)
        if value is None:
            raise ValueError("No test-pin grant exists for this operation ID")
        user = profile["User"]
        rows = [r for r in user["ItemWeapons"] if r["Id"] == value["inventory_id"]]
        if value["removed_at"] is not None:
            if rows:
                raise ValueError("A removed test pin unexpectedly exists again")
            return response(value, profile, "already_removed")
        if (
            len(rows) > 1
            or rows
            and (rows[0]["ItemId"] != value["spec_id"] or rows[0]["Amount"] != 1)
        ):
            raise ValueError("The generated inventory ID no longer matches its test pin")
        if rows:
            if rows[0].get("JewelSlots") and any(rows[0]["JewelSlots"]):
                raise ValueError("Remove socketed jewels before retiring this test pin")
            if value["inventory_id"] in protected_ids(db, user):
                raise ValueError(
                    "Remove the test pin from presets and Training Room before retiring it"
                )
            user["ItemWeapons"].remove(rows[0])
            for character in user["Characters"]:
                for field in EQUIPMENT_FIELDS:
                    if character.get(field) == value["inventory_id"]:
                        character[field] = None
        backup = backup_and_begin(database, db, original, "remove")
        if rows:
            save_profile(db, profile)
        for table in ("weapon_option_proposals", "relic_option_proposals"):
            db.execute(f"DELETE FROM {table} WHERE item_id=?", (value["inventory_id"],))
        value["removed_at"] = datetime.now(timezone.utc).isoformat()
        value["removal_backup_path"] = backup
        db.execute(
            f"UPDATE {TABLE} SET removed_at=?,removal_backup_path=? WHERE operation_id=?",
            (value["removed_at"], backup, operation_id),
        )
        db.execute("COMMIT")
        return response(value, profile, "removed")


def test_pin_history(data_dir, limit=20):
    if not integer(limit, 1000, 1):
        raise ValueError("History limit must be between 1 and 1000")
    database = Path(data_dir).resolve() / "server.sqlite3"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        if not has_grants(db):
            return []
        rows = db.execute(
            f"SELECT {COLUMNS} FROM {TABLE} ORDER BY rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        profile = json.loads(
            db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
        )
        return [response(dict(zip(COLUMNS.split(","), row)), profile, "recorded") for row in rows]
