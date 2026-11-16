# SPDX-License-Identifier: Apache-2.0
import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from guardian_tales.assets import ResourceLibrary, handler_for


class AssetTests(unittest.TestCase):
    def setUp(self):
        base = Path(
            os.environ.get("GT_TEST_TMP", Path(__file__).resolve().parents[1] / ".test_tmp")
        )
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        roots = []
        for i, payload in enumerate((b"base", b"supplement")):
            folder = Path(self.temp.name) / str(i)
            root = folder / "resources/files"
            (root / "media").mkdir(parents=True)
            file = root / "media/demo.jpg"
            file.write_bytes(payload)
            Path(str(file) + ".etag").write_text('"synthetic-etag"')
            (root / "KpUser.dat").write_bytes(b"NEVER_SERVE_THIS")
            (folder / "manifest.json").write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "path": "resources/files/media/demo.jpg",
                                "sha256": hashlib.sha256(payload).hexdigest(),
                            }
                        ]
                    }
                )
            )
            roots.append(root)
        self.library = ResourceLibrary(roots)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.library))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def get(self, path, headers=None, method="GET"):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            c.request(method, path, headers=headers or {})
            r = c.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            c.close()

    def test_overlay_etag_conditional_and_range(self):
        code, headers, body = self.get("/media/demo.jpg")
        self.assertEqual((code, body), (200, b"supplement"))
        self.assertEqual(headers["ETag"], '"synthetic-etag"')
        self.assertEqual(self.get("/media/demo.jpg", {"If-None-Match": headers["ETag"]})[0], 304)
        code, headers, body = self.get("/media/demo.jpg", {"Range": "bytes=1-3"})
        self.assertEqual((code, body), (206, b"upp"))
        self.assertEqual(headers["Content-Range"], "bytes 1-3/10")
        self.assertEqual(self.get("/media/demo.jpg", method="HEAD")[2], b"")
        self.assertEqual(
            self.get("/live/global/0491/master-global-v3.57.0/media/demo.jpg")[2], b"supplement"
        )

    def test_account_files_and_path_traversal_are_not_served(self):
        for path in (
            "/KpUser.dat",
            "/media/../KpUser.dat",
            "/%2e%2e/manifest.json",
            "/media/%2e%2e/KpUser.dat",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)
