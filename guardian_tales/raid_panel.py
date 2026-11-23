# SPDX-License-Identifier: Apache-2.0
"""Local browser controls for the same Raid and arena selections as the command line."""

import hashlib
import json
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from . import guild_raid, punchking, punchking_static, raid_custom, raid_static

WEB = Path(__file__).with_name("raid_web")
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/dka": ("dka.html", "text/html; charset=utf-8"),
    "/dka.js": ("dka.js", "text/javascript; charset=utf-8"),
    "/raid.css": ("raid.css", "text/css; charset=utf-8"),
    "/raid.js": ("raid.js", "text/javascript; charset=utf-8"),
}
BOSS_NAMES = {stage: name for name, stage in raid_custom.BOSS_STAGES.items()}
ELEMENT_NAMES = {values[0]: name for name, values in raid_custom.ELEMENTS.items()}


@lru_cache(maxsize=2)
def encounter_elements(body):
    tables = raid_static.records(raid_static.decode(body))[1]
    raid = json.loads(tables["guildraid2"][1])
    monsters = json.loads(tables["monsters"][1]) if "monsters" in tables else []
    elements = {row["Id"]: ELEMENT_NAMES.get(row.get("ElementalType")) for row in monsters}
    return {row["Id"]: elements.get(row.get("MonsterId")) for row in raid["BossDetails"]}


def season_view(season, elements):
    return {
        "id": season["season_id"],
        "hpPerBar": season["first_round"]["boss_hp_bar"],
        "bosses": [
            {
                "stage": row["stage_id"],
                "boss": BOSS_NAMES.get(row["stage_id"]),
                "element": elements.get(row["id"]),
            }
            for row in sorted(season["bosses"], key=lambda row: row["slot"])
        ],
    }


def map_image(references):
    return references.directory.parent / "resources/files/media/guildraid/raid_bg_02.png"


def panel_state(references):
    catalog = guild_raid.load_catalog(references)
    saved = guild_raid.load_selection(references) or {}
    ident = saved.get("season_id", catalog["default_season_id"])
    active = guild_raid.find_season(catalog, ident, saved or None)
    stock = guild_raid.find_season(catalog, ident)
    elements = encounter_elements(references.read_bytes("static_data_get.bin"))
    active_elements = elements
    custom = "custom_season" in saved
    if custom:
        # Resolve the exact published snapshot, including selections from older CLIs.
        digest = saved["static_data_sha256"]
        body = references.read_bytes(f"guild_raid_static_{digest}.bin")
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("The prepared Raid tables do not match the active selection")
        active_elements = encounter_elements(body)
    return {
        "active": season_view(active, active_elements),
        "custom": custom,
        "customHp": custom and active["round_set"] != stock["round_set"],
        "prepared": "static_data_revision" in saved,
        "revision": saved.get("static_data_revision", 0),
        "seasons": [
            season_view(s, elements)
            for s in sorted(catalog["seasons"], key=lambda s: s["season_id"])
        ],
        "bossNames": list(raid_custom.BOSS_STAGES),
        "elementNames": list(raid_custom.ELEMENTS),
        "hasMap": map_image(references).is_file(),
    }


def apply_selection(references, body):
    if not isinstance(body, dict) or not guild_raid.integer(body.get("revision"), 0):
        raise ValueError("A current Raid revision is required")
    revision = body["revision"]
    if body.get("mode") == "stock" and body.keys() == {"mode", "revision", "season"}:
        guild_raid.select_season(references, body["season"], expected_revision=revision)
    elif body.get("mode") == "custom" and body.keys() == {"mode", "revision", "lineup", "hpPerBar"}:
        lineup = raid_custom.validate_lineup(body["lineup"])
        guild_raid.select_season(
            references, lineup=lineup, hp_per_bar=body["hpPerBar"], expected_revision=revision
        )
    else:
        raise ValueError("Choose an original season or a four-boss custom lineup")


def arena_image(references):
    return (
        references.directory.parent
        / "resources/files/media/guildpunchking/guild_punchking_bg_00.jpg"
    )


def arena_state(references):
    catalog = punchking.load_catalog(references)
    selection = punchking_static.load_selection(references)
    return {
        "variants": sorted(catalog["variants"], key=lambda variant: variant["id"]),
        "active": {"variant": selection["variant"], "day": selection["day"]} if selection else None,
        "revision": selection["static_data_revision"] if selection else 0,
        "hasArt": arena_image(references).is_file(),
    }


def apply_arena(references, body):
    if (
        not isinstance(body, dict)
        or body.keys() != {"variant", "day", "revision"}
        or not punchking.integer(body["revision"])
    ):
        raise ValueError("Choose an arena variant and day using the current revision")
    punchking_static.select(
        references, body["variant"], body["day"], expected_revision=body["revision"]
    )


class RaidPanel(ThreadingHTTPServer):
    # Finish any selection being published when the backend exits.
    daemon_threads = False

    def __init__(self, references, port):
        super().__init__(("127.0.0.1", port), RaidPanelHandler)
        self.references = references

    def start(self):
        Thread(target=self.serve_forever, name="Raid web panel", daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


class RaidPanelHandler(BaseHTTPRequestHandler):
    timeout = 8

    def reply(self, status, mime, data):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def json(self, status, value):
        self.reply(status, "application/json; charset=utf-8", json.dumps(value).encode())

    def allowed_host(self):
        port = self.server.server_port
        hosts = self.headers.get_all("Host", [])
        valid = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            valid.update(("127.0.0.1", "localhost"))
        return len(hosts) == 1 and hosts[0] in valid

    def do_GET(self):
        if not self.allowed_host():
            self.json(
                403, {"error": "Open the panel using the local address printed by the backend."}
            )
            return
        try:
            if self.path in FILES:
                name, mime = FILES[self.path]
                self.reply(200, mime, (WEB / name).read_bytes())
            elif self.path == "/api/raid":
                self.json(200, panel_state(self.server.references))
            elif self.path == "/api/dka":
                self.json(200, arena_state(self.server.references))
            elif self.path == "/arena.jpg" and arena_image(self.server.references).is_file():
                self.reply(200, "image/jpeg", arena_image(self.server.references).read_bytes())
            elif self.path == "/map.png" and map_image(self.server.references).is_file():
                self.reply(200, "image/png", map_image(self.server.references).read_bytes())
            else:
                self.json(404, {"error": "Unknown panel resource"})
        except (ValueError, KeyError, TypeError, OSError) as error:
            self.json(503, {"error": f"Could not load panel data: {error}"})

    def do_POST(self):
        if self.path not in ("/api/raid", "/api/dka"):
            self.json(404, {"error": "Unknown panel action"})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if (
                len(lengths) != 1
                or "Transfer-Encoding" in self.headers
                or not 0 < int(lengths[0]) <= 4096
            ):
                raise ValueError("Invalid selection size")
            raw = self.rfile.read(int(lengths[0]))
        except (ValueError, OSError) as error:
            self.json(400, {"error": str(error)})
            return
        if not self.allowed_host() or self.headers.get_all("Origin") != [
            "http://" + self.headers["Host"].removesuffix(":80")
        ]:
            self.json(403, {"error": "Apply changes from the local panel."})
            return
        if self.headers.get_content_type() != "application/json":
            self.json(415, {"error": "Expected a JSON selection"})
            return
        try:
            body = json.loads(raw.decode("utf-8"))
            if self.path == "/api/dka":
                apply_arena(self.server.references, body)
            else:
                apply_selection(self.server.references, body)
        except (guild_raid.RaidSelectionChanged, punchking_static.ArenaSelectionChanged) as error:
            self.json(409, {"error": str(error)})
        except RuntimeError:
            self.json(409, {"error": "Another Raid change is in progress. Reload and try again."})
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            self.json(400, {"error": str(error)})
        except OSError as error:
            self.json(503, {"error": f"Could not save the selection: {error}"})
        else:
            self.json(200, {"applied": True})

    def log_message(self, format, *args):
        pass
