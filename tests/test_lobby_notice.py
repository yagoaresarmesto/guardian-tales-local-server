# SPDX-License-Identifier: Apache-2.0
import json
import tempfile
import unittest
from pathlib import Path

from guardian_tales import lobby_notice as notice
from guardian_tales.raid_static import compress, decode, digest, records, selected_static_seed
from guardian_tales.reference import ReferenceData


class LobbyNoticeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.refs = ReferenceData(self.directory)
        self.stock = {
            "WebNotice": [
                {
                    "Id": 1,
                    "LobbyPopup": json.dumps({"enUS": "old-en", "esES": "old-es"}),
                    "NoticeUrl": {"Test": "old-url", "KakaoGlobal": "old-global"},
                }
            ],
            "NoticeDate": [{"Id": 1}],
        }
        self.body = self.catalog_body()

    def catalog_body(self):
        values = {"untouched": "{}", "webnotice": json.dumps(self.stock), "__checksum__": "base"}
        return compress(
            "".join(f"{k}\n{v}\n11\n{digest(v.encode())}\n" for k, v in values.items()).encode()
        )

    def seed(self, name, request=None):
        def parent(refs, filename, request):
            return self.body if filename == "static_data_get.bin" else b"parent-check"

        return selected_static_seed(
            self.refs, name, request, parent, notice.selection, notice.prepare
        )

    def configure(self, enabled, generation):
        (self.directory / notice.SETTINGS).write_text(
            json.dumps({"enabled": enabled, "generation": generation}), encoding="utf-8"
        )

    def test_entry_uses_the_local_image_in_each_language_and_restores(self):
        self.assertEqual(self.seed("static_data_check.bin"), b"parent-check")
        self.configure(True, 1)
        get = records(decode(self.seed("static_data_get.bin")))[1]
        catalog = json.loads(get["webnotice"][1])
        self.assertEqual(catalog["WebNotice"][:-1], self.stock["WebNotice"])
        self.assertEqual(catalog["NoticeDate"][:-1], self.stock["NoticeDate"])
        new, dates = catalog["WebNotice"][-1], catalog["NoticeDate"][-1]
        media = notice.media_path(1)
        self.assertEqual(json.loads(new["LobbyPopup"]), {"enUS": media, "esES": media})
        self.assertEqual(dates["Id"], new["Id"])
        self.assertLess(dates["From"]["KakaoGlobal"], dates["To"]["KakaoGlobal"])
        self.assertEqual((new["Rewards"], new["NoticeType"]), ([], "None"))
        checksum = get["__checksum__"][1]
        self.assertTrue(
            json.loads(self.seed("static_data_check.bin", {"Checksum": checksum}))["UpToDate"]
        )
        self.configure(False, 2)
        restored = records(decode(self.seed("static_data_get.bin")))[1]
        self.assertFalse(
            json.loads(self.seed("static_data_check.bin", {"Checksum": checksum}))["UpToDate"]
        )
        self.assertEqual(json.loads(restored["webnotice"][1]), self.stock)
        self.assertGreater(restored["webnotice"][2], get["webnotice"][2])
        self.assertEqual(restored["untouched"], get["untouched"])

    def test_only_the_active_image_is_served(self):
        path = notice.media_path(1)
        (self.directory / "lobby_notice_1.png").write_bytes(b"demo")
        self.assertIsNone(notice.image(self.directory, path))
        self.configure(True, 1)
        self.assertEqual(notice.image(self.directory, path), b"demo")
        self.assertIsNone(notice.image(self.directory, notice.media_path(2)))
        self.assertIsNone(notice.image(self.directory, path + "/../private"))
        self.configure(False, 2)
        self.assertIsNone(notice.image(self.directory, path))

    def test_a_preserved_notice_id_is_never_overwritten(self):
        self.stock["NoticeDate"].append({"Id": notice.NOTICE_ID})
        with self.assertRaisesRegex(ValueError, "already in use"):
            notice.prepare(self.catalog_body(), True, 1)
