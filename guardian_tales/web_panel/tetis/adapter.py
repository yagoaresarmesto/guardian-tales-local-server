# SPDX-License-Identifier: Apache-2.0
"""Read and edit the same per-season Tetis progression as the local game."""

import hashlib
import json
import sqlite3
from contextlib import closing
from functools import cached_property

from ... import tetis_progress
from ...panel_common.labels import english_labels
from ...raid_static import decode, records
from ..artwork import TETIS


class TetisChanged(ValueError):
    pass


class TetisEditor:
    def __init__(self, references, database):
        self.references = references
        self.database = database.resolve() if database is not None else None
        self.labels = None

    @cached_property
    def catalog_and_hash(self):
        body = self.references.read_bytes("static_data_get.bin")
        return tetis_progress.catalog(records(decode(body))[1]), hashlib.sha256(body).hexdigest()

    def connect(self, *, writable=False):
        if self.database is None:
            raise ValueError("Open the Tetis page from the running local backend to edit its save.")
        return sqlite3.connect(
            self.database.as_uri() + ("?mode=rw" if writable else "?mode=ro"), uri=True
        )

    @staticmethod
    def revision(season, loadout):
        return hashlib.sha256(json.dumps([season, loadout], sort_keys=True).encode()).hexdigest()

    def state(self):
        catalog, checksum = self.catalog_and_hash
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            data = tetis_progress.editor_view(db, catalog)
        for season in data["seasons"]:
            season["revision"] = self.revision(season, data["loadout"])
        if self.labels is None:
            keys = {season["title"] for season in data["seasons"]}
            for season in data["seasons"]:
                for node in season["nodes"]:
                    keys.update((node["name"], node["categoryName"], node["description"]))
            for items in ("spells", "artifacts"):
                keys.update(row["name"] for row in data["loadout"][items])
            self.labels = english_labels(self.references, checksum, {key for key in keys if key})
        return {**data, "labels": self.labels, "hasArt": TETIS.available(self.references)}

    def apply(self, body):
        if not isinstance(body, dict) or not isinstance(body.get("revision"), str):
            raise ValueError("Reload the current season before applying changes.")
        catalog, _ = self.catalog_and_hash
        with closing(self.connect(writable=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            state = tetis_progress.editor_view(db, catalog)
            season = next((s for s in state["seasons"] if s["id"] == body.get("seasonId")), None)
            if season is None:
                raise ValueError("Choose a Tetis season from the catalog.")
            if body["revision"] != self.revision(season, state["loadout"]):
                raise TetisChanged("Tetis progression changed. Reload this season before saving.")
            tetis_progress.edit_progress(
                db, catalog, {k: v for k, v in body.items() if k != "revision"}
            )
