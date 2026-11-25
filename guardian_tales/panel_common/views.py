# SPDX-License-Identifier: Apache-2.0
"""Render the shared dashboard header and section tabs around each editor."""

from html import escape
from pathlib import Path
from string import Template

HTML = "text/html; charset=utf-8"
CSS = "text/css; charset=utf-8"
JS = "text/javascript; charset=utf-8"


DASHBOARD = Path(__file__).parent / "static"


def render_layout(view, *, tabs, active_path, inventory=False, body_suffix="", **fields):
    links = []
    for path, label in tabs:
        current = ' aria-current="page"' if path == active_path else ""
        links.append(f'<a href="{escape(path)}"{current}>{escape(label)}</a>')
    template = Template((DASHBOARD / "layout.html").read_text(encoding="utf-8"))
    return template.substitute(
        navigation="\n      ".join(links),
        mode_section="" if inventory else ' aria-current="true"',
        inventory_section=' aria-current="true"' if inventory else "",
        section_name="Inventory" if inventory else "Game modes",
        body=view.read_text(encoding="utf-8") + body_suffix,
        **fields,
    ).encode()
