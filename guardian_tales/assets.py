# SPDX-License-Identifier: Apache-2.0
"""Read-only loopback CDN backed by preservation manifests, never account files."""

import argparse
import hashlib
import json
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class ResourceLibrary:
    def __init__(self, roots):
        self.files = {}
        for root in roots:
            root = Path(root).resolve()
            manifest = json.loads(
                (root.parent.parent / "manifest.json").read_text(encoding="utf-8")
            )
            for row in manifest["files"]:
                name = row["path"]
                if not name.startswith("resources/files/"):
                    continue
                relative = name[len("resources/files/") :]
                path = (root / relative).resolve()
                if path.is_relative_to(root) and path.is_file():
                    self.files[relative] = (path, row["sha256"])

    def lookup(self, url):
        path = unquote(urlsplit(url).path).lstrip("/")
        if "\\" in path or any(p in (".", "..") for p in path.split("/")):
            return None
        for prefix in ("live/global/0491/", "master-global-v3.57.0/", "v3.57.0/", "3.57.0/"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
        if path.startswith("media/staticdata/"):
            path = "static_data/" + path[len("media/staticdata/") :]
        return self.files.get(path)


def handler_for(library, journal=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_response(self, code, message=None):
            self.response_code = code
            return super().send_response(code, message)

        def finish(self):
            try:
                return super().finish()
            finally:
                if journal:
                    with Path(journal).open("a", encoding="utf-8") as out:
                        out.write(
                            json.dumps(
                                {
                                    "phase": "response",
                                    "method": getattr(self, "command", None),
                                    "path": urlsplit(getattr(self, "path", "")).path,
                                    "status": getattr(self, "response_code", None),
                                }
                            )
                            + "\n"
                        )

        def do_HEAD(self):
            self.serve(False)

        def do_GET(self):
            self.serve(True)

        def serve(self, body):
            entry = library.lookup(self.path)
            if journal:
                # Paths only, no query strings, headers or cookies. Keep private.
                with Path(journal).open("a", encoding="utf-8") as out:
                    out.write(
                        json.dumps({"path": urlsplit(self.path).path, "found": bool(entry)}) + "\n"
                    )
            if entry is None:
                self.send_error(404)
                return
            path, sha = entry
            total = path.stat().st_size
            etag_file = Path(str(path) + ".etag")
            etag = etag_file.read_text().strip() if etag_file.is_file() else None
            if (
                not etag
                or "\r" in etag
                or "\n" in etag
                or not re.fullmatch(r'"[A-Za-z0-9._-]+"', etag)
            ):
                with path.open("rb") as src:
                    etag = '"' + hashlib.file_digest(src, "md5").hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            start, end = 0, total - 1
            range_value = self.headers.get("Range")
            if range_value:
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_value)
                if not match:
                    self.send_error(416)
                    return
                start = int(match[1])
                end = min(int(match[2]) if match[2] else end, end)
                if not 0 <= start <= end < total:
                    self.send_error(416)
                    return
            self.send_response(206 if range_value else 200)
            self.send_header(
                "Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("ETag", etag)
            self.send_header("Accept-Ranges", "bytes")
            if range_value:
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.end_headers()
            if body:
                try:
                    with path.open("rb") as src:
                        src.seek(start)
                        remaining = end - start + 1
                        while remaining > 0:
                            data = src.read(min(65536, remaining))
                            if not data:
                                break
                            self.wfile.write(data)
                            remaining -= len(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    return Handler


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Read-only local CDN restricted to preservation manifest entries."
    )
    p.add_argument("--resource-root", action="append", type=Path, required=True)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--journal", type=Path)
    p.add_argument("--run-seconds", type=int, default=0)
    args = p.parse_args(argv)
    library = ResourceLibrary(args.resource_root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(library, args.journal))
    server.daemon_threads = True
    if args.run_seconds:
        timer = threading.Timer(args.run_seconds, server.shutdown)
        timer.daemon = True
        timer.start()
    print("Local CDN: manifest-listed resource files:", len(library.files), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
