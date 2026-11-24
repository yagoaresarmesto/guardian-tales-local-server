# SPDX-License-Identifier: Apache-2.0
"""Read and change native Tetis progression through the running game modes panel."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.raid_static import compress, digest, record_bytes
from guardian_tales.reference import ReferenceData
from guardian_tales.web_panel.server import WebPanel
from guardian_tales.web_panel.tetis import sprites
from tests.test_tetis_progress import catalog_data


class TetisPanelTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = directory / "custom-state.sqlite3"
        sqlite3.connect(self.db).close()
        content = json.dumps(catalog_data())
        checksum = digest(record_bytes("roguechess3", content))
        static = f"roguechess3\n{content}\n1\n{checksum}\n"
        (directory / "static_data_get.bin").write_bytes(compress(static.encode()))
        panel = WebPanel(ReferenceData(directory), 0, database=self.db)
        panel.start()
        self.addCleanup(panel.stop)
        self.origin = f"http://127.0.0.1:{panel.server_port}"

    def api(self, **body):
        request = Request(
            self.origin + "/api/tetis",
            data=json.dumps(body).encode() if body else None,
            headers={"Origin": self.origin, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_native_specialty_art_routes_and_optional_assets(self):
        with patch.object(sprites, "read", return_value=b"native sprite") as reader:
            for sheet, frame in [
                ("nodes", "roguechess_ability_category_common"),
                ("spells", "ic_rc_v2_summoner_spell_name_1"),
            ]:
                with urlopen(
                    f"{self.origin}/tetis/specialty/{sheet}/{frame}.png", timeout=5
                ) as response:
                    self.assertEqual(response.headers.get_content_type(), "image/png")
                    self.assertEqual(response.read(), b"native sprite")
                self.assertEqual(reader.call_args.kwargs, {"atlas": sheet, "frame": frame})
        for path in (
            "nodes/ic_rc_unknown.png",
            "items/ic_rc_unknown.png",
            "nodes/../roguechess.png",
        ):
            with self.assertRaises(HTTPError) as missing:
                urlopen(f"{self.origin}/tetis/specialty/{path}", timeout=5)
            self.assertEqual(missing.exception.code, 404)
            missing.exception.close()

    def test_dual_editor_stale_rejection_and_atomic_validation(self):
        before = self.api()
        first, second = before["seasons"]
        changes = dict(seasonId=2, clearedFloor=4, experience=20, abilities={"40101": 2})
        self.api(**changes, revision=second["revision"])
        current = self.api()["seasons"][1]
        self.assertEqual(
            (current["clearedFloor"], current["level"], current["nodes"][0]["points"]), (4, 3, 2)
        )
        self.assertNotEqual(current["revision"], second["revision"])
        with self.assertRaises(HTTPError) as stale:
            self.api(**changes, revision=second["revision"])
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        with self.assertRaises(HTTPError) as invalid:
            self.api(seasonId=2, clearedFloor=1, experience=0, revision=current["revision"])
        self.assertEqual(invalid.exception.code, 400)
        invalid.exception.close()
        self.assertEqual(self.api()["seasons"][1], current)
        self.api(seasonId=1, clearedFloor=1, revision=first["revision"])
        with urlopen(self.origin + "/tetis", timeout=5) as response:
            self.assertIn(b"Guardian Tactic Level", response.read())

    def test_loadout_change_in_another_season_invalidates_open_editor(self):
        archived, current = self.api()["seasons"]
        self.api(
            seasonId=current["id"],
            revision=current["revision"],
            artifactLevels={"8": 14},
            artifactId=8,
            spellId=1,
        )
        with self.assertRaises(HTTPError) as stale:
            self.api(seasonId=archived["id"], revision=archived["revision"], spellId=0)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        loaded = self.api()["loadout"]
        self.assertEqual(
            (loaded["artifacts"][0]["level"], loaded["artifactId"], loaded["spellId"]), (14, 8, 1)
        )
