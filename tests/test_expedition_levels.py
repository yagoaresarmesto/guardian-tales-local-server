# SPDX-License-Identifier: Apache-2.0
"""Per-stage enemy levels are reversible static overlays, never save edits."""

import copy
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.__main__ import main
from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.expedition import TRIAL
from guardian_tales.expedition_levels import (
    MAX_CONFIG_BYTES,
    SELECTION,
    catalog,
    load_levels,
    prepare,
)
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from guardian_tales.web_panel.expedition import artwork
from guardian_tales.web_panel.routes import media_resource
from guardian_tales.web_panel.server import WebPanel
from tests.test_snapshots import request

STAGE = 250011001
OTHER = 250011002


class ExpeditionLevelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = self.enterContext(closing(sqlite3.connect(":memory:")))
        self.session = BootstrapSession(GuestStore(self.db, self.root))
        self.refs = self.session.store.references
        self.tables = {
            "unlockfeature": [
                {"Id": n, "VersionFrom": {"KakaoGlobal": "v9.99"}, "Value": 38} for n in (31, 110)
            ],
            "expedition": {"Districts": [{"Id": 1, "StageIds": [STAGE, OTHER]}]},
            "stages": [
                {
                    "Id": STAGE,
                    "Name": "trial_one",
                    "StandardLevel": {"Default": 100, "KakaoKorea": 90, "Switch": 85},
                    "StageExorcism": 20,
                    "Time": 100,
                },
                {
                    "Id": OTHER,
                    "Name": "trial_two",
                    "StandardLevel": {"Default": 90, "KakaoGlobal": 110},
                    "Time": 100,
                },
                {"Id": 100010001, "StandardLevel": {"Default": 1}},
            ],
            "exps2": {"LevelExps": [{"Level": n, "TotalExps": (n + 1) * 37} for n in range(220)]},
            "expeditionbattle": {
                "Monsters": [{"Id": 101, "SpecId": 100001}],
                "WaveSets": [{"Id": 1}],
            },
            "constants": {"ChangeNickCost": 1200, "Untouched": 42},
            "guildraid2": {"Seasons": [{"Id": 42}]},
            "__checksum__": "original",
        }
        self.write_source()
        (self.root / TRIAL).touch()

    def write_source(self):
        self.source = compress(
            "".join(
                f"{name}\n{text}\n31\n{digest(text.encode())}\n"
                for name, text in ((name, json.dumps(value)) for name, value in self.tables.items())
            ).encode()
        )
        (self.root / "static_data_get.bin").write_bytes(self.source)
        (self.root / "static_data_check.bin").write_text('{"UpToDate":true}')

    def cli(self, *args):
        with redirect_stdout(io.StringIO()) as output:
            main(["expedition", *args, "--reference-dir", str(self.root)])
        return json.loads(output.getvalue())

    def reject_cli(self, *args):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.cli(*args)
        self.assertEqual(error.exception.code, 2)

    def get(self):
        return self.session.handle(request("/static-data/get", {})).body

    def stage_rows(self, body):
        return json.loads(records(decode(body))[1]["stages"][1])

    def open_panel(self):
        panel = WebPanel(self.refs, 0)
        panel.start()
        self.addCleanup(panel.stop)
        origin = f"http://127.0.0.1:{panel.server_port}"

        def api(body=None):
            req = Request(
                origin + "/api/expedition",
                data=None if body is None else json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "Origin": origin},
            )
            with urlopen(req, timeout=5) as reply:
                return json.load(reply)

        return api

    @unittest.skipUnless(find_spec("PIL"), "Pillow is optional for the panel")
    def test_panel_serves_distinct_journal_scenes_from_the_local_pack(self):
        from PIL import Image

        source = self.root / "static_data_get.bin"
        sample = Image.new("RGBA", (200, 100), (23, 45, 67, 255))
        for slug, texture, size in (
            ("journey", "expedition_bg_event_clara_smile_set_01", (960, 370)),
            ("camp", "expedition_bg_forest_night", (480, 180)),
        ):
            reader, mime = media_resource(f"/expedition/{slug}.jpg")
            with self.subTest(slug=slug):
                with self.assertRaises(FileNotFoundError):
                    reader(self.refs)
                with (
                    patch.object(type(artwork.EXPEDITION), "available", return_value=True),
                    patch.object(type(artwork.EXPEDITION), "path", return_value=source),
                    patch.object(artwork, "bundle_texture", return_value=sample) as read,
                ):
                    with Image.open(io.BytesIO(reader(self.refs))) as image:
                        self.assertEqual(
                            (mime, image.format, image.size), ("image/jpeg", "JPEG", size)
                        )
                    reader(self.refs)
                    read.assert_called_once_with(source, texture)

    def test_panel_and_cli_share_levels_revisions_and_distinct_originals(self):
        api = self.open_panel()
        files = {p.name: p.read_bytes() for p in self.root.iterdir()}
        initial = api()
        self.assertEqual(initial["stages"], self.cli("list")["stages"])
        self.assertEqual(initial["max_enemy_level"], 220)
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, files)
        edit = dict(action="set-level", scope="all", level=220, revision=initial["revision"])
        api(edit)
        self.assertEqual([r["enemy_level"] for r in self.cli("list")["stages"]], [220, 220])
        edit["revision"] = api()["revision"]
        api(edit)
        self.assertEqual(api()["revision"], edit["revision"])
        self.cli("set-level", "--stage", str(STAGE), "--level", "1")
        restore = dict(
            action="restore-level", scope="stage", stage=OTHER, revision=edit["revision"]
        )
        with self.assertRaises(HTTPError) as stale:
            api(restore)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        api(dict(restore, revision=api()["revision"]))
        partial = api()
        self.assertEqual([r["enemy_level"] for r in partial["stages"]], [1, 111])
        api(dict(action="restore-level", scope="all", revision=partial["revision"]))
        self.assertEqual(api()["stages"], initial["stages"])
        self.assertEqual(self.stage_rows(self.get()), self.tables["stages"])
        self.assertEqual((self.root / "static_data_get.bin").read_bytes(), self.source)

    def test_panel_rejects_invalid_scopes_levels_and_setting_when_trial_is_disabled(self):
        api = self.open_panel()
        edit = dict(scope="stage", action="set-level", stage=STAGE, level=1, revision=0)
        for changes in (
            dict(scope="all"),
            dict(stage=None),
            dict(stage=True),
            dict(stage=123),
            dict(level=None),
            dict(level=True),
            dict(level=0),
            dict(level=221),
            dict(action="list"),
        ):
            with self.subTest(changes=changes), self.assertRaises(HTTPError) as error:
                api(dict(edit, **changes))
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        api(edit)
        (self.root / TRIAL).unlink()
        state = api()
        self.assertFalse(state["trial_enabled"])
        with self.assertRaises(HTTPError) as disabled:
            api(dict(edit, revision=state["revision"]))
        self.assertEqual(disabled.exception.code, 400)
        disabled.exception.close()
        api(dict(action="restore-level", scope="stage", stage=STAGE, revision=state["revision"]))
        self.assertFalse(any(row["overridden"] for row in api()["stages"]))

    def test_list_uses_original_global_levels_without_creating_configuration_or_save(self):
        files = {p.name: p.read_bytes() for p in self.root.iterdir()}
        before = list(self.db.iterdump())
        result = self.cli("list")
        self.assertEqual(result["max_enemy_level"], 220)
        self.assertEqual([s["stage_id"] for s in result["stages"]], [STAGE, OTHER])
        self.assertEqual([s["enemy_level"] for s in result["stages"]], [101, 111])
        self.assertFalse(any(s["overridden"] for s in result["stages"]))
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, files)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_level_130_changes_only_selected_global_stage_and_static_checksums(self):
        result = self.cli("set-level", "--stage", str(STAGE), "--level", "130")
        self.assertEqual(result["stages"][0]["enemy_level"], 130)
        body, checksum = prepare(self.source, *load_levels(self.refs))
        expected = copy.deepcopy(self.tables["stages"])
        expected[0]["StandardLevel"]["KakaoGlobal"] = 129
        self.assertEqual(self.stage_rows(body), expected)
        original, updated = records(decode(self.source))[1], records(decode(body))[1]
        for name in original.keys() - {"stages", "__checksum__"}:
            self.assertEqual(updated[name], original[name])
        self.assertNotEqual(checksum, "original")
        self.assertEqual((self.root / "static_data_get.bin").read_bytes(), self.source)

    def test_partial_and_full_restoration_preserve_other_overrides_and_advance_revision(self):
        revisions = []
        for args, expected in (
            (("set-level", "--stage", str(STAGE), "--level", "130"), [129, 110]),
            (("set-level", "--stage", str(OTHER), "--level", "90"), [129, 89]),
            (("restore-level", "--stage", str(STAGE)), [100, 89]),
            (("restore-level", "--all"), [100, 110]),
        ):
            self.cli(*args)
            body, _ = prepare(self.source, *load_levels(self.refs))
            rows = self.stage_rows(body)
            self.assertEqual(
                [
                    r["StandardLevel"].get("KakaoGlobal", r["StandardLevel"]["Default"])
                    for r in rows[:2]
                ],
                expected,
            )
            revisions.append(records(decode(body))[1]["stages"][2])
        self.assertEqual(revisions, [32, 33, 34, 35])
        self.assertEqual(self.stage_rows(body), self.tables["stages"])
        self.assertEqual(load_levels(self.refs), (4, ()))
        self.assertEqual((self.root / "static_data_get.bin").read_bytes(), self.source)

    def test_bootstrap_get_check_and_runtime_changes_compose_without_database_writes(self):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.db.execute("PRAGMA query_only=ON")
        old_checksum = None
        for action in (
            ("set-level", "--stage", str(STAGE), "--level", "130"),
            ("set-level", "--stage", str(STAGE), "--level", "120"),
            ("restore-level", "--all"),
        ):
            self.cli(*action)
            body = self.get()
            tables = records(decode(body))[1]
            checksum = tables["__checksum__"][1]
            self.assertNotEqual(checksum, old_checksum)
            self.assertEqual(
                json.loads(tables["constants"][1]), {"ChangeNickCost": 0, "Untouched": 42}
            )
            self.assertTrue(
                all(
                    row["VersionFrom"]["KakaoGlobal"] == "v3.57"
                    for row in json.loads(tables["unlockfeature"][1])
                )
            )
            for value, expected in ((checksum, True), (old_checksum, False)):
                reply = json.loads(
                    self.session.handle(
                        request("/static-data/check-update", {"Checksum": value})
                    ).body
                )
                self.assertEqual(reply["Checksum"], checksum)
                self.assertEqual(reply["UpToDate"], expected)
            old_checksum = checksum
        self.assertEqual(self.stage_rows(body), self.tables["stages"])
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_missing_configuration_and_disabled_trial_retain_existing_behavior(self):
        baseline = self.get()
        self.assertIsNone(load_levels(self.refs))
        self.cli("set-level", "--stage", str(STAGE), "--level", "130")
        (self.root / TRIAL).unlink()
        self.assertEqual(self.stage_rows(self.get()), self.tables["stages"])
        (self.root / TRIAL).touch()
        self.assertNotEqual(self.get(), baseline)

    def test_existing_test_pin_definitions_compose_and_keep_their_content(self):
        self.tables["items"] = [{"Id": 9110633, "Name": "original_pin"}]
        self.write_source()
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.db.execute("PRAGMA query_only=ON")
        with patch(
            "guardian_tales.test_item_static.active_specs",
            return_value=(
                json.dumps({"Id": 9990003, "Name": "existing_private_pin", "Defense": 10000}),
            ),
        ):
            original = records(decode(self.get()))[1]
            self.cli("set-level", "--stage", str(STAGE), "--level", "130")
            changed = records(decode(self.get()))[1]
        for name in original.keys() - {"stages", "__checksum__"}:
            self.assertEqual(changed[name][1], original[name][1])
        self.assertGreater(changed["items"][2], original["items"][2])
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_repeated_set_or_restoration_is_a_configuration_noop(self):
        self.cli("restore-level", "--all")
        self.assertFalse((self.root / SELECTION).exists())
        args = ("set-level", "--stage", str(STAGE), "--level", "130")
        self.cli(*args)
        before = (self.root / SELECTION).read_bytes()
        self.cli(*args)
        self.assertEqual((self.root / SELECTION).read_bytes(), before)
        self.cli("restore-level", "--all")
        before = (self.root / SELECTION).read_bytes()
        self.cli("restore-level", "--all")
        self.assertEqual((self.root / SELECTION).read_bytes(), before)

    def test_levels_must_fit_existing_global_experience_rows(self):
        for level in (1, 220):
            self.cli("set-level", "--stage", str(STAGE), "--level", str(level))
        before = (self.root / SELECTION).read_bytes()
        for level in (0, -1, 221, 100000, "true", "130.0"):
            self.reject_cli("set-level", "--stage", str(STAGE), "--level", str(level))
            self.assertEqual((self.root / SELECTION).read_bytes(), before)

    def test_unknown_non_expedition_stage_and_disabled_trial_cannot_be_selected(self):
        for ident in (100010001, 123, -1):
            self.reject_cli("set-level", "--stage", str(ident), "--level", "130")
        (self.root / TRIAL).unlink()
        self.reject_cli("set-level", "--stage", str(STAGE), "--level", "130")
        self.assertFalse((self.root / SELECTION).exists())

    def test_invalid_command_combinations_make_no_configuration_writes(self):
        for args in (
            ("set-level",),
            ("set-level", "--stage", str(STAGE)),
            ("restore-level",),
            ("restore-level", "--all", "--stage", str(STAGE)),
            ("list", "--level", "130"),
            ("list", "--all"),
            ("restore-level", "--stage", str(STAGE), "--level", "130"),
        ):
            self.reject_cli(*args)
        self.assertFalse((self.root / SELECTION).exists())

    def test_invalid_configuration_rejects_both_bootstrap_paths_without_writes(self):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        for value in (
            [],
            {"version": True, "generation": 1, "stages": {}},
            {"version": 1, "generation": -1, "stages": {}},
            {"version": 1, "generation": 1, "stages": {"0250011001": 130}},
            {"version": 1, "generation": 1, "stages": {str(STAGE): True}},
            {"version": 1, "generation": 1, "stages": {str(STAGE): 221}},
            {"version": 1, "generation": 1, "stages": {"100010001": 130}},
        ):
            (self.root / SELECTION).write_text(json.dumps(value))
            for route in ("/static-data/get", "/static-data/check-update"):
                with self.subTest(value=value, route=route), self.assertRaises(PacketError):
                    self.session.handle(request(route, {}))
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_oversized_configuration_and_generation_overflow_are_rejected(self):
        path = self.root / SELECTION
        path.write_bytes(b" " * (MAX_CONFIG_BYTES + 1))
        with self.assertRaises(ValueError):
            load_levels(self.refs)
        path.write_text(
            json.dumps({"version": 1, "generation": 0x7FFFFFFF, "stages": {str(STAGE): 130}})
        )
        before = path.read_bytes()
        self.reject_cli("set-level", "--stage", str(STAGE), "--level", "120")
        self.assertEqual(path.read_bytes(), before)

    def test_failed_atomic_publication_retains_previous_configuration_and_cleans_temporary(self):
        self.cli("set-level", "--stage", str(STAGE), "--level", "130")
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch(
            "guardian_tales.expedition_levels.atomic_replace", side_effect=OSError("disk failure")
        ):
            self.reject_cli("set-level", "--stage", str(STAGE), "--level", "120")
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)

    def test_incomplete_duplicate_or_invalid_source_tables_are_rejected(self):
        for change in (
            lambda: self.tables["stages"].pop(0),
            lambda: self.tables["stages"].append(copy.deepcopy(self.tables["stages"][0])),
            lambda: self.tables["exps2"]["LevelExps"][1].update(TotalExps=1),
            lambda: self.tables["exps2"]["LevelExps"][0].update(TotalExps=0),
            lambda: self.tables["stages"][0].update(StandardLevel={"Default": True}),
        ):
            original = copy.deepcopy(self.tables)
            change()
            self.write_source()
            with self.assertRaises(ValueError):
                catalog(self.source)
            self.tables = original

    def test_all_includes_hidden_unexplored_boss_and_event_stages_without_other_modes(self):
        extra = [
            {
                "Id": ident,
                "ExpeditionStageType": kind,
                "StandardLevel": {"Default": 90},
                "StageExorcism": 100,
                "Name": name,
            }
            for ident, kind, name in (
                (250011010, 2, "boss"),
                (250011011, 3, "unexplored"),
                (250011012, 1, "hidden"),
                (250020001, 3, "event"),
            )
        ]
        self.tables["stages"].extend(extra)
        self.tables["stages"].append(
            {"Id": 320010001, "StandardLevel": {"Default": 99}, "CoopType": 1}
        )
        self.write_source()
        before = list(self.db.iterdump())
        self.db.execute("PRAGMA query_only=ON")
        result = self.cli("set-level", "--all", "--level", "220")
        self.assertEqual(len(result["stages"]), 6)
        self.assertTrue(all(row["enemy_level"] == 220 for row in result["stages"]))
        prepared, _ = prepare(self.source, *load_levels(self.refs))
        expected = copy.deepcopy(self.tables["stages"])
        for row in expected:
            if row["Id"] in {STAGE, OTHER} or "ExpeditionStageType" in row:
                row["StandardLevel"]["KakaoGlobal"] = 219
        self.assertEqual(self.stage_rows(prepared), expected)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_every_visible_level_round_trips_through_native_experience_lookup(self):
        levels = self.tables["exps2"]["LevelExps"]
        for visible in range(1, len(levels) + 1):
            with self.subTest(level=visible):
                result = self.cli("set-level", "--stage", str(STAGE), "--level", str(visible))
                raw = dict(load_levels(self.refs)[1])[STAGE]
                # Native GetTotalExpForLevel uses index (level-1), then
                # ExpToLevel finds the first threshold strictly greater than XP.
                xp = 0 if raw == 0 else levels[min(raw - 1, len(levels) - 1)]["TotalExps"]
                resolved = next(
                    (r["Level"] for r in levels if r["TotalExps"] > xp), levels[-1]["Level"]
                )
                self.assertEqual(resolved + 1, visible)
                self.assertEqual(result["stages"][0]["enemy_level"], visible)

    def test_legacy_raw_configuration_is_preserved_until_explicit_visible_level_change(self):
        path = self.root / SELECTION
        path.write_text(json.dumps({"version": 1, "generation": 1, "stages": {str(STAGE): 130}}))
        before = path.read_bytes()
        result = self.cli("list", "--stage", str(STAGE))
        self.assertEqual(result["stages"][0]["enemy_level"], 131)
        self.assertEqual(path.read_bytes(), before)
        prepared, _ = prepare(self.source, *load_levels(self.refs))
        self.assertEqual(self.stage_rows(prepared)[0]["StandardLevel"]["KakaoGlobal"], 130)
        self.cli("set-level", "--stage", str(STAGE), "--level", "130")
        self.assertEqual(load_levels(self.refs), (2, ((STAGE, 129),)))

    def test_all_then_individual_override_and_restoration_recover_distinct_original_levels(self):
        self.cli("set-level", "--all", "--level", "130")
        before = (self.root / SELECTION).read_bytes()
        self.cli("set-level", "--all", "--level", "130")
        self.assertEqual((self.root / SELECTION).read_bytes(), before)
        self.cli("set-level", "--stage", str(STAGE), "--level", "1")
        self.assertEqual(dict(load_levels(self.refs)[1]), {STAGE: 0, OTHER: 129})
        restored = self.cli("restore-level", "--stage", str(STAGE))
        self.assertEqual(restored["stages"][0]["enemy_level"], 101)
        self.assertEqual(dict(load_levels(self.refs)[1]), {OTHER: 129})
        restored = self.cli("restore-level", "--all")
        self.assertEqual([r["enemy_level"] for r in restored["stages"]], [101, 111])
        prepared, _ = prepare(self.source, *load_levels(self.refs))
        self.assertEqual(self.stage_rows(prepared), self.tables["stages"])

    def test_all_rejects_unsupported_levels_and_ambiguous_targets_without_publication(self):
        self.cli("set-level", "--all", "--level", "130")
        before = (self.root / SELECTION).read_bytes()
        for args in (
            ("set-level", "--all", "--level", "0"),
            ("set-level", "--all", "--level", "221"),
            ("set-level", "--all"),
            ("set-level", "--all", "--stage", str(STAGE), "--level", "130"),
        ):
            self.reject_cli(*args)
        self.assertEqual((self.root / SELECTION).read_bytes(), before)
        with patch(
            "guardian_tales.expedition_levels.atomic_replace", side_effect=OSError("disk failure")
        ):
            self.reject_cli("set-level", "--all", "--level", "220")
        self.assertEqual((self.root / SELECTION).read_bytes(), before)

    def test_zero_internal_level_and_saturated_legacy_upper_bound_are_reported_correctly(self):
        self.tables["stages"][0]["StandardLevel"]["Default"] = 0
        self.tables["stages"][1]["StandardLevel"]["KakaoGlobal"] = 220
        self.write_source()
        result = self.cli("list")
        self.assertEqual([r["original_level"] for r in result["stages"]], [1, 220])
        path = self.root / SELECTION
        path.write_text(json.dumps({"version": 1, "generation": 1, "stages": {str(STAGE): 220}}))
        self.assertEqual(self.cli("list", "--stage", str(STAGE))["stages"][0]["enemy_level"], 220)
