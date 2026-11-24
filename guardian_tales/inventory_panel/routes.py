# SPDX-License-Identifier: Apache-2.0
"""Inventory tabs, public asset URLs and page rendering."""

from pathlib import Path

from guardian_tales.panel_common.views import CSS, JS, render_layout

STATIC = Path(__file__).parent / "static"
TITLES = {
    "equipment": "Equipment inventory",
    "relics": "Relics",
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
}


def stylesheet(slug):
    return "/equipment-options.css" if slug == "equipment" else f"/{slug}.css"


for slug in TITLES:
    FILES[f"/{slug}.js"] = (STATIC / slug / "panel.js", JS)
    FILES[stylesheet(slug)] = (STATIC / slug / "panel.css", CSS)


def render_page(slug):
    directory = STATIC / slug
    return render_layout(
        STATIC / "shared/layout.html",
        directory / "view.html",
        tabs=(("/" + key, key.capitalize()) for key in TITLES),
        active_path="/" + slug,
        title=TITLES[slug],
        slug=slug,
        stylesheet=stylesheet(slug),
        body_attributes=' class="relic-page"' if slug == "relics" else "",
        preview_controls=(
            (directory / "preview-controls.html").read_text(encoding="utf-8")
            if slug == "equipment"
            else ""
        ),
    )
