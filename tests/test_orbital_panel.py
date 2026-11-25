# SPDX-License-Identifier: Apache-2.0
"""Orbital Lift progress edits through the unified dashboard on a disposable save."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.reference import ReferenceData
from guardian_tales.snapshots import CLIENT
from guardian_tales.state_lock import StateLock
from guardian_tales.village import MAX_REVISION
from guardian_tales.web_panel.server import WebPanel
from tests.test_inventory_panel import prepare_inventory


class OrbitalPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = self.enterContext(closing(sqlite3.connect(prepare_inventory(self.root))))
        self.original = self.profile()
        self.original["UserProgress"] = {
            "Cas": 17,
            "TowerInfinity": {"Floor": -1340, "Formation": {"Positions": [1, 4, 7, 15]}},
        }
        self.store_original()
        (self.root / "orbital_entry_catalog.json").write_text(
            json.dumps({"client": CLIENT, "floors": [1, 1341, 1400, 1500, 1501]})
        )
        panel = WebPanel(ReferenceData(self.root), 0, database=self.root / "server.sqlite3")
        panel.start()
        self.addCleanup(panel.stop)
        self.origin = f"http://127.0.0.1:{panel.server_port}"

    def profile(self):
        return json.loads(self.db.execute("SELECT profile FROM local_account").fetchone()[0])

    def store_original(self):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.original),))

    def api(self, body=None):
        request = Request(
            self.origin + "/api/orbital-lift",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Origin": self.origin, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_choose_next_floor_preserves_save_and_survives_reopening(self):
        state = self.api()
        self.assertEqual((state["clearedFloor"], state["nextFloor"]), (1340, 1341))
        self.assertEqual(state["floors"], [1, 1341, 1400, 1500])
        self.api(dict(version=state["version"], nextFloor=1341))
        self.assertEqual(self.profile(), self.original)
        for target in (1500, 1, 1341):
            state = self.api()
            self.api(dict(version=state["version"], nextFloor=target))
            self.assertEqual(self.api()["nextFloor"], target)
            self.original["UserProgress"]["TowerInfinity"]["Floor"] = target - 1
            self.original["UserProgress"]["Cas"] += 1
            self.assertEqual(self.profile(), self.original)

    def test_invalid_locked_stale_or_exhausted_updates_preserve_progress(self):
        state = self.api()
        body = dict(version=state["version"], nextFloor=1500)
        for value in (0, -1, 1501, 1499, True, "1400", 1.5):
            with self.subTest(value=value), self.assertRaises(HTTPError) as error:
                self.api(dict(body, nextFloor=value))
            self.assertEqual(error.exception.code, 400)
        with StateLock(self.root):
            self.assertFalse(self.api()["writable"])
            with self.assertRaises(HTTPError) as error:
                self.api(body)
            self.assertEqual(error.exception.code, 423)
        self.assertEqual(self.profile(), self.original)
        self.original["UserProgress"]["TowerInfinity"]["Floor"] = 1500
        self.original["UserProgress"]["Cas"] = MAX_REVISION
        self.store_original()
        state = self.api()
        self.assertEqual(state["nextFloor"], 1501)
        with self.assertRaises(HTTPError) as stale:
            self.api(body)
        self.assertEqual(stale.exception.code, 409)
        with self.assertRaises(HTTPError) as exhausted:
            self.api(dict(body, version=state["version"]))
        self.assertEqual(exhausted.exception.code, 400)
        self.assertEqual(self.profile(), self.original)
