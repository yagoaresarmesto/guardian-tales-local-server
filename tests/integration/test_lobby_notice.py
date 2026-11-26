# SPDX-License-Identifier: Apache-2.0
import json
import tempfile
import unittest
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from guardian_tales.content.reference import ReferenceData
from guardian_tales.lobby_ui import lobby_notice as notice
from guardian_tales.lobby_ui import lobby_notice_art, lobby_notice_details, lobby_settings
from guardian_tales.modes.guild.raid_static import (
    compress,
    decode,
    digest,
    records,
    selected_static_seed,
)


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

    def test_detail_guide_preserves_navigation_day_and_all_stage_overrides_without_art(self):
        cards = [
            {
                "name": "Dungeon Kingdom Arena",
                **lobby_settings.card(
                    "Rotation 2",
                    "Season 36",
                    [("Day 1", "Fire Slime · Downed"), ("Day 2", "Void Slime · Airborne")],
                    selectedDay=2,
                ),
            },
            {
                "name": "Expedition",
                **lobby_settings.card(
                    "Enemy levels",
                    details=[
                        ("Area 4 · Boss (123)", "Lv. 82 → 140"),
                        ("Event <A> (124)", "Lv. 90 → 140"),
                    ],
                ),
            },
            {"name": "Guild Wars", **lobby_settings.card("Practice disabled")},
        ]
        with patch.object(lobby_notice_details, "heading_art", return_value=""):
            page = lobby_notice_details.detail_page(self.refs, cards).decode()
        self.assertEqual(page.count('type="radio"'), 3)
        for n in range(3):
            self.assertIn(f'<label for="mode-{n}">', page)
            self.assertIn(f'<article id="sheet-{n}"', page)
        self.assertIn('aria-controls="sheet-0" checked', page)
        self.assertIn('Day 2<span class="current">Selected</span>', page)
        self.assertEqual(page.count('<span class="current">'), 1)
        self.assertIn("Airborne", page)
        self.assertIn("<summary>Area 4", page)
        self.assertIn("<summary>Other stages", page)
        self.assertIn("Event &lt;A&gt;<small>124</small>", page)
        self.assertIn("Practice disabled", page)

    def test_next_floor_details_use_effective_level_formation_and_elites(self):
        import sqlite3
        from contextlib import closing

        stock = {
            "level": 80,
            "units": [{"position": 1, "enemy": 8, "origin": 1}],
            "originalElites": {1: 5},
        }
        catalog = {
            "floors": {1001: stock},
            "enemies": [{"id": 8, "name": "Imp"}],
            "eliteNames": {5: "Mortar"},
        }
        with (
            closing(sqlite3.connect(":memory:")) as db,
            patch.object(self.refs, "read_bytes", return_value=b""),
            patch.object(lobby_settings.orbital_boards, "catalog", return_value=catalog),
            patch.object(lobby_settings.orbital_levels, "settings") as settings,
        ):
            db.execute("CREATE TABLE local_account(id INTEGER, profile TEXT)")
            db.execute(
                "INSERT INTO local_account VALUES (1, ?)",
                (json.dumps({"UserProgress": {"TowerInfinity": {"Floor": 1000}}}),),
            )
            settings.return_value = {"level": 90, "boards": {}}
            card = lobby_settings.orbital_card(self.refs, db)
            self.assertEqual(
                card["currentFloor"], {"level": 90, "units": [("Cell 1", "Imp · Mortar")]}
            )
            settings.return_value["boards"]["1001"] = {
                "level": 120,
                "units": [{"enemy": 8, "position": 7, "origin": 1, "elite": None}],
            }
            card = lobby_settings.orbital_card(self.refs, db)
            self.assertEqual(card["currentFloor"], {"level": 120, "units": [("Cell 7", "Imp")]})

    def test_dka_uses_the_slime_sprite_for_the_saved_day_and_variant(self):
        elements = ("None", "Ice", "Light", "Earth", "Darkness", "Fire", "Nebula")
        expected = ("basic", "water", "light", "earth", "dark", "fire", "space")
        days = [{"element": element, "weak_point": "Down"} for element in elements]
        options = {
            "variants": [
                {"id": 1, "season_id": 36, "days": list(reversed(days))},
                {"id": 2, "season_id": 37, "days": days},
            ]
        }
        with (
            patch.object(lobby_settings.punchking, "load_catalog", return_value=options),
            patch.object(lobby_settings.punchking_static, "load_selection") as selection,
        ):
            for day, element in enumerate(expected, 1):
                selection.return_value = {"variant": 2, "day": day}
                card = lobby_settings.dka_card(self.refs)
                self.assertEqual(card["sprite"], f"/dka/slimes/{element}.png")
            self.assertEqual(card["caption"], "Season 37 · Void Slime")
            selection.return_value = None
            self.assertIsNone(lobby_settings.dka_card(self.refs).get("sprite"))

    @unittest.skipUnless(find_spec("PIL"), "Lobby rendering requires Pillow")
    def test_optional_scenery_and_sprites_are_composed_independently(self):
        from PIL import Image

        image = Image.new("RGBA", (50, 50), "red")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        tile_card = {"name": "Dungeon Kingdom Arena", "sprite": "/dka/slimes/space.png"}

        def resource(path):
            def read(refs):
                if path == tile_card["sprite"]:
                    return buffer.getvalue()
                raise FileNotFoundError(path)

            return read, "image/png"

        with patch("guardian_tales.web_panel.routes.media_resource", side_effect=resource):
            tile, illustrated = lobby_notice_art.mode_illustration(self.refs, tile_card)
            self.assertTrue(illustrated)
            self.assertEqual(tile.getpixel((412, 82)), (255, 0, 0, 255))
            self.assertEqual(tile.getpixel((23, 82)), (28, 46, 65, 255))
            tile, illustrated = lobby_notice_art.mode_illustration(
                self.refs, {"name": "Expedition"}
            )
            self.assertFalse(illustrated)
            self.assertEqual(tile.getpixel((412, 82)), (28, 46, 65, 255))
