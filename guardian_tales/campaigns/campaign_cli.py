# SPDX-License-Identifier: Apache-2.0
"""Preview or apply a backed-up main-story completion to the local test account."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from guardian_tales.administration.admin_test_items import account_connection, backup_and_begin
from guardian_tales.content.reference import ReferenceData

from .campaign_complete import complete_campaign


def preview(source, refs):
    with closing(sqlite3.connect(":memory:")) as trial:
        source.backup(trial)
        with trial:
            result = complete_campaign(trial, refs)
        if trial.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Completed test copy failed SQLite integrity checking")
        return result, bool(trial.total_changes)


def run(data_dir, reference_dir, apply):
    refs = ReferenceData(reference_dir)
    if not apply:
        database = Path(data_dir).resolve() / "server.sqlite3"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            result, changed = preview(source, refs)
        return {"result": "preview", "would_change": changed, **result}

    with account_connection(data_dir) as (database, db, original, _):
        result, changed = preview(db, refs)
        if not changed:
            return {"result": "already_complete", **result}
        backup = backup_and_begin(database, db, original, "complete", label="campaign")
        result = complete_campaign(db, refs)
        if not db.in_transaction:
            raise RuntimeError("Campaign completion lost its transaction")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Completed save failed SQLite integrity checking")
        db.commit()
    return {"result": "applied", "backup": backup, **result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "complete"))
    parser.add_argument("--data-dir", type=Path, default=Path("local/state"))
    parser.add_argument("--reference-dir", type=Path, default=Path("local/client-data/reference"))
    args = parser.parse_args(argv)
    try:
        result = run(args.data_dir, args.reference_dir, args.action == "complete")
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps(result, indent=2))
