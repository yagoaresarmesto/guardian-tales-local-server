# SPDX-License-Identifier: Apache-2.0
"""Show imported event banners or illustrations of the corresponding season NPC."""

from dataclasses import dataclass
from io import BytesIO

from guardian_tales.panel_common.artwork import Atlas

PORTRAITS = Atlas("spritesheets/heroes", "portraits")


@dataclass(frozen=True)
class SeasonArt:
    version: str
    hero: str
    theme: str

    def original(self, references):
        name = f"v{self.version}_kamazon_land_event_banner_enUS.png"
        return references.directory.parent / "resources/files/media/kamazon_land" / name

    @property
    def scenery(self):
        return Atlas(f"illusts/{self.hero}", f"bg_{self.hero}")

    def available(self, references):
        return self.original(references).is_file() or self.scenery.available(references)

    def read(self, references):
        original = self.original(references)
        if original.is_file():
            return original.read_bytes()
        scenery = self.scenery.read(references)
        from PIL import Image, ImageDraw, ImageOps

        # The actor in SeasonsNpc supplies the theme when the event PNG was not imported.
        with Image.open(BytesIO(scenery)) as image:
            card = ImageOps.fit(image, (520, 240), Image.Resampling.LANCZOS, centering=(0.5, 0.42))
        try:
            portrait = PORTRAITS.read(references, frame=self.hero)
        except FileNotFoundError:
            portrait = None
        if portrait:
            with Image.open(BytesIO(portrait)) as image:
                face = ImageOps.fit(image, (116, 116), Image.Resampling.LANCZOS)
            mask = Image.new("L", face.size)
            ImageDraw.Draw(mask).ellipse((0, 0, 115, 115), fill=255)
            ImageDraw.Draw(card).ellipse((379, 59, 500, 180), fill="#fff0cd")
            card.paste(face, (382, 62), mask)
        output = BytesIO()
        card.save(output, format="PNG")
        return output.getvalue()


SEASONS = {
    "mall_season_name_1": SeasonArt(
        "3.18", "dragon_boy", "Meet Girgas and raise a puppy companion."
    ),
    "mall_season_name_2": SeasonArt(
        "3.30", "summer_android", "Help AA72 find rescue tubes at Bianca’s lifeguard boot camp."
    ),
    "mall_season_name_3": SeasonArt(
        "3.47", "fire_harpy_mecha", "Collect legendary parts for Scintilla’s mecha suit."
    ),
}


def season_card(references, season):
    card = {"id": season["season_id"], "name": season["name"]}
    art = SEASONS.get(season["name_key"])
    if art:
        card["theme"] = art.theme
        if art.available(references):
            card["image"] = f"/kamazone/seasons/{art.hero}.png"
    return card
