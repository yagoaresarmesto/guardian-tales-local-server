# SPDX-License-Identifier: Apache-2.0
"""Browse the local inventory and Guardian Mastery and apply offline save edits."""

import argparse
import gzip
import json
import re
import site
import sqlite3
import subprocess
import sys
import webbrowser
from contextlib import closing
from functools import partial
from http.server import ThreadingHTTPServer
from importlib import import_module, invalidate_caches
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from guardian_tales.panel_common.artwork import UI, decoder_available
from guardian_tales.panel_common.http import LocalPanelHandler
from guardian_tales.panel_common.views import HTML
from guardian_tales.raid_static import decode, records
from guardian_tales.reference import ReferenceData

from .account_details import AccountEditor
from .catalog import InventoryCatalog, inventory_icon
from .equipment import TYPE_ICONS
from .equipment_options import EquipmentOptionEditor
from .hero_portraits import HeroPortraits
from .mastery import MasteryEditor
from .mastery_art import training_banner
from .preview import Sandbox
from .relics import RelicEditor
from .routes import FILES, PAGES, render_page
from .stack_quantities import CONSUMABLES, StackQuantityEditor
from .weapon_progression import WeaponProgression

# Also declared by the panel-art extra. Bare checkouts lack installed package metadata.
PANEL_ART_REQUIREMENTS = ("UnityPy>=1.25.4,<2", "xxhash>=3.5,<5")


class Handler(LocalPanelHandler):
    def end_headers(self):
        if getattr(self, "compressed_json", False):
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        super().end_headers()

    def list_json(self, value):
        payload = json.dumps(value, separators=(",", ":")).encode()
        self.compressed_json = "gzip" in {
            coding.strip().lower() for coding in self.headers.get("Accept-Encoding", "").split(",")
        }
        if self.compressed_json:
            payload = gzip.compress(payload, compresslevel=2)
        return self.reply(200, "application/json; charset=utf-8", payload)

    def do_GET(self):
        if not self.allowed_host():
            return self.json(403, {"error": "Use the local preview address."})
        path = urlsplit(self.path).path
        if path in ("/items", "/necklaces"):
            self.send_response(302)
            self.send_header(
                "Location",
                "/equipment?q=Earth%20Necklace" if path == "/necklaces" else "/equipment",
            )
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        try:
            if path in PAGES:
                return self.reply(200, HTML, render_page(PAGES[path]))
            if path in FILES:
                file, mime = FILES[path]
                return self.reply(200, mime, file.read_bytes())
            if path == "/brand.png":
                brand = self.server.brand_image
                if brand.is_file():
                    return self.reply(200, "image/png", brand.read_bytes())
                path = "/type-icon/inventory.png"
            if path in self.server.listings:
                return self.list_json(self.server.listings[path]())
            if path == "/preview-status":
                return self.json(200, {"preview": "gt-inventory-sandbox"})
            if path == "/mastery-training.png":
                return self.reply(200, "image/png", training_banner(self.server.catalog.refs))
            hero = re.fullmatch(r"/hero-face/([0-9]{1,10})\.png", path)
            if hero:
                return self.reply(
                    200,
                    "image/png",
                    self.server.hero_portraits.read(self.server.catalog.refs, int(hero[1])),
                )
            if path in ("/api/game/relics/status", "/api/game/status"):
                return self.json(200, self.server.relics.status())
            if path.startswith("/type-icon/"):
                frame = TYPE_ICONS.get(path.removeprefix("/type-icon/").removesuffix(".png"))
                if frame:
                    return self.reply(
                        200,
                        "image/png",
                        inventory_icon(UI.read(self.server.catalog.refs, frame=frame)),
                    )
            icon = re.fullmatch(r"/icon/([0-9]{1,10})\.png", path)
            if icon:
                return self.reply(200, "image/png", self.server.catalog.icon(int(icon[1])))
            return self.json(404, {"error": "Unknown resource."})
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        except (FileNotFoundError, KeyError):
            return self.json(404, {"error": "Resource unavailable."})
        except (sqlite3.Error, OSError, ValueError) as error:
            return self.json(503, {"error": "Could not read the local save: " + str(error)})

    def do_POST(self):
        if self.path == "/api/relics":
            return self.json(410, {"error": "Reload Relics to open the game save editor."})
        if self.path != "/api/close" and self.path not in self.server.edits:
            return self.json(404, {"error": "Unknown action."})
        try:
            max_body = (
                32768
                if self.path.startswith("/api/game/mastery")
                else (4096 if self.path.startswith("/api/game/") else 512)
            )
            raw = self.read_body(max_body, "Invalid request size.")
            if not self.allowed_origin():
                return self.json(403, {"error": "Apply changes from the local panel."})
            if self.headers.get_content_type() != "application/json":
                return self.json(415, {"error": "Expected JSON."})
            payload = json.loads(raw)
            if self.path == "/api/close":
                if payload != {}:
                    raise ValueError("Invalid close request.")
                self.json(200, {"closed": True})
                self.server.shutdown()
                return
            status, result = self.server.edits[self.path](payload)
        except (TypeError, ValueError, KeyError, RecursionError) as err:
            status, result = 400, {"error": str(err)}
        except (sqlite3.Error, OSError) as err:
            status, result = 503, {"error": "Could not save the change: " + str(err)}
        self.json(status, result)


class InventoryServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, port, database, references, art_dir):
        database = database.resolve()
        self.database = database
        self.brand_image = art_dir / "brand.png"
        self._sandbox = None
        self._sandbox_guard = Lock()
        body = references.read_bytes("static_data_get.bin")
        tables = records(decode(body))[1]
        self.hero_portraits = HeroPortraits(tables)
        progression = WeaponProgression(tables)
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            self.catalog = InventoryCatalog(
                source,
                references,
                body,
                progression.thresholds,
                self.hero_portraits.name_keys,
                tables,
            )
        self.mastery = MasteryEditor(database, references)
        self.account_editor = AccountEditor(database, references, self.catalog.specs)
        self.relics = RelicEditor(database, self.catalog)
        self.equipment = EquipmentOptionEditor(database, self.catalog, tables, progression)
        self.consumables = StackQuantityEditor(database, self.catalog, CONSUMABLES)
        self.listings = {
            "/api/inventory": lambda: self.sandbox.listing(),
            "/api/game/account": self.account_editor.info,
            "/api/game/consumables": self.consumables.info,
            "/api/game/equipment": self.equipment.info,
            "/api/game/mastery": self.mastery.info,
            "/api/game/relics": self.relics.info,
        }
        self.edits = {
            "/api/lock": lambda payload: self.sandbox.change(payload),
            "/api/game/account": self.account_editor.write,
            "/api/game/consumables": self.consumables.write,
            "/api/game/equipment": self.equipment.request,
            "/api/game/equipment/roll": partial(self.equipment.request, roll=True),
            "/api/game/equipment/hammers": self.equipment.hammers.write,
            "/api/game/mastery": self.mastery.write,
            "/api/game/mastery/preview": self.mastery.preview,
            "/api/game/relics": self.relics.apply,
        }
        super().__init__(("127.0.0.1", port), Handler)

    @property
    def sandbox(self):
        # Only the separate preview pages need a temporary database.
        with self._sandbox_guard:
            if self._sandbox is None:
                db = sqlite3.connect(":memory:", check_same_thread=False)
                try:
                    with closing(
                        sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
                    ) as source:
                        source.backup(db)
                    self._sandbox = Sandbox(db, self.catalog.refs, self.catalog)
                except BaseException:
                    db.close()
                    raise
            return self._sandbox

    def server_close(self):
        super().server_close()
        if self._sandbox is not None:
            self._sandbox.db.close()


def display_readers_available():
    try:
        import_module("xxhash")
    except (ImportError, OSError):
        return False
    return decoder_available()


def ensure_display_readers():
    if display_readers_available():
        return
    print(
        "Installing the inventory artwork and name readers in this Python environment.",
        file=sys.stderr,
    )
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                "--no-input",
                *PANEL_ART_REQUIREMENTS,
            ],
            check=True,
        )
        # A first user-site install can create a directory missing from the startup path.
        if site.ENABLE_USER_SITE:
            user_site = site.getusersitepackages()
            if user_site not in sys.path and Path(user_site).is_dir():
                site.addsitedir(user_site)
        invalidate_caches()
        if display_readers_available():
            return
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Inventory display setup failed: {error}", file=sys.stderr)
    print(
        "Opening the inventory panel with placeholders. "
        "Run the same command again to retry inventory display setup.",
        file=sys.stderr,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("local/state"),
        help="Directory containing the working server.sqlite3",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("local/client-data/reference"),
        help="Imported reference directory",
    )
    parser.add_argument("--art-dir", type=Path, help="Directory containing an optional brand.png")
    parser.add_argument("--port", type=int, default=17661, help="Local HTTP port (default: 17661)")
    parser.add_argument(
        "--open", action="store_true", help="Open the inventory panel in your browser"
    )
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("Choose a port between 0 and 65535.")
    database = args.data_dir / "server.sqlite3"
    if not database.is_file():
        parser.error(
            f"Working save not found: {database}. Set --data-dir to your existing save directory."
        )
    ensure_display_readers()
    try:
        server = InventoryServer(
            args.port,
            database,
            ReferenceData(args.reference_dir),
            args.art_dir or args.data_dir.parent / "panel-art",
        )
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        parser.exit(1, f"Could not start the inventory panel: {error}\n")
    with server:
        address = f"http://127.0.0.1:{server.server_port}/"
        print(address, flush=True)
        if args.open:
            webbrowser.open(address)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
