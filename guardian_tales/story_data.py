# SPDX-License-Identifier: Apache-2.0
"""Main-story specifications from the preserved client tables."""

import json
from functools import lru_cache

from .raid_static import decode, records


def load(references):
    path = references.directory / "static_data_get.bin"
    return parse(path.read_bytes()) if path.is_file() else ({}, {}, {})


@lru_cache(maxsize=2)
def parse(body):
    _, tables = records(decode(body))
    if not {"chapterdata", "stages", "quests"} <= tables.keys():
        return {}, {}, {}

    chapters = {}
    for row in json.loads(tables["chapterdata"][1])["Chapter"]:
        code = row["ChapterId"]
        if (
            row.get("FirstStageId")
            and 10000 < code < 10300
            and row["Chapters"].startswith("chapter_")
        ):
            chapters[code] = []

    required_previous = {}
    if "mainqueststagesequence" in tables:
        for row in json.loads(tables["mainqueststagesequence"][1]):
            ids = row["StageSequence"]
            for previous, stage_id in zip(ids, ids[1:]):
                required_previous[stage_id] = previous

    stages = {}
    for row in json.loads(tables["stages"][1]):
        stage_id = row["Id"]
        chapter_code = stage_id // 10000
        # Main stages and side stages/passages share the story map's chapter code.
        if 11000 < chapter_code < 11300:
            chapter_code -= 1000
        if chapter_code not in chapters:
            continue
        key = str(stage_id)
        if key in stages:
            raise ValueError("Duplicate story stage in preserved tables")
        chapters[chapter_code].append(key)
        required_stage = row.get("ClearedStageId") or required_previous.get(stage_id)
        required_quests = row.get("ClearedQuests") or []
        stages[key] = {
            "stamina": row["Stamina"],
            "tilemap": row["Tilemap"].get("Default"),
            "requires_cleared": [required_stage] if required_stage else [],
            "requires_quests": required_quests,
            "quest_ids": row.get("Quests") or [],
            "requires_discovery": not (row.get("IsOpened") or required_stage or required_quests)
            or bool(row.get("MarkerCondition")),
        }

    story_quest_ids = {quest_id for stage in stages.values() for quest_id in stage["quest_ids"]}
    quests = {r["Id"]: r for r in json.loads(tables["quests"][1]) if r["Id"] in story_quest_ids}
    return chapters, stages, quests
