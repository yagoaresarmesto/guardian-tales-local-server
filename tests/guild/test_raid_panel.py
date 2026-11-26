# SPDX-License-Identifier: Apache-2.0
"""Local browser selection, legacy CLI readback and atomic Raid publication."""

import json
import os
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
from guardian_tales.service_control import active_services, directory, register
from guardian_tales.web_panel.artwork import BOSSES, UI, frame_png
from tests.guild.test_guild_raid import synthetic_catalog, synthetic_static


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

    @unittest.skipUnless(find_spec("PIL"), "Pillow is optional")
    def test_dka_backdrop_serves_local_art_as_jpeg(self):
        from PIL import Image

        artwork = self.root / "arena.png"
        with patch("guardian_tales.web_panel.dka.adapter.arena_backdrop", return_value=artwork):
            with self.assertRaises(HTTPError) as missing:
                self.call("/dka/arena-backdrop.jpg")
            self.assertEqual(missing.exception.code, 404)
            missing.exception.close()
            Image.new("RGB", (40, 23), "navy").save(artwork)
            original = artwork.read_bytes()
            with Image.open(BytesIO(self.call("/dka/arena-backdrop.jpg"))) as preview:
                self.assertEqual((preview.format, preview.size), ("JPEG", (40, 23)))
            self.assertEqual(artwork.read_bytes(), original)

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

    def test_service_restart_checks_scope_origin_and_current_registration(self):
        db = self.root / "save.sqlite3"
        self.server.database = db
        called, other = Event(), Event()
        endpoint = "/api/services/restart"
        with (
            patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "cache")}),
            register("inventory", self.root / "unrelated.sqlite3", 11111, other.set),
            register("cdn", self.root.parent, 12345, other.set),
        ):
            foreign = active_services("inventory", self.root / "unrelated.sqlite3")[0][1]
            with register("inventory", db, 12346, called.set):
                rows = {
                    row["id"]: row for row in json.loads(self.call("/api/services"))["services"]
                }
                self.assertEqual((rows["cdn"]["port"], rows["inventory"]["port"]), (12345, 12346))
                self.assertIsNone(rows["game"]["instance"])
                token = rows["inventory"]["instance"]
                good = {"id": "inventory", "instance": token}
                for payload, headers, status in (
                    ({**good, "instance": foreign}, {}, 409),
                    ({**good, "id": "cdn"}, {}, 409),
                    (good, {"Origin": "https://elsewhere.invalid"}, 403),
                    (good, {"Host": "elsewhere.invalid"}, 403),
                    (good, {"Content-Type": "text/plain"}, 415),
                    ({"id": "all", "instance": token}, {}, 400),
                ):
                    with (
                        self.subTest(payload=payload, headers=headers),
                        self.assertRaises(HTTPError) as error,
                    ):
                        self.call(endpoint, payload, **headers)
                    self.assertEqual(error.exception.code, status)
                    error.exception.close()
                self.assertFalse(called.is_set())
                self.assertEqual(json.loads(self.call(endpoint, good)), {"restarting": True})
                self.assertTrue(called.wait(2))
                self.assertFalse(other.is_set())
            with register("inventory", db, 12346, other.set):
                running = active_services("inventory", db)
                self.assertEqual(len(running), 1)
                self.assertNotEqual(running[0][1], token)
                with self.assertRaises(HTTPError) as stale:
                    self.call(endpoint, good)
                self.assertEqual(stale.exception.code, 409)
                stale.exception.close()
                self.assertFalse(other.is_set())
            self.assertEqual(active_services("inventory", db), [])

    def test_dead_service_lease_is_not_advertised(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "cache")}):
            scope = self.root / "save.sqlite3"
            folder = directory(scope)
            folder.mkdir(parents=True)
            marker = folder / ("game-12345-" + "0" * 32 + ".ready")
            for suffix in (".ready", ".lock", ".restart", ".stop", ".expiry"):
                marker.with_suffix(suffix).touch()
            self.assertEqual(active_services("game", scope), [])
            self.assertEqual(list(folder.iterdir()), [])

    def test_certificate_dates_belong_to_each_game_instance(self):
        db = self.root / "save.sqlite3"
        self.server.database = db
        expiry = {"server": "2026-12-03T20:50:51Z", "authority": "2026-12-19T20:08:05Z"}
        standalone = {"server": "2027-01-02T19:08:05Z", "authority": None}
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "cache")}):
            with (
                register(
                    "game", db, 12345, self.fail, self.fail, certificate_expiry=expiry
                ) as stop,
                register("game", db, 12346, self.fail, certificate_expiry=standalone),
                register("inventory", db, 12347, self.fail),
            ):

                def rows():
                    return {
                        row["port"]: row
                        for row in json.loads(self.call("/api/services"))["services"]
                    }

                running = rows()
                self.assertEqual(running[12345]["certificateExpiry"], expiry)
                self.assertEqual(running[12346]["certificateExpiry"], standalone)
                self.assertNotIn("certificateExpiry", running[12347])
                stop()
                stopped = rows()[12345]
                self.assertTrue(stopped["stopped"])
                self.assertEqual(stopped["certificateExpiry"], expiry)
            self.assertEqual(list(directory(db).iterdir()), [])

    def test_game_stop_keeps_restart_control_and_rejects_foreign_or_stale_requests(self):
        db = self.root / "save.sqlite3"
        self.server.database = db
        stopped, restarted, foreign = Event(), Event(), Event()
        endpoint = "/api/services/stop"
        with (
            patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "cache")}),
            register("game", self.root / "other.sqlite3", 11111, foreign.set, foreign.set),
            register("inventory", db, 12347, foreign.set),
            register("game", db, 12346, restarted.set, stopped.set) as mark_stopped,
        ):

            def game_row():
                return next(
                    row
                    for row in json.loads(self.call("/api/services"))["services"]
                    if row["id"] == "game"
                )

            row = game_row()
            self.assertTrue(row["canStop"])
            self.assertFalse(row["stopped"])
            good = {"id": "game", "instance": row["instance"]}
            foreign_token = active_services("game", self.root / "other.sqlite3")[0][1]
            for payload, headers, status in (
                ({**good, "instance": foreign_token}, {}, 409),
                (good, {"Origin": "https://elsewhere.invalid"}, 403),
                (good, {"Host": "elsewhere.invalid"}, 403),
                (good, {"Content-Type": "text/plain"}, 415),
                ({**good, "id": "inventory"}, {}, 400),
                ({**good, "extra": True}, {}, 400),
            ):
                with (
                    self.subTest(payload=payload, headers=headers),
                    self.assertRaises(HTTPError) as error,
                ):
                    self.call(endpoint, payload, **headers)
                self.assertEqual(error.exception.code, status)
                error.exception.close()
            self.assertFalse(stopped.is_set())
            self.assertEqual(json.loads(self.call(endpoint, good)), {"stopping": True})
            self.assertTrue(stopped.wait(2))
            self.assertFalse(restarted.is_set())
            mark_stopped()
            row = game_row()
            self.assertTrue(row["stopped"])
            self.assertFalse(row["canStop"])
            self.assertEqual(row["instance"], good["instance"])
            with self.assertRaises(HTTPError) as duplicate:
                self.call(endpoint, good)
            self.assertEqual(duplicate.exception.code, 409)
            duplicate.exception.close()
            self.assertEqual(
                json.loads(self.call("/api/services/restart", good)), {"restarting": True}
            )
            self.assertTrue(restarted.wait(2))
            self.assertFalse(foreign.is_set())
        self.assertEqual(active_services("game", db), [])
        with self.assertRaises(HTTPError) as stale:
            self.call(endpoint, good)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()

    def test_older_service_registration_requires_relaunch_before_stop(self):
        db = self.root / "save.sqlite3"
        self.server.database = db
        restarted = Event()
        with (
            patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "cache")}),
            register("game", db, 12346, restarted.set),
        ):
            row = next(
                row
                for row in json.loads(self.call("/api/services"))["services"]
                if row["id"] == "game"
            )
            self.assertFalse(row["canStop"])
            self.assertIsNone(row["certificateExpiry"])
            with self.assertRaises(HTTPError) as old:
                self.call("/api/services/stop", {"id": "game", "instance": row["instance"]})
            self.assertEqual(old.exception.code, 409)
            old.exception.close()
            self.assertFalse(restarted.is_set())

    def test_service_runs_even_if_dashboard_registration_is_unavailable(self):
        unavailable = self.root / "file-in-place-of-cache"
        unavailable.touch()
        with patch.dict(os.environ, {"LOCALAPPDATA": str(unavailable)}):
            with register("cdn", self.root, 12345, self.fail):
                self.assertEqual(active_services("cdn", self.root), [])

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
