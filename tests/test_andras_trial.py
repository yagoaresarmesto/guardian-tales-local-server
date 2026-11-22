# SPDX-License-Identifier: Apache-2.0
"""The experimental Andras view never replaces the stored hero or game assets."""

import base64
import copy
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from guardian_tales.__main__ import main
from guardian_tales.andras_trial import SELECTION, load, project_response
from guardian_tales.andras_trial_static import (
    SOURCE,
    STONE,
    VARIANT,
    binary_rows,
    pack_rows,
    prepare,
)
from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.protocol import Packet, PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from tests.test_snapshots import request, synthetic_snapshot


class AndrasTrialTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = self.root / "state"
        self.state.mkdir()
        self.refs = self.root / "reference"
        self.refs.mkdir()
        self.db = self.enterContext(closing(sqlite3.connect(self.state / "server.sqlite3")))
        self.store = GuestStore(self.db, self.refs)
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True
        snapshot = synthetic_snapshot()
        profile = snapshot["profile"]
        profile["User"]["Characters"][0]["CharacterId"] = SOURCE
        self.owner = profile["User"]["Id"]
        self.target = profile["User"]["Characters"][0]["Id"]
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("synthetic", "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        source = {
            "Id": SOURCE,
            "Name": "demon_slayer_5",
            "OriginId": 488,
            "Rank": 4,
            "Class": "demon_slayer",
            "MythStoneId": 0,
            "Hp": 1100,
            "Atk": 1.521,
            "Def": 23.52,
            "Options": [{"OptionId": 320488}],
            "SpineAssetName": {"default": "existing_andras"},
            "PortraitAssetName": "existing_portrait",
            "EvolveTo": 0,
        }
        self.heroes = [source, {"Id": 200, "Name": "other_hero", "Rank": 4, "OriginId": 200}]
        self.tables = {
            "heroes": self.heroes,
            "heroes-bin": pack_rows(
                [(row["Id"], i + 1, json.dumps(row).encode()) for i, row in enumerate(self.heroes)]
            ),
            "items": [
                {
                    "Id": 85001,
                    "Name": "myth_stone_stock",
                    "Type": "evolve_stone",
                    "StoneType": "HeroMyth",
                    "SpriteName": {"default": "existing_stone_icon"},
                }
            ],
            "charactertreeconfig": [{"OriginId": 488, "TreeLayoutName": "original_tree"}],
            "__checksum__": "source",
        }
        self.write_source()
        # Tests do not require the optional xxhash package; the real pack is
        # checked separately with native xxh3 hashes, never this synthetic hash.
        self.enterContext(
            patch(
                "guardian_tales.andras_trial_static.binary_name_hash",
                side_effect=lambda name: int.from_bytes(
                    hashlib.sha256(name.encode()).digest()[:8], "little"
                ),
            )
        )

    def write_source(self):
        text = ""
        for name, value in self.tables.items():
            content = value if name.endswith("-bin") else json.dumps(value)
            raw = base64.b64decode(content) if name.endswith("-bin") else content.encode()
            text += f"{name}\n{content}\n31\n{digest(raw)}\n"
        self.original = compress(text.encode())
        (self.refs / "static_data_get.bin").write_bytes(self.original)
        (self.refs / "static_data_check.bin").write_text('{"UpToDate":true}')

    def cli(self, action, data_dir=None):
        with redirect_stdout(io.StringIO()) as output:
            main(
                [
                    "andras-trial",
                    action,
                    "--reference-dir",
                    str(self.refs),
                    "--data-dir",
                    str(data_dir or self.state),
                ]
            )
        return json.loads(output.getvalue())

    def reject(self, action, data_dir=None):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.cli(action, data_dir)
        self.assertEqual(error.exception.code, 2)

    def fetch(self):
        return json.loads(self.session.handle(request("/auth/fetch-account", {})).body)

    def test_disabled_feature_retains_exact_original_responses_and_files(self):
        before = list(self.db.iterdump())
        paths = {p.name: p.read_bytes() for p in self.refs.iterdir()}
        packet = request("/auth/fetch-account", {})
        self.assertEqual(self.session.handle(packet), self.session._handle(packet))
        self.assertFalse(self.cli("status")["active"])
        self.assertFalse(self.cli("disable")["active"])
        self.assertEqual({p.name: p.read_bytes() for p in self.refs.iterdir()}, paths)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_enable_projects_only_owned_target_without_database_writes(self):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        expected = copy.deepcopy(self.store.account.profile())
        expected["User"]["Characters"][0]["CharacterId"] = VARIANT
        self.db.execute("PRAGMA query_only=ON")
        self.assertTrue(self.cli("enable")["active"])
        self.assertEqual(self.fetch(), expected)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(
            self.store.account.profile()["User"]["Characters"][0]["CharacterId"], SOURCE
        )

    def test_disable_restores_original_view_and_keeps_progress_since_enable(self):
        self.cli("enable")
        self.assertEqual(self.fetch()["User"]["Characters"][0]["CharacterId"], VARIANT)
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["Experience"] += 123
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        before = list(self.db.iterdump())
        self.assertFalse(self.cli("disable")["active"])
        self.assertEqual(self.fetch(), profile)
        self.assertEqual(load(self.store.references)["generation"], 2)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_static_json_binary_and_assets_retain_original_combat_and_visual_fields(self):
        body, _ = prepare(self.original, 1, True)
        tables = records(decode(body))[1]
        heroes = json.loads(tables["heroes"][1])
        source, other, variant = heroes
        self.assertEqual(
            source, dict(self.heroes[0], MythTo={"KakaoGlobal": VARIANT}, MythStoneId=STONE)
        )
        self.assertEqual(other, self.heroes[1])
        self.assertEqual(
            variant, dict(self.heroes[0], Id=VARIANT, Name="demon_slayer_myth", Rank=6)
        )
        binary = {ident: json.loads(raw) for ident, _, raw in binary_rows(tables["heroes-bin"][1])}
        self.assertEqual(binary, {row["Id"]: row for row in heroes})
        stone = json.loads(tables["items"][1])[-1]
        self.assertEqual(stone["SpriteName"], self.tables["items"][0]["SpriteName"])
        self.assertEqual(
            tables["charactertreeconfig"], records(decode(self.original))[1]["charactertreeconfig"]
        )
        self.assertEqual((self.refs / "static_data_get.bin").read_bytes(), self.original)

    def test_disable_recovers_all_original_static_contents_with_new_revisions(self):
        active, first = prepare(self.original, 1, True)
        restored, second = prepare(self.original, 2, False)
        before, after = records(decode(self.original))[1], records(decode(restored))[1]
        for name in before.keys() - {"__checksum__"}:
            self.assertEqual(after[name][1], before[name][1])
        self.assertNotEqual(first, second)
        self.assertGreater(after["heroes"][2], records(decode(active))[1]["heroes"][2])

    def test_bootstrap_get_and_check_share_active_and_restored_checksums(self):
        before = list(self.db.iterdump())
        self.db.execute("PRAGMA query_only=ON")
        previous = None
        for action in ("enable", "disable", "enable"):
            self.cli(action)
            body = self.session.handle(request("/static-data/get", {})).body
            checksum = records(decode(body))[1]["__checksum__"][1]
            for value, expected in ((checksum, True), (previous, False)):
                check = json.loads(
                    self.session.handle(
                        request("/static-data/check-update", {"Checksum": value})
                    ).body
                )
                self.assertEqual(check["Checksum"], checksum)
                self.assertEqual(check["UpToDate"], expected)
            previous = checksum
        self.assertEqual(list(self.db.iterdump()), before)

    def test_reply_projection_handles_partial_and_nested_resources_without_other_owners(self):
        self.cli("enable")
        selection = load(self.store.references)
        target = {"Id": self.target, "CharacterId": SOURCE, "Experience": 42}
        value = {
            "User": {"Id": self.owner, "Characters": [target]},
            "UserProfileCard": {"User": {"Id": self.owner, "Characters": [target]}},
            "OtherUser": {"Id": self.owner + 1, "Characters": [target]},
        }
        original = Packet(
            1, json.dumps(value).encode(), body_type=1, sequence_id=77, hint="synthetic"
        )
        result = project_response(original, selection)
        expected = json.loads(json.dumps(value))
        expected["User"]["Characters"][0]["CharacterId"] = VARIANT
        expected["UserProfileCard"]["User"]["Characters"][0]["CharacterId"] = VARIANT
        self.assertEqual(json.loads(result.body), expected)
        self.assertEqual(replace(result, body=original.body), original)
        self.assertEqual(json.loads(original.body), value)

    def test_unrelated_and_binary_replies_are_returned_unchanged(self):
        self.cli("enable")
        selection = load(self.store.references)
        for packet in (
            Packet(1),
            Packet(1, b"data", body_type=2),
            Packet(1, b'{"User":{"Cas":4}}', body_type=1),
            Packet(1, b'{"User":{"Characters":[{"Id":999,"CharacterId":490}]}}', body_type=1),
        ):
            self.assertIs(project_response(packet, selection), packet)

    def test_missing_wrong_or_multiple_owned_andras_cannot_be_enabled(self):
        profile = self.store.account.profile()
        for change in (
            lambda u: u["Characters"].clear(),
            lambda u: u["Characters"].append(dict(u["Characters"][0], Id=999)),
        ):
            modified = copy.deepcopy(profile)
            change(modified["User"])
            with self.db:
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1", (json.dumps(modified),)
                )
            self.reject("enable")
            self.assertFalse((self.refs / SELECTION).exists())
        self.reject("enable", self.root / "missing")
        self.assertFalse((self.root / "missing").exists())

    def test_wrong_owner_and_changed_content_reject_before_handler_writes(self):
        self.cli("enable")
        path = self.refs / SELECTION
        original = load(self.store.references)
        before = list(self.db.iterdump())
        for change in (
            {"owner_id": self.owner + 1},
            {"source_sha256": "0" * 64},
            {"inventory_id": self.target + 1},
        ):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(PacketError):
                self.fetch()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_trial_hero_training_is_guarded_before_mutating_the_save(self):
        self.cli("enable")
        before = list(self.db.iterdump())
        with self.assertRaisesRegex(PacketError, "Disable the Andras trial"):
            self.session.handle(
                request("/user/add-character-experience", {"Experiences": {str(self.target): 100}})
            )
        self.assertEqual(list(self.db.iterdump()), before)

    def test_repeated_enable_disable_and_status_are_configuration_noops(self):
        for action in ("enable", "disable"):
            self.cli(action)
            before = (self.refs / SELECTION).read_bytes()
            self.cli(action)
            self.cli("status")
            self.assertEqual((self.refs / SELECTION).read_bytes(), before)

    def test_failed_publication_retains_configuration_and_removes_temporary_file(self):
        self.cli("enable")
        before = {p.name: p.read_bytes() for p in self.refs.iterdir()}
        with patch(
            "guardian_tales.raid_static.atomic_replace", side_effect=OSError("disk failure")
        ):
            self.reject("disable")
        self.assertEqual({p.name: p.read_bytes() for p in self.refs.iterdir()}, before)

    def test_malformed_configuration_and_revision_overflow_do_not_write(self):
        self.cli("enable")
        path = self.refs / SELECTION
        original = load(self.store.references)
        for change in (
            {"version": True},
            {"active": 1},
            {"inventory_id": True},
            {"generation": -1},
        ):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(ValueError):
                load(self.store.references)
        path.write_text(json.dumps(dict(original, generation=0x7FFFFFFF)))
        before = path.read_bytes()
        self.reject("disable")
        self.assertEqual(path.read_bytes(), before)

    def test_binary_repacking_preserves_large_records_and_block_boundaries(self):
        rows = [
            (i, i + 100, json.dumps({"Id": i, "data": "x" * 30000}).encode()) for i in range(1, 5)
        ]
        self.assertEqual(binary_rows(pack_rows(rows)), rows)
        broken = base64.b64encode(b"bad").decode()
        with self.assertRaises(ValueError):
            binary_rows(broken)

    def test_collisions_and_mismatched_source_tables_are_rejected(self):
        for change in (
            lambda: self.heroes[0].update(Rank=5),
            lambda: self.heroes.append(dict(self.heroes[0], Id=VARIANT)),
            lambda: self.tables["items"].append({"Id": STONE}),
            lambda: self.heroes[0].update(Atk=99),
        ):
            old_heroes, old_items = copy.deepcopy(self.heroes), copy.deepcopy(self.tables["items"])
            change()
            self.write_source()
            self.reject("enable")
            self.assertFalse((self.refs / SELECTION).exists())
            self.heroes[:] = old_heroes
            self.tables["items"] = old_items
