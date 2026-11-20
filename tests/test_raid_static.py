# SPDX-License-Identifier: Apache-2.0
"""Historical raid selection changes only its calendar in client static data."""

import copy
import json
import os
import random
import sqlite3
import struct
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.guild_raid import (
    CATALOG,
    SELECTION,
    load_selection,
    select_season,
    selected_season,
)
from guardian_tales.packet_reader import MAX_PACKET, PacketError, lz4_block
from guardian_tales.raid_custom import parse_lineup
from guardian_tales.raid_static import (
    LOCAL_FROM,
    LOCAL_TO,
    MAX_STATIC,
    atomic_replace,
    bootstrap_override,
    compress,
    decode,
    digest,
    records,
)
from tests.test_guild_raid import synthetic_catalog, synthetic_static
from tests.test_snapshots import request


class RaidStaticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.catalog = synthetic_catalog()
        (self.root / CATALOG).write_text(json.dumps(self.catalog))
        self.source = self.root / "static_data_get.bin"
        self.source.write_bytes(synthetic_static(self.catalog))
        self.original = self.source.read_bytes()
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db, self.root)
        self.ref = self.store.references
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def rewrite_source(self, name, mutate):
        lines, items = records(decode(self.original))
        item = json.loads(items[name][1])
        mutate(item)
        value = json.dumps(item)
        at = items[name][0]
        lines[at + 1] = value + "\n"
        lines[at + 3] = digest(value.encode()) + "\n"
        self.source.write_bytes(compress("".join(lines).encode()))

    def test_atomic_publication_retries_transient_windows_sharing_locks_without_partial_output(
        self,
    ):
        target, staged = self.root / "published.json", self.root / "staged.json"
        target.write_bytes(b"old")
        staged.write_bytes(b"new-complete")
        original_replace = os.replace
        attempts = []

        def temporarily_locked(source, destination):
            attempts.append(1)
            if len(attempts) < 3:
                self.assertEqual(target.read_bytes(), b"old")
                error = PermissionError("synthetic sharing violation")
                error.winerror = 32
                raise error
            return original_replace(source, destination)

        with (
            patch("guardian_tales.raid_static.os.replace", side_effect=temporarily_locked),
            patch("guardian_tales.raid_static.time.sleep"),
        ):
            atomic_replace(staged, target)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(target.read_bytes(), b"new-complete")
        self.assertFalse(staged.exists())

    def test_atomic_publication_keeps_failures_bounded_and_does_not_retry_access_denials(self):
        target, staged = self.root / "published.json", self.root / "staged.json"
        target.write_bytes(b"old")
        staged.write_bytes(b"new")
        for winerror, expected_calls in ((33, 6), (5, 1)):
            error = PermissionError("synthetic filesystem refusal")
            error.winerror = winerror
            with (
                patch("guardian_tales.raid_static.os.replace", side_effect=error) as replace,
                patch("guardian_tales.raid_static.time.sleep"),
            ):
                with self.assertRaises(PermissionError):
                    atomic_replace(staged, target)
            self.assertEqual(replace.call_count, expected_calls)
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(staged.read_bytes(), b"new")

    def test_historical_activation_preserves_other_rows_services_bosses_and_all_other_tables(self):
        before = records(decode(self.original))[1]
        select_season(self.ref, 1)
        prepared = bootstrap_override(self.ref, "static_data_get.bin", {})
        after = records(decode(prepared))[1]
        self.assertEqual(set(before), set(after))
        for name in before.keys() - {"seasondate", "__checksum__"}:
            self.assertEqual(before[name], after[name])
        original_dates = json.loads(before["seasondate"][1])["EventPeriod"]
        actual_dates = json.loads(after["seasondate"][1])["EventPeriod"]
        self.assertEqual(original_dates[1:], actual_dates[1:])
        expected = copy.deepcopy(original_dates[0])
        expected["From"]["KakaoGlobal"] = LOCAL_FROM
        expected["To"]["KakaoGlobal"] = LOCAL_TO
        expected["RewardUntil"]["KakaoGlobal"] = "2099-12-31T23:59:59+00:00"
        self.assertEqual(actual_dates[0], expected)
        now = datetime(2026, 11, 18, tzinfo=timezone.utc)
        self.assertLess(datetime.fromisoformat(original_dates[0]["To"]["KakaoGlobal"]), now)
        self.assertLessEqual(datetime.fromisoformat(actual_dates[0]["From"]["KakaoGlobal"]), now)
        self.assertLess(now, datetime.fromisoformat(actual_dates[0]["To"]["KakaoGlobal"]))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_custom_rotation_shares_stages_and_restores_stock_with_new_revisions(self):
        lines, before = records(decode(self.original))
        raid = json.loads(before["guildraid2"][1])
        raid["BossDetails"].extend(
            [
                {"Id": 1100627, "StageId": 810010002, "MonsterId": 100627, "MonsterRelation": 1},
                {"Id": 1790013, "StageId": 810010007, "MonsterId": 790013},
                {"Id": 1790102, "StageId": 810010004, "MonsterId": 790102},
            ]
        )
        monsters = [
            {
                "Id": 100627,
                "Name": "boss_sandmonster_guild",
                "Class": "sandmonster",
                "ElementalType": "Earth",
            },
            {
                "Id": 790013,
                "Name": "boss_demon_guild_v2_fire",
                "Class": "demon",
                "ElementalType": "Fire",
            },
            {
                "Id": 790012,
                "Name": "boss_demon_guild_v2_dark",
                "Class": "demon",
                "ElementalType": "Darkness",
            },
            {"Id": 790102, "Name": "boss_sapa_guild_v2_dark", "ElementalType": "Darkness"},
        ]
        raid_json = json.dumps(raid)
        at = before["guildraid2"][0]
        lines[at + 1] = raid_json + "\n"
        lines[at + 3] = digest(raid_json.encode()) + "\n"
        monster_json = json.dumps(monsters)
        lines[at:at] = [
            "monsters\n",
            monster_json + "\n",
            "1\n",
            digest(monster_json.encode()) + "\n",
        ]
        original = compress("".join(lines).encode())
        self.source.write_bytes(original)
        catalog_file = self.root / CATALOG
        original_catalog = catalog_file.read_bytes()

        lineup = parse_lineup(
            "Sandmonster LIGHT, ancient demon fire, viper clan leader dark, sandmonster water"
        )
        custom = select_season(self.ref, lineup=lineup)
        self.assertEqual(custom["season_id"], 1)
        self.assertEqual(selected_season(self.ref), custom)
        stages = [boss["stage_id"] for boss in custom["bosses"]]
        self.assertEqual(stages, [810010002, 810010007, 810010004, 810010002])
        prepared = records(decode(bootstrap_override(self.ref, "static_data_get.bin", {})))[1]
        overlay = json.loads(prepared["guildraid2"][1])
        details = {row["Id"]: row for row in overlay["BossDetails"]}
        spec = {row["Id"]: row for row in json.loads(prepared["monsters"][1])}
        selected_details = [details[boss["id"]] for boss in custom["bosses"]]
        self.assertEqual(
            [spec[row["MonsterId"]]["ElementalType"] for row in selected_details],
            ["Light", "Fire", "Darkness", "Ice"],
        )
        self.assertEqual([selected_details[i]["MonsterRelation"] for i in (0, 3)], [1, 1])
        self.assertEqual(overlay["Seasons"][1], raid["Seasons"][1])
        self.assertEqual(overlay["Boss"][: len(raid["Boss"])], raid["Boss"])

        # Replace a generated element with the game’s existing unregistered monster.
        lineup[-1] = ("ancient demon", "dark")
        custom = select_season(self.ref, lineup=lineup)
        self.assertEqual(selected_season(self.ref), custom)
        updated = records(decode(bootstrap_override(self.ref, "static_data_get.bin", {})))[1]
        overlay = json.loads(updated["guildraid2"][1])
        self.assertEqual(overlay["BossDetails"][-1]["MonsterId"], 790012)
        self.assertGreater(updated["guildraid2"][2], prepared["guildraid2"][2])

        self.assertEqual(select_season(self.ref, 1), self.catalog["seasons"][0])
        self.assertEqual(selected_season(self.ref), self.catalog["seasons"][0])
        restored = records(decode(bootstrap_override(self.ref, "static_data_get.bin", {})))[1]
        for table, original_json in (("guildraid2", raid_json), ("monsters", monster_json)):
            self.assertEqual(restored[table][1], original_json)
            self.assertGreater(restored[table][2], updated[table][2])
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(catalog_file.read_bytes(), original_catalog)

    def test_custom_lineup_rejects_duplicates_and_unknown_choices(self):
        for text in (
            "sandmonster light",
            "sandmonster light, ancient demon fire, viper clan leader dark, Sandmonster Light",
            "sandmonster light, ancient demon fire, viper clan leader dark, sandmonster wind",
            "sandmonster light, ancient demon fire, viper clan leader dark, sand monster water",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_lineup(text)

    def test_bootstrap_serves_consistent_cache_hashes_and_new_selection_revisions_without_writes(
        self,
    ):
        before = list(self.db.iterdump())
        self.db.execute("PRAGMA query_only=ON")
        changes = self.db.total_changes
        previous_revision = 0
        for season in (1, 2, 1):
            select_season(self.ref, season)
            selected = load_selection(self.ref)
            self.assertGreater(selected["static_data_revision"], previous_revision)
            previous_revision = selected["static_data_revision"]
            response = self.session.handle(request("/static-data/get", {"ClientVersions": {}}))
            self.assertEqual(response.body_type, 2)
            items = records(decode(response.body))[1]
            self.assertEqual(items["__checksum__"][1], selected["static_data_checksum"])
            calendar = json.loads(items["seasondate"][1])["EventPeriod"]
            for row in calendar[:2]:
                self.assertEqual(
                    row["From"]["KakaoGlobal"] == LOCAL_FROM, row["Id"] == 5400000 + season
                )
            for checksum, current in (("old", False), (selected["static_data_checksum"], True)):
                reply = self.session.handle(
                    request("/static-data/check-update", {"Checksum": checksum})
                )
                self.assertEqual(
                    json.loads(reply.body),
                    {
                        "UpToDate": current,
                        "Checksum": selected["static_data_checksum"],
                        "QuitGameWhenStaticDataUpdateNeeded": False,
                    },
                )
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_invalid_static_inputs_keep_previous_selection_and_original_account(self):
        select_season(self.ref, 1)
        selected = (self.root / SELECTION).read_bytes()
        before = list(self.db.iterdump())
        for name, mutate in (
            ("guildraid2", lambda x: x["Seasons"][1].update(BossSet=99)),
            ("guildraid2", lambda x: x["BossDetails"][4].update(StageId=99)),
            ("guildraid2", lambda x: x["Seasons"][1].update(SeasonDateId=99)),
            ("seasondate", lambda x: x["EventPeriod"][1]["From"].pop("KakaoGlobal")),
        ):
            self.rewrite_source(name, mutate)
            with self.assertRaises(ValueError):
                select_season(self.ref, 2)
            self.assertEqual((self.root / SELECTION).read_bytes(), selected)
        self.source.unlink()
        with self.assertRaises(ValueError):
            select_season(self.ref, 2)
        self.assertEqual((self.root / SELECTION).read_bytes(), selected)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_missing_corrupt_artifacts_and_malformed_manifest_fail_closed(self):
        select_season(self.ref, 1)
        selected = load_selection(self.ref)
        path = self.root / f"guild_raid_static_{selected['static_data_sha256']}.bin"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError):
            bootstrap_override(self.ref, "static_data_get.bin", {})
        path.write_bytes(original + b"corrupt")
        with self.assertRaises(ValueError):
            bootstrap_override(self.ref, "static_data_get.bin", {})
        for key, value in (
            ("static_data_sha256", "../escape"),
            ("static_data_checksum", "bad"),
            ("static_data_revision", True),
        ):
            (self.root / SELECTION).write_text(json.dumps(dict(selected, **{key: value})))
            with self.assertRaises(ValueError):
                bootstrap_override(self.ref, "static_data_get.bin", {})

    def test_lz4_matches_literals_overlap_and_window_limits_without_weakening_network_bounds(self):
        rng = random.Random(57)
        for raw in [bytes(range(n)) for n in range(1, 25)] + [
            b"a" * 200000,
            bytes(range(256)) * 600,
            rng.randbytes(100000),
            b"abc" * 60000 + rng.randbytes(70000) + b"abc" * 60000,
        ]:
            self.assertEqual(decode(compress(raw)), raw)
        with self.assertRaises(PacketError):
            lz4_block(b"", MAX_PACKET + 1)
        with self.assertRaises(PacketError):
            decode(b"\x00" + struct.pack("<I", MAX_STATIC + 1))
        raw = decode(self.original).replace(b'"Keep":[1,2]', b'"Keep":[1,3]')
        with self.assertRaises(ValueError):
            records(raw)

    def test_no_override_or_legacy_id_setting_preserves_static_response_and_upgrade_requires_restart(
        self,
    ):
        self.assertIsNone(bootstrap_override(self.ref, "static_data_get.bin", {}))
        (self.root / SELECTION).write_text(
            json.dumps({"client": self.catalog["client"], "season_id": 1})
        )
        self.assertIsNone(bootstrap_override(self.ref, "static_data_get.bin", {}))
        self.assertIsNone(bootstrap_override(self.ref, "resource_urls.bin", {}))
        select_season(self.ref, 1)
        self.assertIsNotNone(bootstrap_override(self.ref, "static_data_get.bin", {}))
        selected = (self.root / SELECTION).read_bytes()
        with patch(
            "guardian_tales.raid_static.os.replace", side_effect=OSError("synthetic failure")
        ):
            with self.assertRaises(OSError):
                select_season(self.ref, 2)
        self.assertEqual((self.root / SELECTION).read_bytes(), selected)
        self.assertFalse(list(self.root.glob(".raid-*")))
