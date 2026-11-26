# SPDX-License-Identifier: Apache-2.0
"""Saved Orbital/Raid choices preserve unrelated state and survive request retries."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.accounts.snapshots import CLIENT, import_snapshot
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.teams.presets import MAX_REVISION
from tests.account.test_snapshots import synthetic_snapshot

ROUTE = "/preset/set-selected-preset"


class PresetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.references = self.root / "references"
        self.references.mkdir()
        (self.references / "orbital_entry_catalog.json").write_text(
            json.dumps({"client": CLIENT, "floors": [1, 2, 3]})
        )
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["SelectedPresetId"] = {
            "InfiniteTower": 401,
            "Rift": 101,
            "GuildRaidAndConquest": 701,
        }
        snapshot["profile"]["UserProgress"]["TowerInfinity"]["Floor"] = 2
        self.presets = {
            "Presets": [
                {"Id": i, "Characters": [{"Id": 1, "Weapon1": 1}]}
                for i in (101, 401, 402, 403, 701, 713, 714)
            ],
            "Cas": 7,
        }
        snapshot["startup_reads"]["/preset/get-presets"]["value"]["UserPartyPreset2"] = self.presets
        self.source = self.root / "synthetic.json"
        self.source.write_text(json.dumps(snapshot))
        self.state = self.root / "state"
        import_snapshot(self.source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db, self.references)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            "/auth/sign-in",
            sequence=1,
        )

    def call(self, body, route=ROUTE, sequence=31):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(request))))

    def reject_without_writes(self, body, sequence=31):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_selection_changes_only_orbital_pointer_and_revision_and_can_enter(self):
        before = self.store.account.profile()
        source = self.source.read_bytes()
        reads = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        expected = copy.deepcopy(before)
        expected["User"]["SelectedPresetId"]["InfiniteTower"] = 402
        expected["User"]["Cas"] += 1
        self.assertEqual(
            self.call({"PresetId": 402}),
            {"User": {key: expected["User"][key] for key in ("Id", "Cas", "SelectedPresetId")}},
        )
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], reads
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM preset_selection_requests").fetchone()[0], 1
        )
        self.assertEqual(
            self.call({"floor": 3, "presetId": 402}, "/tower-infinity/start-stage"), {}
        )
        self.assertEqual(self.store.account.profile(), expected)

    def test_retries_return_current_state_without_undoing_a_later_choice(self):
        initial = self.store.account.profile()["User"]["Cas"]
        self.call({"PresetId": 402}, sequence=31)
        self.call({"PresetId": 403}, sequence=32)
        before = list(self.db.iterdump())
        response = self.call({"PresetId": 402}, sequence=31)
        self.assertEqual(response["User"]["SelectedPresetId"]["InfiniteTower"], 403)
        self.assertEqual(response["User"]["Cas"], initial + 2)
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes({"PresetId": 401}, sequence=31)

    def test_same_choice_does_not_increment_revision_and_new_epoch_allows_new_selection(self):
        self.call({"PresetId": 402})
        revision = self.store.account.profile()["User"]["Cas"]
        self.call({"PresetId": 402}, sequence=32)
        self.assertEqual(self.store.account.profile()["User"]["Cas"], revision)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.call({"PresetId": 402})
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        self.call({"PresetId": 401})
        self.assertEqual(
            self.store.account.profile()["User"]["SelectedPresetId"]["InfiniteTower"], 401
        )
        self.assertEqual(self.store.account.profile()["User"]["Cas"], revision + 1)

    def test_authentication_exact_parameters_scope_and_missing_presets_reject(self):
        self.session = BootstrapSession(self.store)
        self.reject_without_writes({"PresetId": 402})
        self.open_session()
        for body in (
            None,
            {},
            [],
            {"PresetId": True},
            {"PresetId": "402"},
            {"PresetId": 0},
            {"PresetId": 101},
            {"PresetId": 499},
            {"PresetId": 500},
            {"PresetId": 402, "PresetType": "InfiniteTower"},
        ):
            with self.subTest(body=body):
                self.reject_without_writes(body)
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        self.reject_without_writes({"PresetId": 402})

    def test_unowned_characters_gear_and_ambiguous_saved_presets_reject(self):
        original = json.loads(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        )
        for change in ("hero", "gear", "duplicate", "empty"):
            reads = copy.deepcopy(original)
            rows = reads["/preset/get-presets"]["value"]["UserPartyPreset2"]["Presets"]
            target = next(row for row in rows if row["Id"] == 402)
            if change == "hero":
                target["Characters"][0]["Id"] = 999
            elif change == "gear":
                target["Characters"][0]["Weapon1"] = 999
            elif change == "duplicate":
                rows.append(copy.deepcopy(target))
            else:
                target["Characters"] = []
            with self.db:
                self.db.execute("UPDATE imported_account SET startup_reads=?", (json.dumps(reads),))
            self.reject_without_writes({"PresetId": 402})

    def test_invalid_saved_selection_or_revision_and_overflow_do_not_mutate(self):
        original = self.store.account.profile()
        for field, value in (
            ("SelectedPresetId", None),
            ("SelectedPresetId", {"InfiniteTower": 101}),
            ("Cas", True),
            ("Cas", -1),
            ("Cas", MAX_REVISION),
            ("Cas", MAX_REVISION + 1),
        ):
            profile = copy.deepcopy(original)
            profile["User"][field] = value
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            self.reject_without_writes({"PresetId": 402})

    def test_failed_receipt_write_rolls_back_selection_and_revision(self):
        self.db.execute(
            "CREATE TRIGGER fail_preset_receipt BEFORE INSERT ON preset_selection_requests "
            "BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.call({"PresetId": 402})
        self.assertEqual(list(self.db.iterdump()), before)
        self.db.execute("DROP TRIGGER fail_preset_receipt")
        self.db.commit()
        self.call({"PresetId": 402})
        self.assertEqual(
            self.store.account.profile()["User"]["SelectedPresetId"]["InfiniteTower"], 402
        )

    def test_raid_selection_changes_only_its_shared_pointer_and_revision_from_zero(self):
        initial = self.store.account.profile()
        initial["User"]["SelectedPresetId"]["GuildRaidAndConquest"] = 0
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(initial),))
        source = self.source.read_bytes()
        reads = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        expected = copy.deepcopy(initial)
        expected["User"]["SelectedPresetId"]["GuildRaidAndConquest"] = 713
        expected["User"]["Cas"] += 1
        self.assertEqual(
            self.call({"PresetId": 713}),
            {"User": {key: expected["User"][key] for key in ("Id", "Cas", "SelectedPresetId")}},
        )
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], reads
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM preset_selection_requests").fetchone()[0], 1
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM party_preset_state").fetchone()[0], 0
        )

    def test_raid_and_orbital_choices_replay_current_state_and_survive_reopen_without_cross_mode_reset(
        self,
    ):
        initial = self.store.account.profile()["User"]["Cas"]
        self.call({"PresetId": 713}, sequence=31)
        self.call({"PresetId": 402}, sequence=32)
        self.call({"PresetId": 714}, sequence=33)
        self.call({"PresetId": 714}, sequence=34)
        self.assertEqual(self.store.account.profile()["User"]["Cas"], initial + 3)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        for preset_id, sequence in ((713, 31), (402, 32)):
            user = self.call({"PresetId": preset_id}, sequence=sequence)["User"]
            self.assertEqual(
                user["SelectedPresetId"],
                {"InfiniteTower": 402, "Rift": 101, "GuildRaidAndConquest": 714},
            )
            self.assertEqual(user["Cas"], initial + 3)
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes({"PresetId": 701}, sequence=31)
        self.reject_without_writes({"PresetId": 713}, sequence=32)

    def test_raid_rejects_missing_ambiguous_empty_or_unowned_saved_teams(self):
        self.reject_without_writes({"PresetId": 799})
        self.reject_without_writes({"PresetId": 800})
        original = json.loads(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        )
        for change in ("hero", "gear", "duplicate", "empty"):
            reads = copy.deepcopy(original)
            rows = reads["/preset/get-presets"]["value"]["UserPartyPreset2"]["Presets"]
            target = next(row for row in rows if row["Id"] == 713)
            if change == "hero":
                target["Characters"][0]["Id"] = 999
            elif change == "gear":
                target["Characters"][0]["Weapon1"] = 999
            elif change == "duplicate":
                rows.append(copy.deepcopy(target))
            else:
                target["Characters"] = []
            with self.db:
                self.db.execute("UPDATE imported_account SET startup_reads=?", (json.dumps(reads),))
            self.reject_without_writes({"PresetId": 713})

    def test_invalid_saved_raid_pointer_and_revision_do_not_repair_other_modes(self):
        original = self.store.account.profile()
        for value in (None, True, -1, 401, 800):
            profile = copy.deepcopy(original)
            if value is None:
                del profile["User"]["SelectedPresetId"]["GuildRaidAndConquest"]
            else:
                profile["User"]["SelectedPresetId"]["GuildRaidAndConquest"] = value
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            self.reject_without_writes({"PresetId": 713})
        for value in (True, -1, MAX_REVISION, MAX_REVISION + 1):
            profile = copy.deepcopy(original)
            profile["User"]["Cas"] = value
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            self.reject_without_writes({"PresetId": 713})

    def test_raid_selection_and_revision_roll_back_when_receipt_insert_fails(self):
        self.db.execute(
            "CREATE TRIGGER fail_raid_preset BEFORE INSERT ON preset_selection_requests BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.call({"PresetId": 713})
        self.assertEqual(list(self.db.iterdump()), before)
        self.db.execute("DROP TRIGGER fail_raid_preset")
        self.db.commit()
        self.call({"PresetId": 713})
        self.assertEqual(
            self.store.account.profile()["User"]["SelectedPresetId"]["GuildRaidAndConquest"], 713
        )
