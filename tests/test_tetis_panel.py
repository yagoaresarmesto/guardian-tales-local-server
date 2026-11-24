# SPDX-License-Identifier: Apache-2.0
"""Read and change native Tetis progression through the running game modes panel."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.raid_static import compress, digest, record_bytes
from guardian_tales.reference import ReferenceData
from guardian_tales.web_panel.server import WebPanel
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
