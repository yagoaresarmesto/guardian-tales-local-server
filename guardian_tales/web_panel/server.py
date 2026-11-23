# SPDX-License-Identifier: Apache-2.0
"""Loopback HTTP transport for registered panel modes."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from .routes import API, FILES, MEDIA, PAGES, render_page


class WebPanel(ThreadingHTTPServer):
    # Finish any selection being published when the backend exits.
    daemon_threads = False

    def __init__(self, references, port, *, art_dir=None):
        super().__init__(("127.0.0.1", port), PanelHandler)
        self.references = references
        self.brand_image = art_dir / "brand.png" if art_dir is not None else None

    def start(self):
        Thread(target=self.serve_forever, name="Local web panel", daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


class PanelHandler(BaseHTTPRequestHandler):
    timeout = 8

    def reply(self, status, mime, data):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def json(self, status, value):
        self.reply(status, "application/json; charset=utf-8", json.dumps(value).encode())

    def allowed_host(self):
        port = self.server.server_port
        hosts = self.headers.get_all("Host", [])
        valid = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            valid.update(("127.0.0.1", "localhost"))
        return len(hosts) == 1 and hosts[0] in valid

    def do_GET(self):
        if not self.allowed_host():
            self.json(
                403, {"error": "Open the panel using the local address printed by the backend."}
            )
            return
        try:
            if self.path in PAGES:
                brand = self.server.brand_image
                page = render_page(
                    PAGES[self.path], show_brand=brand is not None and brand.is_file()
                )
                self.reply(200, "text/html; charset=utf-8", page)
            elif self.path == "/brand.png" and self.server.brand_image is not None:
                self.reply(200, "image/png", self.server.brand_image.read_bytes())
            elif self.path in FILES:
                path, mime = FILES[self.path]
                self.reply(200, mime, path.read_bytes())
            elif self.path in API:
                self.json(200, API[self.path].state(self.server.references))
            elif self.path in MEDIA:
                reader, mime = MEDIA[self.path]
                self.reply(200, mime, reader(self.server.references))
            else:
                self.json(404, {"error": "Unknown panel resource"})
        except FileNotFoundError:
            self.json(404, {"error": "Panel resource unavailable"})
        except (ValueError, KeyError, TypeError, OSError) as error:
            self.json(503, {"error": f"Could not load panel data: {error}"})

    def do_POST(self):
        mode = API.get(self.path)
        if mode is None:
            self.json(404, {"error": "Unknown panel action"})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if (
                len(lengths) != 1
                or "Transfer-Encoding" in self.headers
                or not 0 < int(lengths[0]) <= 4096
            ):
                raise ValueError("Invalid selection size")
            raw = self.rfile.read(int(lengths[0]))
        except (ValueError, OSError) as error:
            self.json(400, {"error": str(error)})
            return
        if not self.allowed_host() or self.headers.get_all("Origin") != [
            "http://" + self.headers["Host"].removesuffix(":80")
        ]:
            self.json(403, {"error": "Apply changes from the local panel."})
            return
        if self.headers.get_content_type() != "application/json":
            self.json(415, {"error": "Expected a JSON selection"})
            return
        try:
            body = json.loads(raw.decode("utf-8"))
            mode.apply(self.server.references, body)
        except mode.conflict as error:
            self.json(409, {"error": str(error)})
        except RuntimeError:
            self.json(
                409, {"error": "Another selection change is in progress. Reload and try again."}
            )
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            self.json(400, {"error": str(error)})
        except OSError as error:
            self.json(503, {"error": f"Could not save the selection: {error}"})
        else:
            self.json(200, {"applied": True})

    def log_message(self, format, *args):
        pass
