# SPDX-License-Identifier: Apache-2.0
"""Read-only manifest CDN and opt-in generated previews, never account files."""

import argparse
import hashlib
import json
import mimetypes
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .recommended_art import missing_recommended
from .service_control import register, restart_worker
from .tetis_art import missing_tetis_media


def resource_path(url):
    path = unquote(urlsplit(url).path).lstrip("/")
    if "\\" in path or any(p in (".", "..") for p in path.split("/")):
        return None
    for prefix in ("live/global/0491/", "master-global-v3.57.0/", "v3.57.0/", "3.57.0/"):
        if path.startswith(prefix):
            path = path[len(prefix) :]
    if path.startswith("media/staticdata/"):
        path = "static_data/" + path[len("media/staticdata/") :]
    return path


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
        return self.files.get(resource_path(url))


def handler_for(library, journal=None, reference_dir=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = 30

        def log_message(self, *args):
            pass

        def send_response(self, code, message=None):
            self.response_code = code
            return super().send_response(code, message)

        def handle_one_request(self):
            self.response_code = None
            self.command = None
            self.path = ""
            try:
                return super().handle_one_request()
            finally:
                if journal and self.response_code is not None:
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
            relative = resource_path(self.path)
            entry = library.lookup(self.path)
            override = None
            if entry is None:
                entry, override = missing_recommended(library, relative)
            if entry is None and override is None:
                override = missing_tetis_media(library, relative)
            if entry is None and override is None and reference_dir is not None:
                from .kamazone_banner import missing_banner

                try:
                    override = missing_banner(reference_dir, relative)
                except (OSError, ValueError):
                    self.send_error(503, "Optional Kama-ZONE preview is not ready")
                    return
            if journal:
                # Paths only, no query strings, headers or cookies. Keep private.
                with Path(journal).open("a", encoding="utf-8") as out:
                    out.write(
                        json.dumps(
                            {
                                "path": urlsplit(self.path).path,
                                "found": entry is not None or override is not None,
                            }
                        )
                        + "\n"
                    )
            if entry is None and override is None:
                self.send_error(404)
                return
            # A generated preview uses this path only for its MIME suffix.
            # All file reads remain in the original manifest-backed branch.
            path, sha = entry if entry is not None else (Path(resource_path(self.path)), None)
            # The native name filter splits nonempty lines from these downloaded
            # lists. Serve an empty list with a new ETag, retaining preserved files
            # and all chat word lists. This shared client list also covers guild names.
            local_name_list = (
                path.parent.name == "banwords"
                and path.parent.parent.name == "media"
                and re.fullmatch(r"kakao_[A-Za-z0-9-]+_name\.txt", path.name) is not None
            )
            override = b"\n" if local_name_list else override
            if override is None and reference_dir is not None:
                from .andras_trial_labels import cdn_override

                try:
                    override = cdn_override(reference_dir, path, sha)
                except (OSError, ValueError):
                    self.send_error(503, "Optional English title is not ready")
                    return
            total = len(override) if override is not None else path.stat().st_size
            etag_file = Path(str(path) + ".etag")
            etag = (
                '"' + hashlib.md5(override).hexdigest() + '"'
                if override is not None and not local_name_list
                else (
                    '"local-nickname-words-v1"'
                    if local_name_list
                    else etag_file.read_text().strip() if etag_file.is_file() else None
                )
            )
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
                    if override is not None:
                        self.wfile.write(override[start : end + 1])
                        return
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
        description="Read-only manifest CDN with optional in-memory preview responses."
    )
    p.add_argument("--resource-root", action="append", type=Path, required=True)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--journal", type=Path)
    p.add_argument(
        "--reference-dir", type=Path, help="Optional Andras title inputs and Kama-ZONE selection"
    )
    p.add_argument("--run-seconds", type=int, default=0)
    p.add_argument("--restart-worker", action="store_true", help=argparse.SUPPRESS)
    launch_args = list(sys.argv[1:] if argv is None else argv)
    args = p.parse_args(launch_args)
    library = ResourceLibrary(args.resource_root)
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), handler_for(library, args.journal, args.reference_dir)
    )
    server.daemon_threads = True
    timer = None
    if args.run_seconds:
        timer = threading.Timer(args.run_seconds, server.shutdown)
        timer.daemon = True
        timer.start()
    print("Local CDN: manifest-listed resource files:", len(library.files), flush=True)
    requested = threading.Event()
    port = server.server_port
    scope = (
        args.reference_dir.resolve().parent
        if args.reference_dir
        else args.resource_root[0].resolve().parent.parent
    )

    def restart():
        requested.set()
        server.shutdown()

    try:
        with register("cdn", scope, port, restart):
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if timer:
            timer.cancel()
        server.server_close()
    if requested.is_set():
        restart_worker("assets", launch_args, {"--port": port}, args.restart_worker)


if __name__ == "__main__":
    main()
