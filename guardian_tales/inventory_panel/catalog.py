# SPDX-License-Identifier: Apache-2.0
"""Equipment definitions, display names and inventory sprites."""

import json
from functools import lru_cache
from io import BytesIO

from guardian_tales.head_hunter_static import SOURCE, VARIANT, active_spec
from guardian_tales.panel_common.artwork import UI, Atlas
from guardian_tales.test_item_static import PIN_ID, active_specs, item_definitions

from .equipment import EquipmentDisplay
from .equipment_ribbons import read_completed_books

NAMES = {
    9110264: "Earth Necklace",
    SOURCE: "Head Hunter",
    VARIANT: "Head Hunter Myth",
    PIN_ID: "Rustic but Precious Pin",
}
ICONS = Atlas("spritesheets/items", "items")


@lru_cache(maxsize=512)
def inventory_icon(png):
    """Fit inventory artwork to its visible pixels, preserving the original sprite."""
    from PIL import Image

    with Image.open(BytesIO(png)) as sprite:
        bounds = sprite.getchannel("A").getbbox()
        if bounds is None:
            raise FileNotFoundError("Empty inventory sprite")
        if bounds == (0, 0, *sprite.size):
            return png
        output = BytesIO()
        sprite.crop(bounds).save(output, format="PNG")
        return output.getvalue()


class InventoryCatalog:
    def __init__(self, db, references, catalog, thresholds, hero_name_keys, tables):
        self.refs = references
        self.specs = {s["Id"]: s for s in item_definitions(catalog)}
        self.equipment = EquipmentDisplay(
            references,
            self.specs,
            catalog,
            thresholds,
            hero_name_keys,
            read_completed_books(db, self.specs, tables),
        )
        self.names = self.equipment.names | NAMES
        for encoded in active_specs(db):
            spec = json.loads(encoded)
            self.specs[spec["Id"]] = spec
            self.names[spec["Id"]] = "Rustic but Precious Pin · trial"
        head = active_spec(db, references)
        if head:
            self.specs[VARIANT] = json.loads(head)
        self.has_icons = ICONS.available(references) or UI.available(references)

    def icon(self, ident):
        sprite = self.specs.get(ident, {}).get("SpriteName")
        frame = sprite.get("default") if isinstance(sprite, dict) else None
        if not frame:
            raise FileNotFoundError
        try:
            png = ICONS.read(self.refs, frame=frame)
        except FileNotFoundError:
            png = UI.read(self.refs, frame=frame)
        return inventory_icon(png)
