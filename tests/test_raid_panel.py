# SPDX-License-Identifier: Apache-2.0
"""Local browser selection, legacy CLI readback and atomic Raid publication."""

import json
import tempfile
import unittest
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales import guild_raid, raid_custom, raid_panel, raid_static
from guardian_tales.reference import ReferenceData
from guardian_tales.web_panel.artwork import BOSSES, UI, frame_png
from tests.test_guild_raid import synthetic_catalog, synthetic_static


class RaidPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.refs = ReferenceData(self.root)
        catalog = synthetic_catalog()
        names = ["ancient demon", "sandmonster", "fairy", "viper clan leader"]
        monsters = []
        for season in catalog["seasons"]:
            for row, name in zip(season["bosses"], names):
                row["stage_id"] = raid_custom.BOSS_STAGES[name]
                monsters.append(
                    dict(
                        Id=row["id"],
                        Name=name,
                        ElementalType="Fire",
                        Class=name,
                        SpriteName={"default": "native_" + name.replace(" ", "_")},
                    )
                )
        lines, tables = raid_static.records(raid_static.decode(synthetic_static(catalog)))
        raid = json.loads(tables["guildraid2"][1])
        for row in raid["BossDetails"]:
            row["MonsterId"] = row["Id"]
        raid["Round"] = [{"Round": 1, "SetId": 1, "BossHpBar": 500000}]
        lines[1] = json.dumps(raid) + "\n"
        lines[3] = raid_static.digest(lines[1].rstrip().encode()) + "\n"
        monster_json = json.dumps(monsters)
        lines[0:0] = [
            "monsters\n",
            monster_json + "\n",
            "1\n",
            raid_static.digest(monster_json.encode()) + "\n",
        ]
        (self.root / guild_raid.CATALOG).write_text(json.dumps(catalog))
        self.source = self.root / "static_data_get.bin"
        self.source.write_bytes(raid_static.compress("".join(lines).encode()))
        self.art_dir = self.root / "panel-art"
        self.server = raid_panel.RaidPanel(self.refs, 0, art_dir=self.art_dir)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def call(self, path="/api/raid", body=None, **headers):
        method = "GET" if body is None else "POST"
        request_headers = {"Origin": self.origin, "Content-Type": "application/json"}
        request_headers.update(headers)
        request = Request(
            self.origin + path,
            method=method,
            headers=request_headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response) if path == "/api/raid" else response.read()

    def test_default_stock_custom_cli_readback_and_restore(self):
        original = self.source.read_bytes()
        listing = self.call()
        self.assertFalse(listing["prepared"])
        self.assertEqual(listing["active"]["id"], 2)
        self.assertEqual(listing["active"]["bosses"][0]["element"], "fire")
        self.call(body=dict(mode="stock", revision=0, season=1))
        stock = self.call()
        lineup = [
            ["ancient demon", "fire"],
            ["fairy", "light"],
            ["viper clan leader", "dark"],
            ["ancient demon", "water"],
        ]
        custom = dict(mode="custom", revision=stock["revision"], lineup=lineup, hpPerBar=100000000)
        self.assertEqual(self.call(body=custom), {"applied": True})
        state = self.call()
        self.assertTrue(state["customHp"])
        self.assertEqual(state["active"]["hpPerBar"], 100000000)
        self.assertEqual([[s["boss"], s["element"]] for s in state["active"]["bosses"]], lineup)
        with self.assertRaises(HTTPError) as stale:
            self.call(body=custom)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        # An independent terminal can publish a new custom selection using stock HP.
        guild_raid.select_season(self.refs, lineup=raid_custom.validate_lineup(lineup[::-1]))
        state = self.call()
        self.assertFalse(state["customHp"])
        self.assertEqual(state["active"]["bosses"][0]["element"], "water")
        self.call(body=dict(mode="stock", revision=state["revision"], season=2))
        self.assertFalse(self.call()["custom"])
        self.assertEqual(guild_raid.selected_season(self.refs)["season_id"], 2)
        self.assertEqual(self.source.read_bytes(), original)

    def test_bad_or_foreign_submissions_preserve_selection(self):
        self.call(body=dict(mode="stock", revision=0, season=1))
        path = self.root / guild_raid.SELECTION
        original = path.read_bytes()
        rev = self.call()["revision"]
        stock = dict(mode="stock", revision=rev, season=2)
        lineup = [["fairy", s] for s in ("fire", "dark", "water", "light")]
        custom = dict(mode="custom", revision=rev, lineup=lineup, hpPerBar=None)
        for body, headers, status in (
            (stock, {"Origin": "https://example.invalid"}, 403),
            (stock, {"Host": "example.invalid"}, 403),
            (stock, {"Content-Type": "text/plain"}, 415),
            (dict(stock, season=999), {}, 400),
            (dict(stock, revision=True), {}, 400),
            (dict(custom, hpPerBar=0), {}, 400),
            (dict(custom, hpPerBar=2147483648), {}, 400),
            (dict(custom, lineup=lineup[:3]), {}, 400),
            (dict(custom, lineup=[lineup[0]] * 4), {}, 400),
            (dict(custom, lineup=[["unknown", "fire"], *lineup[1:]]), {}, 400),
        ):
            with self.subTest(body=body, headers=headers):
                with self.assertRaises(HTTPError) as error:
                    self.call(body=body, **headers)
                self.assertEqual(error.exception.code, status)
                error.exception.close()
                self.assertEqual(path.read_bytes(), original)

    def test_restart_requires_matching_instance_and_local_origin(self):
        status = json.loads(self.call("/api/backend"))
        restart = "/api/backend/restart"
        body = {"instance": status["instance"]}
        self.assertFalse(status["canRestart"])
        with self.assertRaises(HTTPError) as disabled:
            self.call(restart, body)
        self.assertEqual(disabled.exception.code, 409)
        disabled.exception.close()
        called = Event()
        self.server.restart = called.set
        self.assertTrue(json.loads(self.call("/api/backend"))["canRestart"])
        for payload, headers, code in (
            ({"instance": "previous-backend"}, {}, 409),
            (body, {"Origin": "https://example.invalid"}, 403),
        ):
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as rejected:
                self.call(restart, payload, **headers)
            self.assertEqual(rejected.exception.code, code)
            rejected.exception.close()
            self.assertFalse(called.is_set())
        request = Request(
            self.origin + restart,
            data=json.dumps(body).encode(),
            headers={"Origin": self.origin, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 202)
            self.assertEqual(json.load(response), {"restarting": True})
        self.assertTrue(called.wait(1))

    def test_optional_brand_is_shared_and_missing_art_does_not_block_the_pages(self):
        self.assertNotIn(b'src="/brand.png"', self.call("/"))
        self.art_dir.mkdir()
        logo = b"local test image"
        (self.art_dir / "brand.png").write_bytes(logo)
        for page in ("/", "/dka"):
            self.assertIn(b'src="/brand.png"', self.call(page))
        self.assertEqual(self.call("/brand.png"), logo)
        with self.assertRaises(HTTPError) as error:
            self.call("/dka/slimes/space.png")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_native_raid_portraits_and_element_icons_use_their_respective_atlases(self):
        self.assertEqual(self.call()["bossPortraits"], {})
        with patch.object(type(BOSSES), "available", return_value=True):
            listing = self.call()
            self.assertEqual(listing["bossPortraits"]["ancient demon"], "native_ancient_demon")
            self.assertTrue(listing["hasElementIcons"])
        stat = self.source.stat()
        with (
            patch.object(type(BOSSES), "available", return_value=True),
            patch.object(type(BOSSES), "path", return_value=self.source),
            patch("guardian_tales.panel_common.artwork._read_image", return_value=b"png") as read,
        ):
            for route, atlas, frame in (
                ("/raid/bosses/native_ancient_demon.png", BOSSES, "native_ancient_demon"),
                ("/elements/earth.png", UI, "ic_attribute_ground"),
                ("/elements/space.png", UI, "ic_attribute_nebula"),
                ("/dka/slimes/space.png", BOSSES, "punchking_boss_slime.super"),
            ):
                self.assertEqual(self.call(route), b"png")
                read.assert_called_with(
                    self.source, atlas.sheet, stat.st_mtime_ns, stat.st_size, frame
                )
            for path in ("/raid/bosses/subdir/native.png", "/elements/unknown.png"):
                with self.assertRaises(HTTPError) as error:
                    self.call(path)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()

    @unittest.skipUnless(find_spec("PIL"), "requires the panel-art extra")
    def test_atlas_frame_preserves_original_pixels_and_transparent_trim(self):
        from PIL import Image

        atlas = Image.new("RGBA", (8, 7), "red")
        atlas.putpixel((4, 2), (40, 50, 60, 128))
        entry = {
            "frame": {"x": 3, "y": 2, "w": 2, "h": 3},
            "rotated": False,
            "sourceSize": {"w": 6, "h": 7},
            "spriteSourceSize": {"x": 2, "y": 1, "w": 2, "h": 3},
        }
        icon = Image.open(BytesIO(frame_png(atlas, entry)))
        self.assertEqual(icon.size, (6, 7))
        self.assertEqual(icon.getbbox(), (2, 1, 4, 4))
        self.assertEqual(icon.getpixel((3, 1)), (40, 50, 60, 128))

    def test_page_and_assets_load_without_a_catalog_and_api_reports_missing_data(self):
        (self.root / guild_raid.CATALOG).unlink()
        self.assertIn(b"Guild Raid", self.call("/"))
        self.assertIn(b"fetch(", self.call("/raid.js"))
        self.assertIn(b".banner", self.call("/panel.css"))
        self.assertIn(b".battlefield", self.call("/raid.css"))
        self.assertIn(b".day-card", self.call("/dka.css"))
        self.assertIn(b"Dungeon Kingdom Arena", self.call("/dka"))
        self.assertIn(b"/api/dka", self.call("/dka.js"))
        with self.assertRaises(HTTPError) as arena_error:
            self.call("/api/dka")
        self.assertEqual(arena_error.exception.code, 503)
        arena_error.exception.close()
        with self.assertRaises(HTTPError) as error:
            self.call()
        self.assertEqual(error.exception.code, 503)
        self.assertIn("catalog", json.load(error.exception)["error"])
        error.exception.close()
