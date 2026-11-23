# SPDX-License-Identifier: Apache-2.0
"""Browse equipment, relics and consumables and apply offline inventory edits."""

import argparse
import gzip
import json
import re
import sqlite3
import uuid
import webbrowser
from contextlib import closing
from functools import lru_cache
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from guardian_tales.account import AccountStore
from guardian_tales.head_hunter_static import SOURCE, VARIANT, active_spec
from guardian_tales.item_lock import INVENTORIES, LOCK, UNLOCK
from guardian_tales.item_sell import gear_references
from guardian_tales.reference import ReferenceData
from guardian_tales.test_item_static import PIN_ID, active_specs, item_definitions
from guardian_tales.web_panel.artwork import UI, Atlas
from guardian_tales.web_panel.server import PanelHandler

from .consumables import ConsumableEditor
from .equipment import TYPE_ICONS, EquipmentDisplay
from .equipment_options import EquipmentOptionEditor
from .relics import RelicEditor

STATIC = Path(__file__).resolve().parent / "static"

GROUPS = dict(zip(INVENTORIES, ("Equipment", "Miscellaneous", "Stackables")))
NAMES = {
    9110264: "Earth Necklace",
    SOURCE: "Head Hunter",
    VARIANT: "Head Hunter Myth",
    PIN_ID: "Rustic but Precious Pin",
}
ICONS = Atlas("spritesheets/items", "items")


@lru_cache(maxsize=512)
def inventory_icon(png):
    """Fit inventory artwork to its visible pixels, preserving the original sprite."""
    from PIL import Image

    with Image.open(BytesIO(png)) as sprite:
        bounds = sprite.getchannel("A").getbbox()
        if bounds is None:
            raise FileNotFoundError("Empty inventory sprite")
        if bounds == (0, 0, *sprite.size):
            return png
        output = BytesIO()
        sprite.crop(bounds).save(output, format="PNG")
        return output.getvalue()


class InventoryCatalog:
    def __init__(self, db, references):
        self.refs = references
        catalog = references.read_bytes("static_data_get.bin")
        self.specs = {s["Id"]: s for s in item_definitions(catalog)}
        self.equipment = EquipmentDisplay(references, self.specs, catalog)
        self.names = self.equipment.names | NAMES
        for encoded in active_specs(db):
            spec = json.loads(encoded)
            self.specs[spec["Id"]] = spec
            self.names[spec["Id"]] = "Rustic but Precious Pin · trial"
        head = active_spec(db, references)
        if head:
            self.specs[VARIANT] = json.loads(head)
        self.has_icons = ICONS.available(references)

    def icon(self, ident):
        sprite = self.specs.get(ident, {}).get("SpriteName")
        frame = sprite.get("default") if isinstance(sprite, dict) else None
        if not frame or not self.has_icons:
            raise FileNotFoundError
        return inventory_icon(ICONS.read(self.refs, frame=frame))


class Sandbox:
    def __init__(self, db, references, catalog):
        self.db = db
        self.refs = references
        self.guard = Lock()
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("The save copy failed its integrity check.")
        if db.execute("SELECT schema_version FROM local_account WHERE id=1").fetchone() != (3,):
            raise ValueError("This preview requires a local schema-3 save.")
        self.account = AccountStore(db, references.directory)
        self.equipment = catalog.equipment
        self.specs = catalog.specs
        self.names = catalog.names
        self.has_icons = catalog.has_icons
        user = self.account.profile()["User"]
        self.original = {r["Id"]: r["Locked"] for k in INVENTORIES for r in user[k]}

    def rows(self):
        user = self.account.profile()["User"]
        equipped = gear_references(user["Characters"])
        training = {slot.get("ItemId") for slot in user.get("TrainingSlots", {}).values()}
        rows = []
        for group in INVENTORIES:
            for r in user[group]:
                ident, item = r["Id"], r["ItemId"]
                spec = self.specs.get(item, {})
                key = spec.get("Name", "")
                name = self.names.get(item) or (
                    spec.get("NameWithoutRarity") or key or f"Item {item}"
                ).replace("_", " ")
                rows.append(
                    dict(
                        id=ident,
                        spec=item,
                        name=name,
                        key=key,
                        group=GROUPS[group],
                        kind=spec.get("WeaponType") or spec.get("Type") or "",
                        amount=r["Amount"],
                        locked=r["Locked"],
                        original=self.original[ident],
                        equipped=ident in equipped,
                        breaks=r.get("LimitBreaks") or 0,
                        **(
                            self.equipment.facts(r, spec, training)
                            if group == "ItemWeapons"
                            else {}
                        ),
                    )
                )
        return rows, user["Cas"]

    def listing(self):
        with self.guard:
            rows, rev = self.rows()
            return dict(rows=rows, revision=rev, hasIcons=self.has_icons, equipmentView=True)

    def change(self, body):
        if (
            not isinstance(body, dict)
            or set(body) != {"id", "locked", "revision"}
            or type(body["id"]) is not int
            or body["id"] not in self.original
            or type(body["locked"]) is not bool
            or type(body["revision"]) is not int
        ):
            raise ValueError("Select a valid item copy.")
        with self.guard:
            if self.account.profile()["User"]["Cas"] != body["revision"]:
                return 409, {"error": "The copy changed in another tab. Reload before saving."}
            user = self.account.change_item_locks(
                {"itemIndexes": [body["id"]]},
                "inventory-preview:" + uuid.uuid4().hex,
                LOCK if body["locked"] else UNLOCK,
            )["User"]
            return 200, {"revision": user["Cas"]}


class Handler(PanelHandler):
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
        assets = {
            "/": ("equipment.html", "text/html; charset=utf-8"),
            "/equipment": ("equipment.html", "text/html; charset=utf-8"),
            "/equipment/preview": ("equipment.html", "text/html; charset=utf-8"),
            "/equipment-options.js": ("equipment-options.js", "text/javascript; charset=utf-8"),
            "/equipment-options.css": ("equipment-options.css", "text/css; charset=utf-8"),
            "/equipment.js": ("equipment.js", "text/javascript; charset=utf-8"),
            "/inventory-dom.js": ("inventory-dom.js", "text/javascript; charset=utf-8"),
            "/equipment.css": ("equipment.css", "text/css; charset=utf-8"),
            "/relics": ("relics.html", "text/html; charset=utf-8"),
            "/relics.js": ("relics.js", "text/javascript; charset=utf-8"),
            "/relics.css": ("relics.css", "text/css; charset=utf-8"),
            "/consumables": ("consumables.html", "text/html; charset=utf-8"),
            "/consumables.js": ("consumables.js", "text/javascript; charset=utf-8"),
            "/consumables.css": ("consumables.css", "text/css; charset=utf-8"),
        }
        try:
            if path in assets:
                name, mime = assets[path]
                return self.reply(200, mime, (STATIC / name).read_bytes())
            if path == "/brand.png":
                brand = self.server.brand_image
                if brand.is_file():
                    return self.reply(200, "image/png", brand.read_bytes())
                path = "/type-icon/inventory.png"
            if path == "/api/inventory":
                return self.list_json(self.server.sandbox.listing())
            if path == "/preview-status":
                return self.json(200, {"preview": "gt-inventory-sandbox"})
            if path == "/api/game/relics":
                return self.list_json(self.server.relics.info())
            if path == "/api/game/equipment":
                return self.list_json(self.server.equipment.info())
            if path == "/api/game/consumables":
                return self.list_json(self.server.consumables.info())
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
        if self.path not in (
            "/api/lock",
            "/api/close",
            "/api/game/relics",
            "/api/game/equipment",
            "/api/game/equipment/roll",
            "/api/game/consumables",
        ):
            return self.json(404, {"error": "Unknown action."})
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if (
                len(lengths) != 1
                or not 0 < int(lengths[0]) <= (4096 if self.path.startswith("/api/game/") else 512)
                or "Transfer-Encoding" in self.headers
            ):
                raise ValueError("Invalid request size.")
            raw = self.rfile.read(int(lengths[0]))
            if not self.allowed_host() or self.headers.get_all("Origin") != [
                "http://" + self.headers["Host"].removesuffix(":80")
            ]:
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
            if self.path == "/api/game/relics":
                status, result = self.server.relics.apply(payload)
            elif self.path == "/api/game/consumables":
                status, result = self.server.consumables.write(payload)
            elif self.path in ("/api/game/equipment", "/api/game/equipment/roll"):
                status, result = self.server.equipment.request(
                    payload, roll=self.path.endswith("/roll")
                )
            else:
                status, result = self.server.sandbox.change(payload)
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
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            self.catalog = InventoryCatalog(source, references)
        self.relics = RelicEditor(database, self.catalog)
        self.equipment = EquipmentOptionEditor(database, self.catalog)
        self.consumables = ConsumableEditor(database, self.catalog)
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
