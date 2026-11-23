# SPDX-License-Identifier: Apache-2.0
"""Generate an original menu-preview PNG only for a selected missing season banner."""

import hashlib
import json
import re
import struct
import zlib
from functools import lru_cache

from . import kamazone
from .raid_static import decode, records
from .reference import ReferenceData

# Original block lettering, not extracted game artwork or a bundled font.
FONT = {
    "A": "01110/10001/10001/11111/10001/10001/10001",
    "E": "11111/10000/10000/11110/10000/10000/11111",
    "I": "11111/00100/00100/00100/00100/00100/11111",
    "K": "10001/10010/10100/11000/10100/10010/10001",
    "M": "10001/11011/10101/10101/10001/10001/10001",
    "N": "10001/11001/10101/10011/10001/10001/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110",
    "P": "11110/10001/10001/11110/10000/10000/10000",
    "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110",
    "U": "10001/10001/10001/10001/10001/10001/01110",
    "V": "10001/10001/10001/10001/10001/01010/00100",
    "W": "10001/10001/10001/10101/10101/10101/01010",
    "Z": "11111/00001/00010/00100/01000/10000/11111",
    "-": "00000/00000/00000/11111/00000/00000/00000",
    " ": "00000/00000/00000/00000/00000/00000/00000",
    "0": "01110/10001/10011/10101/11001/10001/01110",
    "1": "00100/01100/00100/00100/00100/00100/01110",
    "2": "01110/10001/00001/00010/00100/01000/11111",
    "3": "11110/00001/00001/01110/00001/00001/11110",
    "4": "00010/00110/01010/10010/11111/00010/00010",
    "5": "11111/10000/10000/11110/00001/00001/11110",
    "6": "01110/10000/10000/11110/10001/10001/01110",
    "7": "11111/00001/00010/00100/01000/01000/01000",
    "8": "01110/10001/10001/01110/10001/10001/01110",
    "9": "01110/10001/10001/01111/00001/00001/01110",
}


@lru_cache(maxsize=64)
def render(season_id):
    if type(season_id) is not int or not 1 <= season_id <= 0x7FFFFFFF:
        raise ValueError("Invalid preview season ID")
    width, height = 720, 192
    pixels = bytearray(bytes((14, 24, 44)) * width * height)

    def box(x, y, w, h, color):
        for line in range(y, y + h):
            at = (line * width + x) * 3
            pixels[at : at + w * 3] = bytes(color) * w

    def text(label, y, scale, color):
        x = (width - (len(label) * 6 - 1) * scale) // 2
        for character in label:
            for row, bits in enumerate(FONT[character].split("/")):
                for column, bit in enumerate(bits):
                    if bit == "1":
                        box(x + column * scale, y + row * scale, scale, scale, color)
            x += 6 * scale

    box(0, 0, width, 4, (35, 184, 213))
    box(0, height - 4, width, 4, (35, 184, 213))
    text("KAMA-ZONE", 22, 8, (240, 246, 255))
    text("SEASON " + str(season_id), 100, 4, (109, 218, 242))
    text("MENU PREVIEW", 149, 3, (160, 178, 200))

    def chunk(kind, body):
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    scanlines = b"".join(b"\0" + pixels[y * width * 3 : (y + 1) * width * 3] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def missing_banner(directory, path):
    if path is None or not re.fullmatch(
        r"media/kamazon_land/v[0-9.]+_kamazon_land_event_banner_[A-Za-z]+\.png", path
    ):
        return None
    references = ReferenceData(directory)
    selected = kamazone.load(references)
    if selected is None or selected["season_id"] is None:
        return None
    now = kamazone.utc_now()
    if (
        not kamazone.timestamp(selected["period"]["From"])
        <= now
        < kamazone.timestamp(selected["period"]["RewardUntil"])
    ):
        return None
    body = references.read_bytes("static_data_get.bin")
    if hashlib.sha256(body).hexdigest() != selected["source_sha256"]:
        raise ValueError("Kama-ZONE preview belongs to another content pack")
    if selected["season_id"] not in kamazone.catalog(body):
        raise ValueError("Kama-ZONE preview needs a selected Global season")
    tables = records(decode(body))[1]
    season = kamazone.one(
        json.loads(tables["kamazonland2"][1])["Seasons"], "Id", selected["season_id"]
    )
    banner = season.get("Banner")
    urls = json.loads(banner) if isinstance(banner, str) else banner
    if not isinstance(urls, dict) or path not in urls.values():
        return None
    return render(selected["season_id"])
