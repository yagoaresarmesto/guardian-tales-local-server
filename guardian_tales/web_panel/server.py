# SPDX-License-Identifier: Apache-2.0
"""Loopback HTTP transport for registered panel modes."""

import json
import socket
import sqlite3
import uuid
from http.server import ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import urlsplit

from guardian_tales.inventory_panel.application import InventoryApplication
from guardian_tales.inventory_panel.http import InventoryHandler
from guardian_tales.panel_common.services import service_request
from guardian_tales.panel_common.views import HTML

from .. import orbital_boards
from ..orbital import LAST_SELECTABLE_FLOOR
from .orbital_lift import tower
from .orbital_lift.adapter import OrbitalEditor
from .routes import API, FILES, PAGES, media_resource, render_page
from .tetis.adapter import TetisEditor


class WebPanel(ThreadingHTTPServer):
    # Finish any selection being published when the backend exits.
    daemon_threads = False
    # Inventory grids load dozens of separate artwork requests as a page opens.
    request_queue_size = 64
    inventory_home = False
    closing = False
    # On Windows SO_REUSEADDR lets two live dashboards serve the same endpoint.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(
        self, references, port, *, art_dir=None, database=None, restart=None, prepare_inventory=None
    ):
        self.references = references
        self.database = database.resolve() if database is not None else None
        self._inventory = None
        self._inventory_lock = Lock()
        self.prepare_inventory = prepare_inventory
        self.restart = restart
        self.instance = uuid.uuid4().hex
        self.tetis = TetisEditor(references, database)
        self.brand_image = art_dir / "brand.png" if art_dir is not None else None
        super().__init__(("127.0.0.1", port), PanelHandler)

    @property
    def orbital(self):
        if self.database is None:
            raise ValueError("This dashboard has no working game save.")
        return OrbitalEditor(self.database, self.references)

    @property
    def inventory(self):
        with self._inventory_lock:
            if self._inventory is None:
                if self.database is None:
                    raise ValueError("This dashboard has no working game save.")
                if self.prepare_inventory is not None:
                    self.prepare_inventory()
                    self.prepare_inventory = None
                self._inventory = InventoryApplication(self.database, self.references)
            return self._inventory

    def close_preview(self):
        with self._inventory_lock:
            if self._inventory is not None:
                self._inventory.close_preview()

    def server_close(self):
        self.closing = True
        super().server_close()
        self.close_preview()

    def start(self):
        Thread(target=self.serve_forever, name="Local web panel", daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


class PanelHandler(InventoryHandler):
    def do_GET(self):
        if service_request(self):
            return
        if not self.allowed_host():
            self.json(
                403, {"error": "Open the panel using the local address printed by the backend."}
            )
            return
        try:
            path = urlsplit(self.path).path
            if path == "/":
                path = "/equipment" if self.server.inventory_home else "/raid"
            if path == "/api/backend":
                self.json(
                    200,
                    {
                        "instance": self.server.instance,
                        "canRestart": self.server.restart is not None,
                    },
                )
            elif path in PAGES:
                brand = self.server.brand_image
                page = render_page(PAGES[path], show_brand=brand is not None and brand.is_file())
                self.reply(200, HTML, page)
            elif path in FILES:
                path, mime = FILES[path]
                self.reply(200, mime, path.read_bytes())
            elif path == "/api/orbital-lift/map":
                self.list_json(tower.encounters(self.server.references))
            elif path.startswith("/api/orbital-lift/boards/"):
                number = path.removeprefix("/api/orbital-lift/boards/")
                if (
                    not number.isascii()
                    or not number.isdecimal()
                    or len(number) > 4
                    or not 1 <= int(number) <= LAST_SELECTABLE_FLOOR
                ):
                    self.json(400, {"error": "Choose a floor from 1 to 1500."})
                    return
                self.json(200, orbital_boards.state(self.server.references, int(number)))
            elif path in API:
                mode = API[path]
                self.json(200, mode.state(getattr(self.server, mode.source)))
            elif resource := media_resource(path):
                reader, mime = resource
                self.reply(200, mime, reader(self.server.references), artwork=True)
            else:
                self.inventory_get(path)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # A user can navigate to another editor while its predecessor is still loading.
            return
        except FileNotFoundError:
            self.json(404, {"error": "Panel resource unavailable"})
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
            self.json(503, {"error": f"Could not load panel data: {error}"})

    def do_POST(self):
        if service_request(self):
            return
        mode = API.get(self.path)
        restarting = self.path == "/api/backend/restart"
        if mode is None and not restarting:
            return self.inventory_post()
        try:
            raw = self.read_body(4096, "Invalid selection size")
        except (ValueError, OSError) as error:
            self.json(400, {"error": str(error)})
            return
        if not self.allowed_origin():
            self.json(403, {"error": "Apply changes from the local panel."})
            return
        if self.headers.get_content_type() != "application/json":
            self.json(415, {"error": "Expected a JSON selection"})
            return
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            self.json(400, {"error": "Invalid JSON body"})
            return
        if restarting:
            if self.server.restart is None or body != {"instance": self.server.instance}:
                self.json(
                    409, {"error": "Reload the game-mode panel before restarting the backend."}
                )
                return
            self.json(202, {"restarting": True})
            self.server.restart()
            return
        try:
            result = mode.apply(getattr(self.server, mode.source), body)
        except mode.conflict as error:
            self.json(409, {"error": str(error)})
        except RuntimeError:
            self.json(
                409, {"error": "Another selection change is in progress. Reload and try again."}
            )
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            self.json(400, {"error": str(error)})
        except (OSError, sqlite3.Error) as error:
            self.json(503, {"error": f"Could not save the selection: {error}"})
        else:
            if result is None:
                self.json(200, {"applied": True})
            else:
                self.json(*result)
