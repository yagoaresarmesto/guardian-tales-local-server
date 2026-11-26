# SPDX-License-Identifier: Apache-2.0
"""Opt-in local image for the client's native lobby notice."""

import json
from functools import lru_cache
from pathlib import Path

from .raid_static import LOCAL_FROM, LOCAL_TO, compress, decode, digest, records
from .reference import ReferenceData
from .village import integer

SETTINGS = "lobby_notice.json"
NOTICE_ID = 900001
MEDIA_PREFIX = "media/local/lobby-notice-"


def selection(references):
    path = references.directory / SETTINGS
    if not path.is_file():
        return False, 0
    settings = json.loads(path.read_bytes())
    if (
        not isinstance(settings, dict)
        or type(settings.get("enabled")) is not bool
        or not integer(settings.get("generation"), minimum=1)
    ):
        raise ValueError("Invalid lobby notice settings")
    return settings["enabled"], settings["generation"]


def media_path(generation):
    return f"{MEDIA_PREFIX}{generation}.png"


def image(directory, relative):
    if not relative or not relative.startswith(MEDIA_PREFIX):
        return None
    enabled, generation = selection(ReferenceData(directory))
    if enabled and relative == media_path(generation):
        return (Path(directory) / f"lobby_notice_{generation}.png").read_bytes()
    return None


@lru_cache(maxsize=2)
def prepare(body, enabled, generation):
    lines, tables = records(decode(body))
    if not {"webnotice", "__checksum__"} <= tables.keys():
        raise ValueError("The lobby notice requires the matching web notice catalog")
    content = tables["webnotice"][1]
    if enabled:
        catalog = json.loads(content)
        notices, dates = catalog["WebNotice"], catalog["NoticeDate"]
        if any(row["Id"] == NOTICE_ID for row in (*notices, *dates)):
            raise ValueError("The local lobby notice ID is already in use")
        template = next((row for row in notices if row.get("LobbyPopup")), None)
        if template is None:
            raise ValueError("Missing the localized lobby notice template")
        locales = json.loads(template["LobbyPopup"])
        publishers = template["NoticeUrl"]
        media = media_path(generation)
        notices.append(
            {
                "Id": NOTICE_ID,
                "Type": "GET",
                "Param": None,
                "Rewards": [],
                "NoticeUrl": dict.fromkeys(publishers, f"http://127.0.0.1:18080/{media}"),
                "LobbyPopup": json.dumps(dict.fromkeys(locales, media)),
                "NoticeType": "None",
                "NoticeTitle": "",
                "DailyDisabling": False,
            }
        )
        dates.append(
            {
                "Id": NOTICE_ID,
                "From": dict.fromkeys(publishers, LOCAL_FROM),
                "To": dict.fromkeys(publishers, LOCAL_TO),
            }
        )
        content = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    checksum = digest(f"lobby-notice/{generation}/{tables['__checksum__'][1]}/{content}".encode())
    for name, value in (("webnotice", content), ("__checksum__", checksum)):
        index, _, revision = tables[name]
        if not integer(revision + generation, minimum=1):
            raise ValueError("The lobby notice revision exceeds the client limit")
        lines[index : index + 4] = [
            f"{part}\n" for part in (name, value, revision + generation, digest(value.encode()))
        ]
    return compress("".join(lines).encode()), checksum
