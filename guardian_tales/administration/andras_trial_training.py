# SPDX-License-Identifier: Apache-2.0
"""Keep experimental hero experience in a sidecar, outside the saved account."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from guardian_tales.campaigns.campaign import FIRST_STAGE_ID, STAGE_CLEARED
from guardian_tales.heroes.imported_training import load_catalog
from guardian_tales.settlement.village import MAX_REVISION, integer

from .andras_trial_static import SOURCE

FILENAME = "andras-myth-trial.sqlite3"


def state_path(db):
    filename = next(row[2] for row in db.execute("PRAGMA database_list") if row[1] == "main")
    if not filename:
        raise ValueError("Andras trial experience requires a file-backed account")
    return Path(filename).with_name(FILENAME)


def context(store, selection):
    profile = store.account.profile()
    user = profile["User"]
    heroes = [
        r
        for r in user["Characters"]
        if r["Id"] == selection["inventory_id"] and r["CharacterId"] == SOURCE
    ]
    if (
        user["Id"] != selection["owner_id"]
        or len(heroes) != 1
        or not integer(heroes[0].get("Experience"))
    ):
        raise ValueError("Invalid original Andras for experimental training")
    hero = heroes[0]
    binding = hashlib.sha256(
        json.dumps(
            [
                selection["owner_id"],
                selection["inventory_id"],
                selection["source_sha256"],
                hero["Experience"],
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return profile, hero, binding


def read_state(db, binding, base_experience):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1):
        raise ValueError("Unsupported Andras trial experience schema")
    table = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='progress'"
    ).fetchone()
    row = (
        db.execute(
            "SELECT experience,revision FROM progress WHERE binding=?", (binding,)
        ).fetchone()
        if table
        else None
    )
    if row is None:
        return base_experience, 0
    experience, revision = row
    if not integer(experience, minimum=base_experience) or not integer(revision, MAX_REVISION, 1):
        raise ValueError("Invalid stored Andras trial experience")
    return experience, revision


def current(store, selection):
    _, hero, binding = context(store, selection)
    path = state_path(store.db)
    if not path.exists():
        return hero["Experience"], 0
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as trial:
            trial.execute("PRAGMA query_only=ON")
            return read_state(trial, binding, hero["Experience"])
    except sqlite3.Error as error:
        raise ValueError("Cannot read the separate Andras trial progress") from error


def targets_trial(request, selection):
    return (
        isinstance(request, dict)
        and isinstance(request.get("Experiences"), dict)
        and str(selection["inventory_id"]) in request["Experiences"]
    )


def maximum_experience(store, profile, hero):
    if not profile["UserProgress"]["StageStates"].get(str(FIRST_STAGE_ID), 0) & STAGE_CLEARED:
        raise ValueError("Complete Inn before training the Andras trial")
    catalog = load_catalog(store.references)
    if (
        hero["CharacterId"] not in catalog["character_ids"]
        or not integer(hero.get("LimitBreaks"), catalog["max_limit_breaks"])
        or not integer(hero.get("BlessLevel"), catalog["max_bless_level"])
    ):
        raise ValueError("Invalid original Andras training state")
    cap = catalog["caps"][0]["max_level"]
    for row in catalog["caps"][1:]:
        if profile["UserProgress"]["StageStates"].get(str(row["opened_stage_id"]), 0) & 1:
            cap = row["max_level"]
    cap += (
        hero["LimitBreaks"] * catalog["limit_break_coefficient"]
        + hero["BlessLevel"] * catalog["blessing_coefficient"]
        + catalog["myth_coefficient"]
    )
    if cap >= len(catalog["experience_by_level"]):
        raise ValueError("Andras trial level cap exceeds the supplied experience table")
    return catalog["experience_by_level"][cap]


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS progress (binding TEXT PRIMARY KEY,experience INTEGER NOT NULL,revision INTEGER NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS requests (operation_id TEXT PRIMARY KEY,binding TEXT NOT NULL,request TEXT NOT NULL)"
    )
    db.execute("PRAGMA user_version=1")


def train(store, selection, request, operation_id):
    key = str(selection["inventory_id"])
    if (
        not isinstance(request, dict)
        or set(request) != {"Experiences"}
        or not isinstance(request["Experiences"], dict)
        or set(request["Experiences"]) != {key}
        or not integer(request["Experiences"][key], minimum=1)
    ):
        raise ValueError(
            "Trial experience requests must contain only Andras and a positive integer delta"
        )
    if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 200:
        raise ValueError("Invalid Andras trial training identity")
    profile, hero, binding = context(store, selection)
    maximum = maximum_experience(store, profile, hero)
    delta = request["Experiences"][key]
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
    # A first invalid request must not create even an empty sidecar file.
    if hero["Experience"] + delta > maximum:
        raise ValueError("Andras trial experience exceeds her Myth level cap")
    path = state_path(store.db)
    try:
        with closing(sqlite3.connect(path, isolation_level=None)) as trial:
            trial.execute("BEGIN IMMEDIATE")
            try:
                experience, revision = read_state(trial, binding, hero["Experience"])
                create_tables(trial)
                receipt = trial.execute(
                    "SELECT binding,request FROM requests WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if receipt is not None:
                    if receipt != (binding, encoded):
                        raise ValueError(
                            "Andras trial training identity was already used differently"
                        )
                else:
                    if experience + delta > maximum:
                        raise ValueError("Andras trial experience exceeds her Myth level cap")
                    if (
                        not integer(profile["User"].get("Cas"), MAX_REVISION)
                        or revision >= MAX_REVISION - profile["User"]["Cas"]
                    ):
                        raise ValueError("Andras trial resource revision exceeds the native range")
                    trial.execute(
                        "INSERT INTO progress VALUES(?,?,?) ON CONFLICT(binding) DO UPDATE SET experience=excluded.experience,revision=excluded.revision",
                        (binding, experience + delta, revision + 1),
                    )
                    trial.execute(
                        "INSERT INTO requests VALUES(?,?,?)", (operation_id, binding, encoded)
                    )
                trial.execute("COMMIT")
            except BaseException:
                trial.execute("ROLLBACK")
                raise
    except sqlite3.Error as error:
        raise ValueError("Cannot save the separate Andras trial experience") from error
    return {"User": profile["User"], "UserRecord": profile["UserRecord"]}
