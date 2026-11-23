# SPDX-License-Identifier: Apache-2.0
"""Season selection reveals only Kama-ZONE's menu calendar and never account state."""

import copy
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.__main__ import main
from guardian_tales.assets import ResourceLibrary, handler_for
from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.kamazone import FIELDS, INACTIVE, REGION, SELECTION, load
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from tests import test_andras_trial as andras_fixture
from tests.test_snapshots import request, synthetic_snapshot

NOW = datetime(2030, 11, 23, 14, 0, tzinfo=timezone.utc)


class KamazoneTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = self.enterContext(closing(sqlite3.connect(":memory:")))
        self.session = BootstrapSession(GuestStore(self.db, self.root))
        self.refs = self.session.store.references
        self.enterContext(patch("guardian_tales.kamazone.utc_now", return_value=NOW))
        self.tables = {
            "kamazonland2": {
                "Seasons": [
                    dict(
                        Id=41 + i,
                        SeasonName="mall_season_name_" + str(i + 1),
                        SeasonDateId=7000101 + i,
                        MiniSeasonGroupId=1,
                        Banner=json.dumps(
                            {
                                "enUS": f"media/kamazon_land/v3.{(18,30,47)[i]}_kamazon_land_event_banner_enUS.png"
                            }
                        ),
                    )
                    for i in range(3)
                ]
                + [dict(Id=2041, SeasonName="mall_season_name_1", SeasonDateId=7100033)],
                "Artifacts": [{"Id": 900, "Keep": True}],
                "MiniSeasons": [{"Id": 101, "MiniSeasonGroupId": 1}],
            },
            "seasondate": {
                "EventPeriod": [
                    dict(
                        Id=ident,
                        **{
                            key: dict(KakaoGlobal=value, KakaoKorea=value)
                            for key, value in zip(FIELDS, INACTIVE)
                        },
                    )
                    for ident in (7000101, 7000102, 7000103, 5500001)
                ]
                + [
                    dict(
                        Id=7100033,
                        **{key: dict(Kong=value) for key, value in zip(FIELDS, INACTIVE)},
                    )
                ],
                "Unrelated": {"Keep": True},
            },
            "untouched": {"value": [1, 2, 3]},
            "__checksum__": "original",
        }
        self.write_source()

    def write_source(self):
        self.source = compress(
            "".join(
                f"{name}\n{text}\n31\n{digest(text.encode())}\n"
                for name, text in ((k, json.dumps(v)) for k, v in self.tables.items())
            ).encode()
        )
        (self.root / "static_data_get.bin").write_bytes(self.source)
        (self.root / "static_data_check.bin").write_bytes(b'{"UpToDate":true}')

    def cli(self, *args, reference_dir=None):
        with redirect_stdout(io.StringIO()) as output:
            main(["kamazone", *args, "--reference-dir", str(reference_dir or self.root)])
        return json.loads(output.getvalue())

    def reject(self, *args):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.cli(*args)
        self.assertEqual(error.exception.code, 2)

    def fetch(self, route="/static-data/get", body=None):
        return self.session.handle(request(route, body or {})).body

    def decoded(self):
        return records(decode(self.fetch()))[1]

    def test_unconfigured_bootstrap_is_byte_identical_and_reads_create_no_files(self):
        before = list(self.db.iterdump())
        files = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(self.fetch(), self.source)
        for action in ("list", "status", "disable"):
            value = self.cli(action)
            self.assertIsNone(value["selected_season_id"])
            self.assertFalse(value["menu_active_now"])
            self.assertFalse(value["restart_backend_and_game_required"])
            self.assertEqual([r["season_id"] for r in value["seasons"]], [41, 42, 43])
        self.assertEqual(
            [r["name"] for r in value["seasons"]],
            ["Valentine Season", "Lifeguard Season", "Mecha Harpy Scintilla Season"],
        )
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, files)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_select_changes_only_selected_global_dates_and_never_opens_an_account(self):
        before = list(self.db.iterdump())
        with patch("sqlite3.connect", side_effect=AssertionError("CLI must not open any database")):
            value = self.cli("select", "--season-id", "41")
        tables = self.decoded()
        calendar = json.loads(tables["seasondate"][1])
        expected = copy.deepcopy(self.tables["seasondate"])
        for key, date in value["local_period"].items():
            expected["EventPeriod"][0][key][REGION] = date
        self.assertEqual(calendar, expected)
        for name in self.tables.keys() - {"seasondate", "__checksum__"}:
            self.assertEqual(tables[name], records(decode(self.source))[1][name])
        self.assertEqual((self.root / "static_data_get.bin").read_bytes(), self.source)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertTrue(value["menu_active_now"])
        self.assertTrue(value["restart_backend_and_game_required"])
        self.assertFalse(value["saved_account_modified"])

    def test_get_and_check_share_checksum_and_other_static_routes_keep_parent_body(self):
        self.cli("select", "--season-id", "42")
        checksum = self.decoded()["__checksum__"][1]
        for supplied, expected in ((checksum, True), ("old", False)):
            reply = json.loads(self.fetch("/static-data/check-update", dict(Checksum=supplied)))
            self.assertEqual(reply["Checksum"], checksum)
            self.assertEqual(reply["UpToDate"], expected)
        from guardian_tales.kamazone import bootstrap_seed

        def parent(refs, name, body):
            return b"unchanged resource URL"

        self.assertEqual(
            bootstrap_seed(self.refs, "resource_urls.bin", {}, parent), b"unchanged resource URL"
        )

    def test_switch_and_disable_restore_original_calendar_with_advancing_revisions(self):
        revisions = []
        for action, ident in (("select", 41), ("select", 42), ("disable", None)):
            self.cli(action, *([] if ident is None else ["--season-id", str(ident)]))
            tables = self.decoded()
            revisions.append(tables["seasondate"][2])
            calendar = json.loads(tables["seasondate"][1])
            expected = copy.deepcopy(self.tables["seasondate"])
            if ident:
                selected = load(self.refs)
                for key, date in selected["period"].items():
                    expected["EventPeriod"][ident - 41][key][REGION] = date
            self.assertEqual(calendar, expected)
        self.assertTrue(revisions[0] < revisions[1] < revisions[2])
        self.assertEqual(tables["seasondate"][1], records(decode(self.source))[1]["seasondate"][1])

    def test_repeated_commands_are_noops_and_expired_selection_can_be_renewed(self):
        self.cli("select", "--season-id", "41")
        path = self.root / SELECTION
        before = path.read_bytes()
        self.assertFalse(
            self.cli("select", "--season-id", "41")["restart_backend_and_game_required"]
        )
        self.assertEqual(path.read_bytes(), before)
        with patch("guardian_tales.kamazone.utc_now", return_value=NOW + timedelta(days=22)):
            self.assertFalse(self.cli("status")["menu_active_now"])
            self.assertTrue(self.cli("select", "--season-id", "41")["menu_active_now"])
        self.assertEqual(load(self.refs)["generation"], 2)
        self.cli("disable")
        before = path.read_bytes()
        self.assertFalse(self.cli("disable")["restart_backend_and_game_required"])
        self.assertEqual(path.read_bytes(), before)

    def test_overlapping_unselected_season_is_hidden_only_in_global(self):
        row = self.tables["seasondate"]["EventPeriod"][1]
        dates = (NOW - timedelta(days=1), NOW + timedelta(days=1), NOW + timedelta(days=8))
        for key, date in zip(FIELDS, dates):
            row[key][REGION] = date.isoformat()
        self.write_source()
        self.cli("select", "--season-id", "41")
        calendar = json.loads(self.decoded()["seasondate"][1])
        for key, date in zip(FIELDS, INACTIVE):
            self.assertEqual(calendar["EventPeriod"][1][key][REGION], date)
            self.assertEqual(calendar["EventPeriod"][1][key]["KakaoKorea"], row[key]["KakaoKorea"])
        self.cli("disable")
        self.assertEqual(json.loads(self.decoded()["seasondate"][1]), self.tables["seasondate"])

    def test_content_binding_fails_closed_and_disable_recovers_on_changed_content(self):
        self.cli("select", "--season-id", "41")
        self.tables["untouched"]["value"].append(4)
        self.write_source()
        with self.assertRaises(PacketError):
            self.fetch()
        status = self.cli("status")
        self.assertFalse(status["content_matches"])
        self.assertFalse(status["menu_active_now"])
        self.cli("disable")
        self.assertEqual(
            self.decoded()["seasondate"][1], records(decode(self.source))[1]["seasondate"][1]
        )

    def test_unknown_regional_or_malformed_cli_selection_cannot_publish(self):
        before = list(self.db.iterdump())
        for args in (
            ("select",),
            ("select", "--season-id", "2041"),
            ("select", "--season-id", "0"),
            ("select", "--season-id", "99"),
            ("status", "--season-id", "41"),
        ):
            self.reject(*args)
        self.assertFalse((self.root / SELECTION).exists())
        self.assertEqual(list(self.db.iterdump()), before)

    def test_malformed_configuration_and_revision_overflow_do_not_write_accounts(self):
        self.cli("select", "--season-id", "41")
        path = self.root / SELECTION
        original = load(self.refs)
        before = list(self.db.iterdump())
        for change in (
            {"version": True},
            {"generation": 0},
            {"generation": 0x7FFFFFFF},
            {"season_id": True},
            {"source_sha256": "bad"},
            {"period": None},
        ):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(PacketError):
                self.fetch()
        path.write_text("x" * 4097)
        with self.assertRaises(PacketError):
            self.fetch()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_missing_ambiguous_or_invalid_source_calendar_rejects_before_publication(self):
        original = copy.deepcopy(self.tables)
        for mode in ("missing", "duplicate", "naive", "wrong_order"):
            if mode == "missing":
                self.tables.pop("kamazonland2")
            elif mode == "duplicate":
                self.tables["seasondate"]["EventPeriod"].append(
                    copy.deepcopy(self.tables["seasondate"]["EventPeriod"][0])
                )
            elif mode == "naive":
                self.tables["seasondate"]["EventPeriod"][0]["From"][REGION] = "2000-01-01T00:00:00"
            else:
                self.tables["seasondate"]["EventPeriod"][0]["To"][REGION] = INACTIVE[0]
            self.write_source()
            self.reject("select", "--season-id", "41")
            self.assertFalse((self.root / SELECTION).exists())
            self.tables = copy.deepcopy(original)

    def test_atomic_publication_failure_preserves_previous_selection_and_removes_temporary_file(
        self,
    ):
        self.cli("select", "--season-id", "41")
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch(
            "guardian_tales.punchking_static.atomic_replace",
            side_effect=OSError("synthetic failure"),
        ):
            self.reject("select", "--season-id", "42")
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)

    def test_selection_does_not_claim_unsupported_gameplay_or_create_progress(self):
        self.cli("select", "--season-id", "41")
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.fetch("/kamazonland/challenge", dict(Difficulty=1))
        self.assertEqual(list(self.db.iterdump()), before)

    def test_andras_overlay_composes_without_changing_its_configuration_or_account(self):
        f = andras_fixture.AndrasTrialTests()
        self.addCleanup(f.doCleanups)
        f.setUp()
        for name in ("kamazonland2", "seasondate"):
            f.tables[name] = copy.deepcopy(self.tables[name])
        f.write_source()
        f.cli("enable")
        before = f.session.handle(request("/static-data/get", {})).body
        saved = list(f.db.iterdump())
        config = {p.name: p.read_bytes() for p in f.refs.iterdir()}
        self.cli("select", "--season-id", "43", reference_dir=f.refs)
        after = f.session.handle(request("/static-data/get", {})).body
        old, new = records(decode(before))[1], records(decode(after))[1]
        for name in old.keys() - {"seasondate", "__checksum__"}:
            self.assertEqual(new[name], old[name])
        self.assertEqual(list(f.db.iterdump()), saved)
        self.assertTrue(all((f.refs / name).read_bytes() == raw for name, raw in config.items()))


class KamazonePreviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = KamazoneTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.db, self.session = self.fixture.db, self.fixture.session
        snapshot = synthetic_snapshot()
        # An older saved mode state must remain stored verbatim while the preview
        # uses its separate, unsaved idle view for the locally selected season.
        snapshot["profile"]["UserKamazonLand"] = {
            "SeasonId": 7,
            "SilverCoin": 123,
            "Progress": {"Floor": 3},
        }
        with self.db:
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1", (json.dumps(snapshot["profile"]),)
            )
        self.session.signed_in = True

    def call(self, body=None):
        packet = self.session.handle(
            request("/kamazonland/enter", {"IsPartial": False} if body is None else body)
        )
        self.assertEqual((packet.packet_type, packet.body_type, packet.sequence_id), (1, 1, 12))
        return json.loads(packet.body)

    def test_events_automatic_full_and_partial_entry_are_read_only_idle_previews(self):
        self.fixture.cli("select", "--season-id", "43")
        before, changes = list(self.db.iterdump()), self.db.total_changes
        files = {p.name: p.read_bytes() for p in self.fixture.root.iterdir()}
        for partial in (False, True, False):
            reply = self.call({"IsPartial": partial})
            self.assertEqual(set(reply), {"NewSeason", "UserKamazonLand"})
            self.assertFalse(reply["NewSeason"])
            user = reply["UserKamazonLand"]
            self.assertEqual((user["SeasonId"], user["MiniSeasonId"]), (43, 101))
            self.assertEqual(user["Progress"], {"Floor": 0, "CurrentNodeId": 0, "Concluded": True})
            self.assertEqual(user["Likeability"], {"Points": 0, "ClaimedRewardStep": 0})
            self.assertEqual(user["Characters"], [])
            self.assertEqual(user["Nodes"], {})
            self.assertTrue(
                all(
                    user[key] == 0
                    for key in (
                        "SilverCoin",
                        "KamazonPoint",
                        "KamazonPointTotal",
                        "KamazonTicket",
                        "KamazonEventPoint",
                    )
                )
            )
        self.assertEqual((list(self.db.iterdump()), self.db.total_changes), (before, changes))
        self.assertEqual({p.name: p.read_bytes() for p in self.fixture.root.iterdir()}, files)

    def test_switching_selected_season_refreshes_the_view_without_creating_saved_progress(self):
        for ident in (41, 42, 43):
            self.fixture.cli("select", "--season-id", str(ident))
            self.assertEqual(self.call()["UserKamazonLand"]["SeasonId"], ident)
        self.assertEqual(self.session.store.account.profile()["UserKamazonLand"]["SeasonId"], 7)

    def test_entry_requires_authentication_and_completed_prologue(self):
        self.fixture.cli("select", "--season-id", "43")
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.call()
        self.session.signed_in = True
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        with self.assertRaises(PacketError):
            self.call()

    def test_entry_rejects_malformed_parameters_without_writes(self):
        self.fixture.cli("select", "--season-id", "43")
        before = list(self.db.iterdump())
        for body in (
            {},
            [],
            {"IsPartial": 0},
            {"IsPartial": "false"},
            {"IsPartial": False, "x": 1},
        ):
            with self.assertRaises(PacketError):
                self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_unconfigured_disabled_expired_or_mismatched_preview_fails_closed(self):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call()
        self.fixture.cli("select", "--season-id", "43")
        with patch("guardian_tales.kamazone.utc_now", return_value=NOW + timedelta(days=22)):
            with self.assertRaises(PacketError):
                self.call()
        self.fixture.tables["untouched"]["value"].append(4)
        self.fixture.write_source()
        with self.assertRaises(PacketError):
            self.call()
        self.fixture.cli("disable")
        with self.assertRaises(PacketError):
            self.call()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_missing_or_ambiguous_mini_season_cannot_fabricate_an_identity(self):
        for minis in (
            None,
            [],
            [{"Id": 0, "MiniSeasonGroupId": 1}],
            [{"Id": 101, "MiniSeasonGroupId": 1}] * 2,
        ):
            self.fixture.tables["kamazonland2"]["MiniSeasons"] = minis
            self.fixture.write_source()
            self.fixture.cli("select", "--season-id", "43")
            with self.assertRaises(PacketError):
                self.call()

    def test_preview_does_not_enable_challenges_battles_shops_or_rewards(self):
        self.fixture.cli("select", "--season-id", "43")
        self.call()
        before = list(self.db.iterdump())
        for route in (
            "/kamazonland/challenge",
            "/kamazonland/start-stage",
            "/kamazonland/conclude",
            "/kamazonland/gacha",
            "/kamazonland/take-likeability",
        ):
            with self.assertRaises(PacketError):
                self.session.handle(request(route, {}))
        self.assertEqual(list(self.db.iterdump()), before)


class KamazoneBannerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = KamazoneTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.path = (
            "/master-global-v3.57.0/media/kamazon_land/v3.18_kamazon_land_event_banner_enUS.png"
        )
        self.library = ResourceLibrary([])

    def server(self, references=True):
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            handler_for(self.library, reference_dir=self.fixture.root if references else None),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:" + str(server.server_address[1])

    def error(self, url, code):
        with self.assertRaises(HTTPError) as error:
            urlopen(url, timeout=3)
        self.assertEqual(error.exception.code, code)
        error.exception.close()

    def test_generated_preview_is_a_valid_png_and_serves_head_ranges_and_etags_without_files(self):
        self.fixture.cli("select", "--season-id", "41")
        before = {p.name: p.read_bytes() for p in self.fixture.root.iterdir()}
        base = self.server()
        with urlopen(base + self.path, timeout=3) as response:
            data = response.read()
            etag = response.headers["ETag"]
            self.assertEqual(response.headers["Content-Type"], "image/png")
        import struct

        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack_from(">II", data, 16), (720, 192))
        with urlopen(Request(base + self.path, method="HEAD"), timeout=3) as response:
            self.assertEqual(int(response.headers["Content-Length"]), len(data))
            self.assertEqual(response.read(), b"")
        with urlopen(
            Request(base + self.path, headers={"Range": "bytes=10-19"}), timeout=3
        ) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), data[10:20])
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(base + self.path, headers={"If-None-Match": etag}), timeout=3)
        self.assertEqual(error.exception.code, 304)
        error.exception.close()
        self.assertEqual({p.name: p.read_bytes() for p in self.fixture.root.iterdir()}, before)

    def test_only_selected_declared_missing_banner_is_generated(self):
        base = self.server()
        self.error(base + self.path, 404)
        self.fixture.cli("select", "--season-id", "42")
        self.error(base + self.path, 404)
        with urlopen(base + self.path.replace("v3.18_", "v3.30_"), timeout=3) as response:
            self.assertEqual(response.status, 200)
        for path in (
            "/server.sqlite3",
            "/%2e%2e/server.sqlite3",
            "/media/kamazon_land/v9.99_kamazon_land_event_banner_enUS.png",
        ):
            self.error(base + path, 404)
        self.fixture.cli("disable")
        self.error(base + self.path.replace("v3.18_", "v3.30_"), 404)

    def test_cdn_without_reference_option_keeps_manifest_only_behavior(self):
        self.fixture.cli("select", "--season-id", "41")
        self.error(self.server(references=False) + self.path, 404)

    def test_preserved_manifest_banner_always_takes_precedence(self):
        self.fixture.cli("select", "--season-id", "41")
        path = self.fixture.root / "stock.png"
        path.write_bytes(b"preserved stock image")
        self.library.files[self.path.split("v3.57.0/", 1)[1]] = (path, "synthetic")
        with urlopen(self.server() + self.path, timeout=3) as response:
            self.assertEqual(response.read(), b"preserved stock image")
        self.assertEqual(path.read_bytes(), b"preserved stock image")

    def test_mismatched_content_rejects_preview_instead_of_serving_other_private_files(self):
        self.fixture.cli("select", "--season-id", "41")
        self.fixture.tables["untouched"]["value"].append(4)
        self.fixture.write_source()
        base = self.server()
        self.error(base + self.path, 503)
        self.error(base + "/private.key", 404)
