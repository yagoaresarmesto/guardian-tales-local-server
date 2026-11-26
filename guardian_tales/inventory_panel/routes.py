# SPDX-License-Identifier: Apache-2.0
"""Inventory tabs, public asset URLs and page rendering."""

from pathlib import Path
from string import Template

from guardian_tales.panel_common.views import CSS, JS, render_layout

STATIC = Path(__file__).parent / "static"
TITLES = {
    "equipment": "Equipment inventory",
    "relics": "Relics",
    "merch": "Merch",
    "heroes": "Heroes",
    "consumables": "Consumables",
    "mastery": "Guardian Mastery",
    "account": "Account",
}
PAGES = {"/" + slug: slug for slug in TITLES}
PAGES.update({"/": "equipment", "/equipment/preview": "equipment"})
FILES = {
    "/equipment.css": (STATIC / "shared/inventory.css", CSS),
    "/inventory-dom.js": (STATIC / "shared/inventory-dom.js", JS),
    "/quantity-editor.js": (STATIC / "shared/quantity-editor.js", JS),
    "/equipment-options.js": (STATIC / "equipment/options.js", JS),
    "/equipment-add.js": (STATIC / "equipment/add.js", JS),
    "/hero-add.js": (STATIC / "heroes/add.js", JS),
    "/copy-protection.js": (STATIC / "shared/copy-protection.js", JS),
    "/bulk-selection.js": (STATIC / "shared/bulk-selection.js", JS),
    "/delete-copy.js": (STATIC / "shared/delete-copy.js", JS),
    "/catalog-picker.js": (STATIC / "shared/catalog-picker.js", JS),
}


def stylesheet(slug):
    return "/equipment-options.css" if slug == "equipment" else f"/{slug}.css"


for slug in TITLES:
    FILES[f"/{slug}.js"] = (STATIC / slug / "panel.js", JS)
    FILES[stylesheet(slug)] = (STATIC / slug / "panel.css", CSS)


def render_page(slug):
    directory = STATIC / slug
    dialog = ""
    if slug in ("equipment", "relics", "merch"):
        dialog = Template((STATIC / "shared/catalog.html").read_text(encoding="utf-8")).substitute(
            section=slug,
            noun="relic" if slug == "relics" else slug,
            plural=slug,
            type_label={
                "relics": "Relic family",
                "equipment": "Equipment type",
                "merch": "Base rarity",
            }[slug],
        )
    if slug in ("equipment", "relics"):
        dialog += (STATIC / "shared/delete-copy.html").read_text(encoding="utf-8")
        dialog += (STATIC / "shared/bulk-selection.html").read_text(encoding="utf-8")
    return render_layout(
        directory / "view.html",
        tabs=(("/" + key, key.capitalize()) for key in TITLES),
        active_path="/" + slug,
        title=TITLES[slug],
        slug=slug,
        base_css="/equipment.css",
        brand_icon='<img class="brand-icon" src="/brand.png" alt="">',
        inventory=True,
        body_suffix=dialog,
        stylesheet=stylesheet(slug),
        body_attributes=' class="relic-page"' if slug == "relics" else "",
        preview_controls=(
            (directory / "preview-controls.html").read_text(encoding="utf-8")
            if slug == "equipment"
            else ""
        ),
    )
