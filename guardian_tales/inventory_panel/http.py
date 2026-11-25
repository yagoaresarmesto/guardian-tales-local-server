# SPDX-License-Identifier: Apache-2.0
"""HTTP handling for inventory resources in the local dashboard."""

import gzip
import json
import re
import sqlite3

from guardian_tales.panel_common.artwork import UI
from guardian_tales.panel_common.http import LocalPanelHandler
from guardian_tales.panel_common.views import HTML

from .catalog import inventory_icon
from .equipment import TYPE_ICONS
from .mastery_art import training_banner
from .routes import FILES, PAGES, render_page


class InventoryHandler(LocalPanelHandler):
    def list_json(self, value):
        payload = json.dumps(value, separators=(",", ":")).encode()
        compressed = "gzip" in {
            coding.strip().lower() for coding in self.headers.get("Accept-Encoding", "").split(",")
        }
        if compressed:
            payload = gzip.compress(payload, compresslevel=2)
        return self.reply(200, "application/json; charset=utf-8", payload, compressed=compressed)

    def inventory_get(self, path):
        if path in ("/items", "/necklaces"):
            self.send_response(302)
            self.send_header(
                "Location",
                "/equipment?q=Earth%20Necklace" if path == "/necklaces" else "/equipment",
            )
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        try:
            if path in PAGES:
                return self.reply(200, HTML, render_page(PAGES[path]))
            if path in FILES:
                file, mime = FILES[path]
                return self.reply(200, mime, file.read_bytes())
            if path == "/brand.png":
                brand = self.server.brand_image
                if brand is not None and brand.is_file():
                    return self.reply(200, "image/png", brand.read_bytes())
                path = "/type-icon/inventory.png"
            if path == "/preview-status":
                return self.json(200, {"preview": "gt-inventory-sandbox"})
            if path == "/mastery-training.png":
                return self.reply(200, "image/png", training_banner(self.server.references))
            hero = re.fullmatch(r"/hero-face/([0-9]{1,10})\.png", path)
            if hero:
                return self.reply(
                    200,
                    "image/png",
                    self.server.inventory.hero_portraits.read(self.server.references, int(hero[1])),
                )
            if path.startswith("/api/game/") or path == "/api/inventory":
                inventory = self.server.inventory
                if path in ("/api/game/relics/status", "/api/game/status"):
                    return self.json(200, inventory.relics.status())
                if path in inventory.listings:
                    return self.list_json(inventory.listings[path]())
            if path.startswith("/type-icon/"):
                frame = TYPE_ICONS.get(path.removeprefix("/type-icon/").removesuffix(".png"))
                if frame:
                    return self.reply(
                        200,
                        "image/png",
                        inventory_icon(UI.read(self.server.references, frame=frame)),
                    )
            icon = re.fullmatch(r"/icon/([0-9]{1,10})\.png", path)
            if icon:
                return self.reply(
                    200, "image/png", self.server.inventory.catalog.icon(int(icon[1]))
                )
            return self.json(404, {"error": "Unknown resource."})
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        except (FileNotFoundError, KeyError):
            return self.json(404, {"error": "Resource unavailable."})
        except (sqlite3.Error, OSError, ValueError) as error:
            return self.json(503, {"error": "Could not read the local save: " + str(error)})

    def inventory_post(self):
        if self.path == "/api/relics":
            return self.json(410, {"error": "Reload Relics to open the game save editor."})
        if self.path not in (
            "/api/lock",
            "/api/close",
            "/api/preview/close",
        ) and not self.path.startswith("/api/game/"):
            return self.json(404, {"error": "Unknown action."})
        try:
            max_body = (
                32768
                if self.path.startswith("/api/game/mastery")
                else (4096 if self.path.startswith("/api/game/") else 512)
            )
            if re.fullmatch(
                r"/api/game/(equipment|relics)/(lock|unlock|delete|force-delete)", self.path
            ):
                max_body = 1024 * 1024
            raw = self.read_body(max_body, "Invalid request size.")
            if not self.allowed_origin():
                return self.json(403, {"error": "Apply changes from the local panel."})
            if self.headers.get_content_type() != "application/json":
                return self.json(415, {"error": "Expected JSON."})
            payload = json.loads(raw)
            if self.path in ("/api/close", "/api/preview/close"):
                if payload != {}:
                    raise ValueError("Invalid close request.")
                self.server.close_preview()
                self.json(200, {"closed": True})
                if self.path == "/api/close" and self.server.inventory_home:
                    # Legacy launchers use this endpoint to stop the standalone server.
                    self.server.shutdown()
                return
            action = self.server.inventory.edits.get(self.path)
            if action is None:
                return self.json(404, {"error": "Unknown action."})
            status, result = action(payload)
        except (TypeError, ValueError, KeyError, RecursionError) as err:
            status, result = 400, {"error": str(err)}
        except (sqlite3.Error, OSError) as err:
            status, result = 503, {"error": "Could not save the change: " + str(err)}
        self.json(status, result)
