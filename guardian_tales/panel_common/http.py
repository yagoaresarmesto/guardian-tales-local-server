# SPDX-License-Identifier: Apache-2.0
"""HTTP response and request checks for local browser panels."""

import json
from http.server import BaseHTTPRequestHandler


class LocalPanelHandler(BaseHTTPRequestHandler):
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
