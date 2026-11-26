# SPDX-License-Identifier: Apache-2.0
"""Shared read snapshots and exclusive, offline writes for the working game save."""

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager

from guardian_tales.state_lock import StateLock
from guardian_tales.village import MAX_REVISION, integer


class GameSaveEditor:
    def __init__(self, database):
        self.database = database.resolve()

    def status(self):
        try:
            with StateLock(self.database.parent):
                return {"writable": True}
        except RuntimeError:
            return {"writable": False}

    @contextmanager
    def reader(self):
        with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("BEGIN")
            yield db

    @staticmethod
    def pending_items(db, table):
        # A save imported before the first backend start has no proposal tables.
        queries = {
            "weapon_option_proposals": "SELECT item_id FROM weapon_option_proposals",
            "relic_option_proposals": "SELECT item_id FROM relic_option_proposals",
        }
        query = queries[table]
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            return set()
        return {row[0] for row in db.execute(query)}

    @staticmethod
    def profile(db):
        saved = db.execute(
            "SELECT schema_version, profile FROM local_account WHERE id=1"
        ).fetchone()
        if not saved or saved[0] != 3:
            raise ValueError("The game save requires an existing schema-3 account.")
        profile = json.loads(saved[1])
        user = profile["User"]
        if not integer(user.get("Id"), minimum=1) or not integer(user.get("Cas"), MAX_REVISION):
            raise ValueError("The game save has an invalid owner or revision.")
        return profile

    @staticmethod
    def inventory_version(user):
        return f"{user['Id']}:{user['Cas']}"

    @staticmethod
    def option_version(user, item, *fields):
        values = [user["Id"], item["Id"], item["ItemId"], *(item.get(field) for field in fields)]
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def write(self, body):
        try:
            lock = StateLock(self.database.parent).acquire()
        except RuntimeError:
            return 423, {
                "error": "The game save is in use. Stop the backend before applying changes."
            }
        try:
            with closing(sqlite3.connect(self.database.as_uri() + "?mode=rw", uri=True)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                return self.apply_locked(db, body)
        finally:
            lock.release()
