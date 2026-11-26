# SPDX-License-Identifier: Apache-2.0
"""HTTP response and request checks for local browser panels."""

import hashlib
import json
from http.server import BaseHTTPRequestHandler

from .views import CSS, JS


class LocalPanelHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 8

    def parse_request(self):
        self.connection.settimeout(self.timeout)
        return super().parse_request()

    def end_headers(self):
        # Only bodyless GETs can be followed by another request on this socket.
        headers = getattr(self, "headers", {})
        if (
            self.server.closing
            or self.command != "GET"
            or "Transfer-Encoding" in headers
            or "Content-Length" in headers
        ):
            self.send_header("Connection", "close")
        super().end_headers()

    def handle_one_request(self):
        super().handle_one_request()
        if not self.close_connection:
            # Release idle browser sockets promptly on a service restart.
            self.connection.settimeout(2)

    def reply(self, status, mime, data, *, artwork=False, compressed=False):
        cache = "no-store"
        etag = None
        if self.command == "GET" and status == 200:
            if artwork or mime.startswith("image/"):
                cache = "private, max-age=900"
            elif mime in (CSS, JS):
                cache = "private, no-cache"
        if cache != "no-store":
            etag = '"' + hashlib.sha256(data).hexdigest() + '"'
            validators = self.headers.get("If-None-Match", "").split(",")
            if any(value.strip().removeprefix("W/") in ("*", etag) for value in validators):
                status = 304
        self.send_response(status)
        if status != 304:
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        if etag:
            self.send_header("ETag", etag)
        if compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        if status != 304:
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

    def allowed_origin(self):
        return self.allowed_host() and self.headers.get_all("Origin") == [
            "http://" + self.headers["Host"].removesuffix(":80")
        ]

    def read_body(self, limit, error):
        lengths = self.headers.get_all("Content-Length", [])
        if (
            len(lengths) != 1
            or "Transfer-Encoding" in self.headers
            or not 0 < int(lengths[0]) <= limit
        ):
            raise ValueError(error)
        return self.rfile.read(int(lengths[0]))

    def log_message(self, format, *args):
        pass
