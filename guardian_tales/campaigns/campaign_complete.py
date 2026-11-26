# SPDX-License-Identifier: Apache-2.0
"""Prepare a completed, replayable campaign using the installed build's data."""

import base64
import json
import struct
from collections import defaultdict

from guardian_tales.modes.guild.raid_static import decode, records

from .campaign import STAGE_CLEARED, STAGE_OPENED, STAGE_UNLOCKED
from .story_data import parse
from .story_handles import stage_handles


def campaign_test_enabled(db):
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_test_state'"
    ).fetchone()
    return bool(exists and db.execute("SELECT 1 FROM campaign_test_state WHERE id=1").fetchone())


def decode_progress(encoded):
    """Read native v2 stores without changing saved integer puzzles or the board count."""
    if not encoded:
        return {}, 0
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) < 3 or raw[0] != 2:
        raise ValueError("Unsupported imported stage progress version")
    offset = 2

    def take(count):
        nonlocal offset
        end = offset + count
        if end > len(raw):
            raise ValueError("Truncated imported stage progress")
        value = raw[offset:end]
        offset = end
        return value

    stores = {}
    for _ in range(raw[1]):
        category, size = take(2)
        if not 1 <= category <= 11 or category in stores:
            raise ValueError("Invalid imported story progress store")
        bits = take((size + 7) // 8)
        values = {i: True for i in range(size) if bits[i // 8] & (1 << (i % 8))}
        if size:
            values.setdefault(size - 1, False)  # Retain the original bitmap extent.
        for _ in range(take(1)[0]):
            key, value = struct.unpack("<Bi", take(5))
            if key >= size:
                raise ValueError("Integer lies outside the imported story bitmap")
            values[key] = value
        stores[category] = values
    stones = take(1)[0]
    if offset != len(raw) or stones > 3:
        raise ValueError("Unexpected trailing imported story progress")
    return stores, stones


def complete_quests(progress, specs, checkpoints):
    existing = {q["Id"]: q for q in progress["QuestProgresses"]}
    if len(existing) != len(progress["QuestProgresses"]):
        raise ValueError("Duplicate saved quest ID")
    for quest_id, spec in specs.items():
        quest = existing.get(quest_id)
        if quest is None:
            quest = {"Id": quest_id, "InnerProgress": 0, "Grade": -1, "CustomStates": {}}
            progress["QuestProgresses"].append(quest)
        if quest["Grade"] >= 0:
            continue  # Preserve the player's recorded ending and its checkpoint.
        grades = spec["EndingGrades"]
        if not grades or any(type(grade) is not int or grade < 0 for grade in grades):
            raise ValueError("Missing valid ending for campaign quest")
        quest["Grade"] = min(grades)
        quest["InnerProgress"] = max(quest["InnerProgress"], checkpoints.get(quest_id, 0))


def catalog(references):
    body = references.read_bytes("static_data_get.bin")
    chapters, stages, linked = parse(body)
    _, tables = records(decode(body))
    if not chapters or not stages or not linked:
        raise ValueError("Main story chapter, stage and quest specifications are required")

    def table(name):
        return json.loads(tables[name][1])

    # Hidden chapter quests can be absent from every individual stage's Quests list.
    specs = {
        q["Id"]: q
        for q in table("quests")
        if q["Id"] in linked or 10000 + q.get("Chapter", 0) in chapters
    }
    checkpoints = defaultdict(int)
    for row in table("questtargetstage"):
        key = row["QuestId"]
        checkpoints[key] = max(checkpoints[key], row["Progress"])
    for key, spec in specs.items():
        for field in ("ProgressOpenStages", "ProgressRewards"):
            for step in spec.get(field) or {}:
                checkpoints[key] = max(checkpoints[key], int(step))
    followers = {
        row["Id"] for row in table("followers")["Followers"] if str(row["StageId"]) in stages
    }
    # A board with an empty reward list still has three sockets.
    boards = {name for name, row in table("stagemetaitem").items() if "StoneBoardItems" in row}
    handles = {row["tilemap"]: stage_handles(references, int(key)) for key, row in stages.items()}
    return chapters, stages, specs, checkpoints, followers, boards, handles


def prepare_stages(db, profile, chapters, stages, boards, handles, cache):
    states = profile["UserProgress"]["StageStates"]
    totals = {"purple_coins": 0, "star_pieces": 0, "stone_boards": 0}
    initial_rows = []
    pickup_rows = []
    for chapter, keys in chapters.items():
        count = {2: 0, 3: 0}
        for key in keys:
            stage_id = int(key)
            name = stages[key]["tilemap"]
            row = handles.get(name)
            if not isinstance(row, dict) or not {"2", "3", "4", "5"} <= row.keys():
                raise ValueError(f"Missing collectible handles for story tilemap {name}")
            flags = STAGE_OPENED | STAGE_UNLOCKED | STAGE_CLEARED
            if stage_id // 10000 == chapter:
                # Hell counts challenges A/B, Normal and Nightmare count coin/star collection.
                flags |= (1 << 9 | 1 << 10) if chapter // 100 == 102 else (1 << 3 | 1 << 4)
            states[key] = states.get(key, 0) | flags
            stores, stones = decode_progress(cache.get(key))
            for category, values in stores.items():
                initial_rows.extend(
                    (stage_id, category, index, json.dumps(value))
                    for index, value in values.items()
                )
            for category in (2, 3, 4, 5):
                indices = row[str(category)].values()
                pickup_rows.extend((stage_id, category, i) for i in indices)
                if category in count:
                    count[category] += len(indices)
            if name in boards:
                stones = 3
                totals["stone_boards"] += 1
            if stones:
                db.execute(
                    "INSERT INTO campaign_stone_pieces VALUES(?,?) ON CONFLICT(stage_id) DO "
                    "UPDATE SET pieces=excluded.pieces WHERE pieces<excluded.pieces",
                    (stage_id, stones),
                )
        for category, resource in ((2, "PurpleCoins"), (3, "StarPieces")):
            current = profile[resource].setdefault(str(chapter), {})
            if current.get("Total", count[category]) != count[category]:
                raise ValueError(
                    f"{resource} for chapter {chapter} disagrees with installed tilemaps"
                )
            current.update(Current=count[category], Total=count[category])
        totals["purple_coins"] += count[2]
        totals["star_pieces"] += count[3]

    # Existing local progress takes precedence over an older snapshot.
    db.executemany("INSERT OR IGNORE INTO campaign_progress VALUES(?,?,?,?)", initial_rows)
    db.executemany(
        "INSERT INTO campaign_progress VALUES(?,?,?,'true') "
        "ON CONFLICT(stage_id,category,key) DO UPDATE SET value='true' WHERE value<>'true'",
        pickup_rows,
    )
    return totals


def complete_campaign(db, references):
    """Apply the main-world test state atomically. Caller backs up the selected database."""
    chapters, stages, specs, checkpoints, followers, boards, handles = catalog(references)
    db.execute("SAVEPOINT complete_campaign")
    try:
        row = db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()
        if row is None:
            raise ValueError("Create a local account and finish the prologue first")
        profile = json.loads(row[0])
        progress = profile["UserProgress"]
        if not progress["StageStates"].get("100000001", 0) & STAGE_CLEARED:
            raise ValueError("Finish the prologue before enabling campaign test mode")
        before = json.dumps(profile, separators=(",", ":"))
        db.execute(
            "CREATE TABLE IF NOT EXISTS campaign_test_state (id INTEGER PRIMARY KEY CHECK(id=1))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS campaign_stone_pieces (stage_id INTEGER PRIMARY KEY, "
            "pieces INTEGER NOT NULL CHECK(pieces BETWEEN 0 AND 3))"
        )
        imported = db.execute("SELECT stage_progresses FROM imported_account WHERE id=1").fetchone()
        cache = json.loads(imported[0]) if imported and not campaign_test_enabled(db) else {}
        totals = prepare_stages(db, profile, chapters, stages, boards, handles, cache)
        complete_quests(progress, specs, checkpoints)
        progress["Followers"].extend(sorted(followers.difference(progress["Followers"])))
        if json.dumps(profile, separators=(",", ":")) != before:
            progress["Cas"] += 1
            db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
        db.execute("INSERT OR IGNORE INTO campaign_test_state VALUES(1)")
        db.execute("RELEASE complete_campaign")
    except BaseException:
        db.execute("ROLLBACK TO complete_campaign")
        db.execute("RELEASE complete_campaign")
        raise
    return dict(chapters=len(chapters), stages=len(stages), quests=len(specs), **totals)
