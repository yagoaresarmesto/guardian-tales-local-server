# SPDX-License-Identifier: Apache-2.0
"""Generate an original menu-preview PNG only for a selected missing season banner."""

import hashlib
import json
import re
from functools import lru_cache

from guardian_tales.content.pixel_banner import PixelBanner
from guardian_tales.content.reference import ReferenceData

from . import kamazone


@lru_cache(maxsize=64)
def render(season_id):
    if type(season_id) is not int or not 1 <= season_id <= 0x7FFFFFFF:
        raise ValueError("Invalid preview season ID")
    width, height = 720, 192
    image = PixelBanner(width, height, (14, 24, 44))
    image.box(0, 0, width, 4, (35, 184, 213))
    image.box(0, height - 4, width, 4, (35, 184, 213))
    image.text("KAMA-ZONE", 22, 8, (240, 246, 255))
    image.text("SEASON " + str(season_id), 100, 4, (109, 218, 242))

    return image.png()


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
    if not kamazone.playable_season(body, selected["season_id"]):
        raise ValueError("Kama-ZONE preview needs a selected Global season")
    season = kamazone.one(
        kamazone.mode_data(body, selected["season_id"])["Seasons"], "Id", selected["season_id"]
    )
    banner = season.get("Banner")
    urls = json.loads(banner) if isinstance(banner, str) else banner
    if not isinstance(urls, dict) or path not in urls.values():
        return None
    return render(selected["season_id"])
