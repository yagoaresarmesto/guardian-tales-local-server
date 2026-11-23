# SPDX-License-Identifier: Apache-2.0
"""Guild Wars web settings share the CLI selection and protect stale edits."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales import guild_war
from guardian_tales import guild_war_static as war
from guardian_tales.reference import ReferenceData
from guardian_tales.web_panel.server import WebPanel
from tests.test_guild_raid import synthetic_catalog
from tests.test_guild_war import synthetic_war_static


class GuildWarPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.refs = ReferenceData(self.root)
        self.source = self.root / "static_data_get.bin"
        self.source.write_bytes(synthetic_war_static(synthetic_catalog()))
        server = WebPanel(self.refs, 0)
        server.start()
        self.addCleanup(server.stop)
        self.origin = f"http://127.0.0.1:{server.server_port}"

    def api(self, **fields):
        request = Request(
            self.origin + "/api/guild-war",
            data=json.dumps(fields).encode() if fields else None,
            headers={"Origin": self.origin, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_web_cli_round_trip_and_stale_disable(self):
        original = self.source.read_bytes()
        first = self.api()
        self.assertEqual(first["castles"], [{"id": 1, "grade": 1}, {"id": 2, "grade": 4}])
        self.assertEqual(list(self.root.iterdir()), [self.source])
        edit = dict(action="enable", phase="multi-offense", round="prep", castle=0, skipBasic=True)
        self.api(**edit, revision=first["revision"])
        active = self.api()
        output = io.StringIO()
        with redirect_stdout(output):
            guild_war.main(["status", "--reference-dir", str(self.root)])
        cli = json.loads(output.getvalue())
        self.assertEqual(active["selection"], {k: cli[k] for k in active["selection"]})
        with redirect_stdout(io.StringIO()):
            guild_war.main(
                [
                    "enable",
                    "--phase",
                    "multi-defense",
                    "--defend-castle",
                    "2",
                    "--round",
                    "combat",
                    "--reference-dir",
                    str(self.root),
                ]
            )
        with self.assertRaises(HTTPError) as stale:
            self.api(action="disable", revision=active["revision"])
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        saved = self.api()
        self.assertEqual(saved["selection"]["local_defense_castle"], 2)
        self.source.unlink()
        self.assertTrue(self.api()["catalogError"])
        self.api(action="disable", revision=saved["revision"])
        self.assertIsNone(war.load_selection(self.refs))
        self.source.write_bytes(original)
        self.assertIsNone(self.api()["catalogError"])

    def test_wrong_phase_castle_and_stale_revision_preserve_settings(self):
        edit = dict(action="enable", phase="multi-defense", round="prep", castle=2, skipBasic=True)
        self.api(**edit, revision="disabled")
        saved = self.api()
        for changes in (
            dict(phase="coop-defense"),
            dict(castle=101),
            dict(castle=True),
            dict(round="unknown"),
            dict(skipBasic=None),
            dict(revision=None),
        ):
            with self.subTest(changes=changes), self.assertRaises(HTTPError) as rejected:
                self.api(**(dict(edit, revision=saved["revision"]) | changes))
            self.assertEqual(rejected.exception.code, 400)
            rejected.exception.close()
        with war.war_lock(self.refs), self.assertRaises(HTTPError) as busy:
            self.api(action="disable", revision=saved["revision"])
        self.assertEqual(busy.exception.code, 409)
        busy.exception.close()
        self.assertEqual(self.api(), saved)

    def test_bootstrap_refresh_cannot_reenable_a_concurrently_disabled_trial(self):
        selection = war.enable(self.refs)
        (self.root / war.SELECTION).write_text(json.dumps(dict(selection, overlay_policy=6)))

        def read_parent(references):
            war.disable(references)
            return self.source.read_bytes()

        with patch.object(war, "base_body", side_effect=read_parent):
            self.assertIsNone(war.bootstrap_override(self.refs, "static_data_get.bin", None))
        self.assertIsNone(war.load_selection(self.refs))
