# SPDX-License-Identifier: Apache-2.0
import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from guardian_tales.assets import ResourceLibrary, handler_for
from guardian_tales.recommended_art import PREFIX, STORY_SCENERY


class AssetTests(unittest.TestCase):
    def setUp(self):
        base = Path(
            os.environ.get("GT_TEST_TMP", Path(__file__).resolve().parents[2] / ".test_tmp")
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
            words = root / "media/banwords"
            words.mkdir()
            manifest_path = folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            for name in (
                "kakao_en-US_name.txt",
                "kakao_es-ES_name.txt",
                "kakao_ko-KR_name.txt",
                "kakao_en-US_chat.txt",
                "other_name.txt",
            ):
                file = words / name
                file.write_bytes(b"synthetic-blocked\nsecond-word\n")
                Path(str(file) + ".etag").write_text('"preserved-word-list"')
                manifest["files"].append(
                    {
                        "path": "resources/files/media/banwords/" + name,
                        "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                    }
                )
            manifest_path.write_text(json.dumps(manifest))
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

    def test_recommended_cards_prefer_exact_then_mode_art_then_pack_scenery(self):
        scenery = self.library.lookup("/media/demo.jpg")
        bundle = self.library.lookup("/media/large.bin")
        self.library.files[STORY_SCENERY] = scenery
        self.library.files["AssetBundles/Android/ui/backgrounds/rogue_chess"] = bundle
        short = "/" + PREFIX + "story_short_00.png"
        tetis = "/" + PREFIX + "rogue_chess_02.png"
        with patch("guardian_tales.recommended_art._card", return_value=b"native-mode-art") as card:
            self.assertEqual(self.get(tetis)[2], b"native-mode-art")
            card.assert_called_once_with(*bundle, "bg_rogue_chess_perks_00")
            self.assertEqual(self.get(short)[2], b"supplement")
            chapter = "/live/global/0491/" + PREFIX + "ch21_00.png"
            self.assertEqual(self.get(chapter)[2], b"supplement")
            self.assertEqual(self.get("/" + PREFIX + "ch23_00.png")[0], 404)
            self.library.files[short[1:]] = bundle
            self.assertEqual(self.get(short)[2], self.large_payload)
            self.assertEqual(self.get("/" + PREFIX + "unknown.png")[0], 404)
        with patch("guardian_tales.recommended_art._card", side_effect=ImportError()):
            self.assertEqual(self.get(tetis)[2], b"supplement")

    @unittest.skipUnless(find_spec("PIL"), "requires the panel-art extra")
    def test_tetis_archive_serves_transparent_titles_and_the_matching_episode_scene(self):
        from PIL import Image

        prefix = "/live/global/0491/media/roguechess/"
        titles = []
        for name in (
            "v2.93_rc_1_title_enUS.png",
            "v3.09_rc_2_title_en.png",
            "v3.25_rc_3_title_enUS.png",
        ):
            code, headers, body = self.get(prefix + name)
            self.assertEqual((code, headers["Content-Type"]), (200, "image/png"))
            with Image.open(BytesIO(body)) as title:
                self.assertEqual(title.mode, "RGBA")
                self.assertEqual(title.getchannel("A").getextrema(), (0, 255))
            titles.append(body)
        self.assertEqual(len(set(titles)), 3)
        scene = Image.new("RGB", (24, 18), (25, 180, 197))
        bundle = self.library.lookup("/media/large.bin")
        self.library.files["AssetBundles/Android/ondemand/roguechess/narrative/ep2"] = bundle
        with patch("guardian_tales.tetis_art.bundle_texture", return_value=scene) as read:
            code, headers, body = self.get(prefix + "bg_rogue_chess_s2_00.png")
            self.assertEqual((code, headers["Content-Type"]), (200, "image/png"))
            with Image.open(BytesIO(body)) as replacement:
                self.assertEqual(replacement.getpixel((0, 0)), (25, 180, 197))
            read.assert_called_once_with(bundle[0], "Roguechess_main_S02")
        self.library.files["media/roguechess/bg_rogue_chess_s2_00.png"] = bundle
        self.assertEqual(self.get(prefix + "bg_rogue_chess_s2_00.png")[2], self.large_payload)
        self.assertEqual(self.get(prefix + "unknown_title.png")[0], 404)

    def test_name_word_lists_refresh_cached_content_without_changing_preserved_files(self):
        for name in ("kakao_en-US_name.txt", "kakao_es-ES_name.txt", "kakao_ko-KR_name.txt"):
            path, sha = self.library.lookup("/media/banwords/" + name)
            before = path.read_bytes(), Path(str(path) + ".etag").read_bytes()
            for prefix in ("/", "/live/global/0491/", "/live/global/0491/master-global-v3.57.0/"):
                code, headers, body = self.get(
                    prefix + "media/banwords/" + name, {"If-None-Match": '"preserved-word-list"'}
                )
                self.assertEqual((code, body), (200, b"\n"))
                self.assertNotEqual(headers["ETag"], '"preserved-word-list"')
                self.assertEqual(int(headers["Content-Length"]), 1)
                # Native Split with RemoveEmptyEntries creates a zero-word list.
                self.assertEqual(body.split(), [])
                self.assertEqual(
                    self.get(prefix + "media/banwords/" + name, {"If-None-Match": headers["ETag"]})[
                        0
                    ],
                    304,
                )
            self.assertEqual((path.read_bytes(), Path(str(path) + ".etag").read_bytes()), before)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)

    def test_name_list_head_range_and_normal_chat_lists_keep_correct_http_framing(self):
        path = "/media/banwords/kakao_en-US_name.txt"
        code, headers, body = self.get(path, method="HEAD")
        self.assertEqual((code, headers["Content-Length"], body), (200, "1", b""))
        code, headers, body = self.get(path, {"Range": "bytes=0-0"})
        self.assertEqual((code, headers["Content-Range"], body), (206, "bytes 0-0/1", b"\n"))
        self.assertEqual(self.get(path, {"Range": "bytes=1-2"})[0], 416)
        for name in ("kakao_en-US_chat.txt", "other_name.txt"):
            code, headers, body = self.get("/media/banwords/" + name)
            self.assertEqual((code, body), (200, b"synthetic-blocked\nsecond-word\n"))
            self.assertEqual(headers["ETag"], '"preserved-word-list"')
        self.assertEqual(self.get("/media/banwords/kakao_missing_name.txt")[0], 404)

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
