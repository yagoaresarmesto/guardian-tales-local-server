# SPDX-License-Identifier: Apache-2.0
"""Publish the local game mode summary in the client's native lobby notice."""

import hashlib
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from threading import Lock

from guardian_tales.content.reference import ReferenceData
from guardian_tales.modes.guild.raid_static import (
    LOCAL_FROM,
    LOCAL_TO,
    compress,
    decode,
    digest,
    records,
    source_tables,
)
from guardian_tales.runtime.packet_reader import MAX_PACKET
from guardian_tales.settlement.village import integer

SETTINGS = "lobby_notice.json"
NOTICE_ID = 900001
MEDIA_PREFIX = "media/local/lobby-notice-"
REPORTS = "lobby_notice_snapshots.json"
DEFAULT_SETTINGS = (True, 2, "settings")
_publish_lock = Lock()


def settings(references):
    path = references.directory / SETTINGS
    if not path.is_file():
        return None
    settings = json.loads(path.read_bytes())
    if (
        not isinstance(settings, dict)
        or type(settings.get("enabled")) is not bool
        or not integer(settings.get("generation"), minimum=1)
        or settings.get("mode", "image") not in ("image", "settings")
    ):
        raise ValueError("Invalid lobby notice settings")
    return settings["enabled"], settings["generation"], settings.get("mode", "image")


def notice_fields(catalog):
    notices, dates = catalog["WebNotice"], catalog["NoticeDate"]
    if not all(isinstance(rows, list) for rows in (notices, dates)):
        raise ValueError("Invalid web notice catalog")
    if any(row["Id"] == NOTICE_ID for row in (*notices, *dates)):
        raise ValueError("The local lobby notice ID is already in use")
    template = next((row for row in notices if row.get("LobbyPopup")), None)
    if template is None:
        raise ValueError("Missing the localized lobby notice template")
    locales, publishers = json.loads(template["LobbyPopup"]), template["NoticeUrl"]
    if not all(isinstance(keys, dict) and keys for keys in (locales, publishers)):
        raise ValueError("Missing lobby notice locales or publishers")
    return notices, dates, locales, publishers


@lru_cache(maxsize=2)
def supports_summary(path, modified, size):
    if not 5 <= size <= MAX_PACKET:
        return False
    try:
        tables = source_tables(path.read_bytes())
        if "__checksum__" not in tables:
            return False
        notice_fields(json.loads(tables["webnotice"][1]))
    except (ValueError, KeyError, TypeError, OSError):
        return False
    return True


def selection(references, db=None):
    configured = settings(references)
    if configured is None:
        source = references.directory / "static_data_get.bin"
        try:
            stat = source.stat()
        except OSError:
            return False, 0
        if not supports_summary(source, stat.st_mtime_ns, stat.st_size):
            return False, 0
    enabled, generation, mode = configured or DEFAULT_SETTINGS
    if mode == "image" and not (references.directory / REPORTS).exists():
        return enabled, generation
    from guardian_tales.modes.guild.punchking_static import atomic_write

    from .lobby_settings import report

    path = references.directory / REPORTS
    with _publish_lock:
        history = json.loads(path.read_bytes()) if path.is_file() else []
        rows = report(references, db) if enabled and mode == "settings" else []
        contents = [enabled, mode, generation, rows]
        if rows:
            contents.append("illustrated-details-v2")
        signature = hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()
        if history and history[0]["signature"] == signature:
            revision = history[0]["revision"]
        else:
            revision = max(generation, history[0]["revision"] + 1 if history else 1)
            snapshot = {"revision": revision, "signature": signature, "cards": rows}
            try:
                atomic_write(
                    path, json.dumps([snapshot, *history[:1]], separators=(",", ":")).encode()
                )
            except OSError:
                if configured is not None:
                    raise
                logging.getLogger(__name__).warning(
                    "Could not publish the default lobby notice", exc_info=True
                )
                return False, 0
    if not enabled:
        return False, revision
    return (f"settings-{revision}" if mode == "settings" else str(generation)), revision


def media_path(generation):
    return f"{MEDIA_PREFIX}{generation}.png"


def image(directory, relative):
    if not relative or not relative.startswith(MEDIA_PREFIX):
        return None
    enabled, generation, mode = settings(ReferenceData(directory)) or DEFAULT_SETTINGS
    if not enabled:
        return None
    if mode == "image" and relative == media_path(generation):
        return (Path(directory) / f"lobby_notice_{generation}.png").read_bytes()
    match = re.fullmatch(
        re.escape(MEDIA_PREFIX) + r"settings-([1-9][0-9]{0,9})\.(png|html)", relative
    )
    cache = Path(directory) / REPORTS
    if mode == "settings" and match and cache.is_file():
        from .lobby_notice_art import render

        for snapshot in json.loads(cache.read_bytes()):
            if snapshot["revision"] == int(match[1]) and snapshot["cards"]:
                return render(Path(directory), json.dumps(snapshot["cards"]), match[2])
    return None


@lru_cache(maxsize=2)
def prepare(body, enabled, generation):
    lines, tables = records(decode(body))
    if not {"webnotice", "__checksum__"} <= tables.keys():
        raise ValueError("The lobby notice requires the matching web notice catalog")
    content = tables["webnotice"][1]
    if enabled:
        catalog = json.loads(content)
        notices, dates, locales, publishers = notice_fields(catalog)
        media = media_path(generation if enabled is True else enabled)
        target = (
            media.removesuffix(".png") + ".html"
            if isinstance(enabled, str) and enabled.startswith("settings-")
            else media
        )
        notices.append(
            {
                "Id": NOTICE_ID,
                "Type": "GET",
                "Param": None,
                "Rewards": [],
                "NoticeUrl": dict.fromkeys(publishers, f"http://127.0.0.1:18080/{target}"),
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
