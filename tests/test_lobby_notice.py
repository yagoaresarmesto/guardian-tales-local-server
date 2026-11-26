# SPDX-License-Identifier: Apache-2.0
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales import lobby_notice as notice
from guardian_tales import lobby_settings
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

    def configure(self, enabled, generation, **options):
        (self.directory / notice.SETTINGS).write_text(
            json.dumps({"enabled": enabled, "generation": generation, **options}), encoding="utf-8"
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

    def test_configuration_changes_refresh_the_catalog_and_keep_in_flight_links(self):
        self.configure(True, 2, mode="settings")
        cards = [
            {
                "name": "Guild Raid",
                **lobby_settings.card("Season 1", "Custom lineup", [("Boss", "Earth < Fire")]),
            }
        ]
        with patch.object(lobby_settings, "report", return_value=cards):
            first = self.seed("static_data_get.bin")
            self.assertEqual(first, self.seed("static_data_get.bin"))
            catalog = json.loads(records(decode(first))[1]["webnotice"][1])
            new = catalog["WebNotice"][-1]
            self.assertEqual(json.loads(new["LobbyPopup"])["esES"], notice.media_path("settings-2"))
            detail = new["NoticeUrl"]["KakaoGlobal"].split(":18080/")[1]
            self.assertIn(b"Earth &lt; Fire", notice.image(self.directory, detail))
            cards[0]["summary"] = "Season 2"
            second = self.seed("static_data_get.bin")
            self.assertNotEqual(first, second)
            self.assertIn(b"Season 1", notice.image(self.directory, detail))
            self.assertIn(b"Season 2", notice.image(self.directory, detail.replace("-2.", "-3.")))
            self.configure(False, 3, mode="settings")
            self.assertEqual(notice.selection(self.refs), (False, 4))
            self.assertIsNone(notice.image(self.directory, detail))
            self.configure(True, 4)
            self.assertEqual(notice.selection(self.refs), ("4", 5))

    def test_disabled_modes_and_partial_expedition_overrides(self):
        self.assertEqual(lobby_settings.war_card(self.refs)["summary"], "Practice disabled")
        self.assertEqual(lobby_settings.dka_card(self.refs)["summary"], "No practice rotation")
        self.assertEqual(lobby_settings.expedition_card(self.refs)["summary"], "Trial disabled")
        (self.directory / lobby_settings.expedition.TRIAL).touch()
        stages = [
            {
                "stage_id": i,
                "name": f"expedition_battle_chosenone_1_{i}",
                "enemy_level": level,
                "original_level": 80,
                "overridden": i != 3,
            }
            for i, level in enumerate((110, 140, 80), 1)
        ]
        with patch.object(
            lobby_settings.expedition_levels, "level_settings", return_value={"stages": stages}
        ):
            card = lobby_settings.expedition_card(self.refs)
        self.assertEqual(card["summary"], "Enemy levels 110–140")
        self.assertEqual(card["caption"], "2 of 3 stages")
        self.assertEqual(len(card["details"]), 2)
