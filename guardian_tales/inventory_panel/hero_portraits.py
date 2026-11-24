# SPDX-License-Identifier: Apache-2.0
"""Resolve a weapon's native hero ID to the portraits used by the installed game."""

import json

from guardian_tales.panel_common.artwork import Atlas

PORTRAITS = Atlas("spritesheets/heroes", "portraits")


class HeroPortraits:
    def __init__(self, tables):
        heroes = json.loads(tables["heroes"][1]) if "heroes" in tables else []
        # In the hero table, rank 5 is ascended and rank 6 is Myth.
        myth = {
            hero["OriginId"]: hero["PortraitAssetName"]
            for hero in heroes
            if hero.get("OriginId") and hero.get("Rank") == 6 and hero.get("PortraitAssetName")
        }
        base_faces = {
            hero["Id"]: hero["PortraitAssetName"]
            for hero in heroes
            if hero["Id"] == hero.get("OriginId") and hero.get("PortraitAssetName")
        }
        self.name_keys = {}
        self.frames = {}
        for hero in heroes:
            base = hero.get("PortraitAssetName")
            origin = hero.get("OriginId")
            preferred = myth.get(origin)
            if origin in base_faces:
                self.name_keys[hero["Id"]] = "name_" + base_faces[origin]
            self.frames[hero["Id"]] = tuple(
                dict.fromkeys(name for name in (preferred, base) if name)
            )

    def read(self, references, hero_id):
        for frame in self.frames.get(hero_id, ()):
            try:
                return PORTRAITS.read(references, frame=frame)
            except FileNotFoundError:
                continue
        raise FileNotFoundError("Hero portrait unavailable in the local atlas")
