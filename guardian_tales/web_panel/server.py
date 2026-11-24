# SPDX-License-Identifier: Apache-2.0
"""Loopback HTTP transport for registered panel modes."""

import json
import sqlite3
import uuid
from http.server import ThreadingHTTPServer
from threading import Thread

from guardian_tales.panel_common.http import LocalPanelHandler
from guardian_tales.panel_common.views import HTML

from .routes import API, FILES, PAGES, media_resource, render_page
from .tetis.adapter import TetisEditor


class WebPanel(ThreadingHTTPServer):
    # Finish any selection being published when the backend exits.
    daemon_threads = False

    def __init__(self, references, port, *, art_dir=None, database=None, restart=None):
        super().__init__(("127.0.0.1", port), PanelHandler)
        self.references = references
        self.restart = restart
        self.instance = uuid.uuid4().hex
        self.tetis = TetisEditor(references, database)
        self.brand_image = art_dir / "brand.png" if art_dir is not None else None

    def start(self):
        Thread(target=self.serve_forever, name="Local web panel", daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


class PanelHandler(LocalPanelHandler):
    def do_GET(self):
        if not self.allowed_host():
            self.json(
                403, {"error": "Open the panel using the local address printed by the backend."}
            )
            return
        try:
            if self.path == "/api/backend":
                self.json(
                    200,
                    {
                        "instance": self.server.instance,
                        "canRestart": self.server.restart is not None,
                    },
                )
            elif self.path in PAGES:
                brand = self.server.brand_image
                page = render_page(
                    PAGES[self.path], show_brand=brand is not None and brand.is_file()
                )
                self.reply(200, HTML, page)
            elif self.path == "/brand.png" and self.server.brand_image is not None:
                self.reply(200, "image/png", self.server.brand_image.read_bytes())
            elif self.path in FILES:
                path, mime = FILES[self.path]
                self.reply(200, mime, path.read_bytes())
            elif self.path in API:
                mode = API[self.path]
                self.json(200, mode.state(getattr(self.server, mode.source)))
            elif resource := media_resource(self.path):
                reader, mime = resource
                self.reply(200, mime, reader(self.server.references))
            else:
                self.json(404, {"error": "Unknown panel resource"})
        except FileNotFoundError:
            self.json(404, {"error": "Panel resource unavailable"})
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
            self.json(503, {"error": f"Could not load panel data: {error}"})

    def do_POST(self):
        mode = API.get(self.path)
        restarting = self.path == "/api/backend/restart"
        if mode is None and not restarting:
            self.json(404, {"error": "Unknown panel action"})
            return
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
            mode.apply(getattr(self.server, mode.source), body)
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
            self.json(200, {"applied": True})
