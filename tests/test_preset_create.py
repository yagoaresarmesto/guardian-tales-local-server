# SPDX-License-Identifier: Apache-2.0
"""Applying a populated native empty slot creates and selects an owned team."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.presets import MAX_REVISION, current_group
from guardian_tales.snapshots import CLIENT, preserved_read
from tests.test_preset_edit import PresetFixture


class PresetCreateTests(PresetFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.catalog = self.references / "orbital_preset_catalog.json"
        self.catalog.write_text(json.dumps({"client": CLIENT, "count": 5}))

    def new_body(self, ident=403, selected=True):
        body = self.body(selected=selected)
        body["PartyPreset"].update(Id=ident, Name="New team", Order=999)
        return body

    def test_apply_creates_one_team_and_changes_only_selection_and_revisions(self):
        before = self.store.account.profile()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        source = self.source.read_bytes()
        body = self.new_body()
        response = self.call(body)
        expected = copy.deepcopy(before)
        expected["User"]["SelectedPresetId"]["InfiniteTower"] = 403
        expected["User"]["Cas"] += 1
        group = current_group(self.db)
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(response, {"UserPartyPreset2": group, "User": expected["User"]})
        self.assertEqual(group["Presets"][:3], self.initial_group["Presets"])
        self.assertEqual(group["Cas"], self.initial_group["Cas"] + 1)
        self.assertEqual(group["Presets"][3]["Order"], 3)
        self.assertEqual(
            group["Presets"][3]["Characters"], self.initial_group["Presets"][2]["Characters"]
        )
        self.assertEqual(preserved_read(self.db, "/preset/get-presets")["UserPartyPreset2"], group)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.call({"floor": 1, "presetId": 403}, "/tower-infinity/start-stage"), {}
        )

    def test_empty_new_team_requires_nonselected_save_and_preserves_profile(self):
        body = self.new_body()
        body["PartyPreset"]["Characters"] = []
        self.reject_without_writes(body)
        profile = self.store.account.profile()
        body["SetSelected"] = False
        self.call(body)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(current_group(self.db)["Presets"][-1]["Characters"], [])
        self.reject_without_writes({"PresetId": 403}, "/preset/set-selected-preset")

    def test_catalog_is_needed_only_for_new_slots_and_not_receipt_replays(self):
        body = self.new_body()
        self.catalog.unlink()
        self.reject_without_writes(body)
        edit = self.body()
        edit["PartyPreset"]["Name"] = "Existing"
        self.call(edit, sequence=30)
        self.catalog.write_text(json.dumps({"client": CLIENT, "count": 5}))
        self.call(body)
        self.catalog.unlink()
        before = list(self.db.iterdump())
        self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_catalogs_slots_and_native_empty_order_reject_atomically(self):
        for value in (
            {},
            {"client": {}, "count": 5},
            {"client": CLIENT, "count": True},
            {"client": CLIENT, "count": 0},
            {"client": CLIENT, "count": 101},
            {"client": CLIENT, "count": 5, "extra": 1},
        ):
            self.catalog.write_text(json.dumps(value))
            self.reject_without_writes(self.new_body())
        self.catalog.write_text(" " * 4097)
        self.reject_without_writes(self.new_body())
        self.catalog.write_text(json.dumps({"client": CLIENT, "count": 5}))
        for ident, order in ((405, 999), (499, 999), (403, 0), (403, True), (403, None)):
            body = self.new_body(ident)
            body["PartyPreset"]["Order"] = order
            self.reject_without_writes(body)

    def test_new_slot_rejects_foreign_repeated_or_injected_characters_and_gear(self):
        for characters in (
            [{"Id": 999}],
            [{"Id": 1, "Weapon1": 999}],
            [{"Id": 1, "Level": 99}],
            [{"Id": 1}] * 2,
            [{"Id": 1}] * 5,
        ):
            body = self.new_body()
            body["PartyPreset"]["Characters"] = characters
            self.reject_without_writes(body)

    def test_old_save_and_delete_replays_do_not_recreate_or_remove_new_incarnation(self):
        body = self.new_body()
        self.call(body)
        self.call({"PresetId": 403}, "/preset/delete-preset", 32)
        before = list(self.db.iterdump())
        response = self.call(body)
        self.assertNotIn(403, [p["Id"] for p in response["UserPartyPreset2"]["Presets"]])
        self.assertEqual(list(self.db.iterdump()), before)
        recreated = copy.deepcopy(body)
        recreated["PartyPreset"]["Name"] = "Recreated"
        self.call(recreated, sequence=33)
        self.call({"PresetId": 401}, "/preset/set-selected-preset", 34)
        before = list(self.db.iterdump())
        response = self.call({"PresetId": 403}, "/preset/delete-preset", 32)
        self.assertEqual(response["UserPartyPreset2"]["Presets"][-1]["Name"], "Recreated")
        self.assertEqual(response["User"]["SelectedPresetId"]["InfiniteTower"], 401)
        self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject_without_writes(recreated)

    def test_reopen_reconnect_and_new_login_keep_creation_receipts(self):
        body = self.new_body()
        self.call(body)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.open_session(False)
        # A new operation edits an existing team, so it must retain saved order.
        self.reject_without_writes(body)
        current = self.body(403, selected=True)
        self.call(current)
        self.assertEqual(current_group(self.db)["Cas"], 8)

    def test_invalid_saved_order_ambiguous_ids_and_revision_limits_reject(self):
        for mutate in (
            lambda group: group["Presets"][1].update(Order=999),
            lambda group: group["Presets"].append(copy.deepcopy(group["Presets"][1])),
            lambda group: group.update(Cas=MAX_REVISION),
        ):
            group = copy.deepcopy(self.initial_group)
            mutate(group)
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO party_preset_state VALUES(1,?)", (json.dumps(group),)
                )
            self.reject_without_writes(self.new_body())
        with self.db:
            self.db.execute("DELETE FROM party_preset_state")
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.reject_without_writes(self.new_body())

    def test_failed_receipt_rolls_back_new_definition_and_selection(self):
        self.db.execute(
            "CREATE TRIGGER fail_create BEFORE INSERT ON preset_edit_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.call(self.new_body())
        self.assertEqual(list(self.db.iterdump()), before)

    def test_creation_requires_authentication_and_existing_order_cannot_be_changed(self):
        from guardian_tales.bootstrap import BootstrapSession

        self.session = BootstrapSession(self.store)
        self.reject_without_writes(self.new_body())
        self.open_session()
        body = self.body()
        body["PartyPreset"]["Order"] = 999
        self.reject_without_writes(body)
