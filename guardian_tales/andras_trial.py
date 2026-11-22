# SPDX-License-Identifier: Apache-2.0
"""Opt-in response-only Andras Myth trial; the stored hero remains untouched."""

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from .andras_trial_static import SOURCE, VARIANT, definitions, prepare
from .reference import ReferenceData
from .village import integer

SELECTION = "andras_myth_trial.json"


def load(references):
    path = references.directory / SELECTION
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 2048:
        raise ValueError("Invalid Andras trial configuration file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or set(value)
        != {"version", "active", "generation", "owner_id", "inventory_id", "source_sha256"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or type(value["active"]) is not bool
        or any(
            not integer(value[key], minimum=1) for key in ("generation", "owner_id", "inventory_id")
        )
        or not isinstance(value["source_sha256"], str)
        or len(value["source_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in value["source_sha256"])
    ):
        raise ValueError("Invalid Andras trial configuration")
    return value


def saved_target(db, selection=None):
    row = db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Andras trial requires an existing account")
    profile = json.loads(row[0])
    user = profile["User"]
    heroes = [r for r in user["Characters"] if r.get("CharacterId") == SOURCE]
    if selection is not None:
        heroes = [r for r in heroes if r["Id"] == selection["inventory_id"]]
    if (
        len(heroes) != 1
        or not integer(user.get("Id"), minimum=1)
        or not integer(heroes[0].get("Id"), minimum=1)
    ):
        raise ValueError("Exactly one owned five-star Andras is required")
    if selection is not None and user["Id"] != selection["owner_id"]:
        raise ValueError("Andras trial belongs to a different saved account")
    return user["Id"], heroes[0]["Id"]


def validate_active(store, selection):
    saved_target(store.db, selection)
    body = store.references.read_bytes("static_data_get.bin")
    if hashlib.sha256(body).hexdigest() != selection["source_sha256"]:
        raise ValueError(
            "Andras trial content changed; disable the trial before using another pack"
        )
    definitions(body)


def project_response(reply, selection, store=None):
    if reply.body_type != 1:
        return reply
    experience, revision = None, 0
    if store is not None:
        from .andras_trial_training import current

        experience, revision = current(store, selection)
    if b'"Characters"' not in reply.body and not revision:
        return reply
    value = json.loads(reply.body)
    changed = False

    def visit(node, resource=None):
        nonlocal changed
        if isinstance(node, dict):
            if (
                resource == "User"
                and node.get("Id", selection["owner_id"]) == selection["owner_id"]
                and "Cas" in node
                and revision
            ):
                if not integer(node["Cas"], 0x7FFFFFFFFFFFFFFF - revision):
                    raise ValueError("Andras trial resource revision exceeds the native range")
                node["Cas"] += revision
                changed = True
            characters = node.get("Characters")
            if (
                isinstance(characters, list)
                and node.get("Id", selection["owner_id"]) == selection["owner_id"]
            ):
                for hero in characters:
                    if (
                        isinstance(hero, dict)
                        and type(hero.get("Id")) is int
                        and hero["Id"] == selection["inventory_id"]
                        and hero.get("CharacterId", SOURCE) == SOURCE
                    ):
                        if "CharacterId" in hero:
                            hero["CharacterId"] = VARIANT
                            changed = True
                        if experience is not None and "Experience" in hero:
                            hero["Experience"] = experience
                            changed = True
            for key, child in node.items():
                visit(child, key)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    if not changed:
        return reply
    return replace(
        reply,
        body=json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(),
    )


def bootstrap_seed(references, filename, request, parent):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return parent(references, filename, request)
    selection = load(references)
    if selection is None:
        return parent(references, filename, request)
    body, checksum = prepare(
        parent(references, "static_data_get.bin", request),
        selection["generation"],
        selection["active"],
    )
    if filename == "static_data_get.bin":
        return body
    return json.dumps(
        {
            "UpToDate": isinstance(request, dict) and request.get("Checksum") == checksum,
            "Checksum": checksum,
            "QuitGameWhenStaticDataUpdateNeeded": False,
        }
    ).encode()


def publish(references, value):
    from .raid_static import atomic_replace

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=references.directory, prefix=".andras-trial-", delete=False
        ) as stream:
            temporary = stream.name
            stream.write(json.dumps(value, indent=2).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace(temporary, references.directory / SELECTION)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Enable, disable or inspect the response-only Andras Myth trial"
    )
    parser.add_argument("action", choices=("enable", "disable", "status"))
    parser.add_argument("--data-dir", default="local/state")
    parser.add_argument("--reference-dir", default="local/client-data/reference")
    args = parser.parse_args(argv)
    references = ReferenceData(args.reference_dir)
    try:
        previous = load(references)
        value = previous
        if args.action == "enable":
            database = Path(args.data_dir).resolve() / "server.sqlite3"
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
                owner, target = saved_target(db)
                assert db.total_changes == 0
            body = references.read_bytes("static_data_get.bin")
            value = dict(
                version=1,
                active=True,
                generation=(previous or {}).get("generation", 0),
                owner_id=owner,
                inventory_id=target,
                source_sha256=hashlib.sha256(body).hexdigest(),
            )
        elif args.action == "disable" and previous is not None:
            value = dict(previous, active=False)
        if args.action != "status" and value is not None and value != previous:
            value["generation"] += 1
            prepare(
                references.read_bytes("static_data_get.bin"), value["generation"], value["active"]
            )
            publish(references, value)
        print(
            json.dumps(
                {
                    "hero": "Andras",
                    "active": bool(value and value["active"]),
                    "stored_spec_id": SOURCE,
                    "trial_spec_id": VARIANT,
                    "appearance_and_skills": "original",
                    "saved_account_modified": False,
                    "restart_backend_and_game_required": args.action != "status",
                },
                indent=2,
            )
        )
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as error:
        parser.error(str(error))
