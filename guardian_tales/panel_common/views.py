# SPDX-License-Identifier: Apache-2.0
"""Render a panel's registered tabs inside its own HTML layout."""

from html import escape
from string import Template

HTML = "text/html; charset=utf-8"
CSS = "text/css; charset=utf-8"
JS = "text/javascript; charset=utf-8"


def render_layout(layout, view, *, tabs, active_path, **fields):
    links = []
    for path, label in tabs:
        current = ' aria-current="page"' if path == active_path else ""
        links.append(f'<a href="{escape(path)}"{current}>{escape(label)}</a>')
    template = Template(layout.read_text(encoding="utf-8"))
    return template.substitute(
        navigation="\n      ".join(links), body=view.read_text(encoding="utf-8"), **fields
    ).encode()
