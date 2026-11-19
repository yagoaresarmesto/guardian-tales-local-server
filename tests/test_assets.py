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
        self.large_payload = bytes(range(251)) * 1024 + b"final partial chunk"
        roots = []
        for i, payload in enumerate((b"base", b"supplement")):
            folder = Path(self.temp.name) / str(i)
            root = folder / "resources/files"
            (root / "media").mkdir(parents=True)
            file = root / "media/demo.jpg"
            file.write_bytes(payload)
            Path(str(file) + ".etag").write_text('"synthetic-etag"')
            large = root / "media/large.bin"
            large.write_bytes(self.large_payload)
            (root / "KpUser.dat").write_bytes(b"NEVER_SERVE_THIS")
            (folder / "manifest.json").write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "path": "resources/files/media/demo.jpg",
                                "sha256": hashlib.sha256(payload).hexdigest(),
                            },
                            {
                                "path": "resources/files/media/large.bin",
                                "sha256": hashlib.sha256(self.large_payload).hexdigest(),
                            },
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

    def test_full_head_conditional_and_range_share_one_persistent_connection(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("GET", "/media/large.bin")
            response = connection.getresponse()
            self.assertEqual((response.status, response.version), (200, 11))
            self.assertFalse(response.will_close)
            self.assertEqual(response.read(), self.large_payload)
            etag = response.getheader("ETag")
            socket = connection.sock

            connection.request("HEAD", "/media/large.bin")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(int(response.getheader("Content-Length")), len(self.large_payload))
            self.assertEqual(response.read(), b"")

            connection.request("GET", "/media/large.bin", headers={"If-None-Match": etag})
            response = connection.getresponse()
            self.assertEqual(response.status, 304)
            self.assertEqual(response.read(), b"")

            connection.request("GET", "/media/large.bin", headers={"Range": "bytes=65517-131087"})
            response = connection.getresponse()
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), self.large_payload[65517:131088])
            self.assertIs(connection.sock, socket)
        finally:
            connection.close()

    def test_journal_records_each_persistent_request_once_without_queries(self):
        journal = Path(self.temp.name) / "requests.jsonl"
        finished = threading.Event()
        base = handler_for(self.library, journal)

        class Observed(base):
            def finish(self):
                try:
                    super().finish()
                finally:
                    finished.set()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Observed)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            for method, headers in (
                ("GET", {}),
                ("HEAD", {}),
                ("GET", {"If-None-Match": '"synthetic-etag"'}),
            ):
                connection.request(method, "/media/demo.jpg?synthetic=excluded", headers=headers)
                connection.getresponse().read()
            connection.close()
            self.assertTrue(finished.wait(timeout=2))
            text = journal.read_text(encoding="utf-8")
            responses = [json.loads(line) for line in text.splitlines() if '"phase"' in line]
            self.assertEqual([row["status"] for row in responses], [200, 200, 304])
            self.assertEqual([row["method"] for row in responses], ["GET", "HEAD", "GET"])
            self.assertTrue(all(row["path"] == "/media/demo.jpg" for row in responses))
            self.assertNotIn("synthetic=excluded", text)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
