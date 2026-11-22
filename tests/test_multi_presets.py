# SPDX-License-Identifier: Apache-2.0
"""Expedition preset operations preserve the account, other groups and retry state."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.expedition import TRIAL
from guardian_tales.items import inventory_item
from guardian_tales.multi_presets import DELETE, REORDER, SAVE, current_group, delete
from guardian_tales.presets import GEAR_FIELDS, MAX_REVISION
from guardian_tales.protocol import PacketError
from tests.test_village_harvest import NOW, VillageFixture


def member(ident, weapon):
    return {"Id": ident, **{k: weapon if k == "Weapon1" else None for k in GEAR_FIELDS}}


def preset(ident, order):
    return {
        "Id": ident,
        "Name": f"Team {ident}",
        "Order": order,
        "Metadata": "keep",
        "Parties": [
            {
                "Id": i,
                "Name": f"Party {i}",
                "Order": 0,
                "Characters": [member(i, 10 + i + (3 if ident == 901 else 0))],
                "Metadata": f"keep-{i}",
            }
            for i in (1, 2, 3)
        ],
    }


class MultiPresetTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        profile = self.store.account.profile()
        template = profile["User"]["Characters"][0]
        for ident in (2, 3, 4):
            profile["User"]["Characters"].append(dict(copy.deepcopy(template), Id=ident))
        profile["User"]["CharacterIdCounter"] = 4
        profile["User"]["ItemWeapons"].extend(inventory_item(i, 101) for i in range(11, 17))
        profile["User"]["ItemIdCounter"] = 20
        profile["User"]["SelectedPresetId"]["Expedition"] = 900
        self.save_profile(profile)
        self.initial = {
            "Cas": 0x80000008,
            "Metadata": "group metadata",
            "Presets": [
                preset(900, 0),
                preset(901, 1),
                {"Id": 1700, "Name": "Other mode", "Order": 0, "Parties": []},
            ],
        }
        reads = json.loads(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        )
        reads["/preset/get-presets"]["value"]["UserMultiPartyPreset"] = self.initial
        with self.db:
            self.db.execute("UPDATE imported_account SET startup_reads=?", (json.dumps(reads),))
        (self.references / TRIAL).touch()

    def call(self, body=None, route=DELETE, sequence=4001, now=NOW):
        return super().call(body, route, sequence, now)

    def group(self):
        return current_group(self.db)

    def body(self, ident=900, target=None, selected=False):
        row = copy.deepcopy(next(p for p in self.group()["Presets"] if p["Id"] == ident))
        row = {k: row[k] for k in ("Id", "Name", "Order", "Parties")}
        row["Parties"] = [
            {k: p[k] for k in ("Id", "Name", "Order", "Characters")} for p in row["Parties"]
        ]
        if target is not None:
            row.update(Id=target, Order=999)
        return {"MultiPartyPreset": row, "SetSelected": selected}

    def reject(self, body, route=DELETE, sequence=4001):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route, sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_selected_delete_changes_only_multi_group_selection_and_their_revisions(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        expected["User"]["SelectedPresetId"]["Expedition"] = 0
        expected["User"]["Cas"] += 1
        source = self.source.read_bytes()
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        group = copy.deepcopy(self.initial)
        group["Presets"].pop(0)
        group["Cas"] += 1
        reply = self.call({"PresetId": 900})
        self.assertEqual(reply["UserMultiPartyPreset"], group)
        self.assertEqual(reply["User"]["SelectedPresetId"], expected["User"]["SelectedPresetId"])
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.group(), group)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM party_preset_state").fetchone(), (0,)
        )
        self.assertEqual(self.call({}, "/preset/get-presets")["UserMultiPartyPreset"], group)

    def test_unselected_delete_preserves_raw_profile_and_other_mode_definitions(self):
        before = self.db.execute("SELECT profile FROM local_account").fetchone()[0]
        self.call({"PresetId": 901})
        self.assertEqual(self.db.execute("SELECT profile FROM local_account").fetchone()[0], before)
        self.assertEqual([p["Id"] for p in self.group()["Presets"]], [900, 1700])

    def test_delete_retry_after_recreation_does_not_remove_the_recreated_preset(self):
        self.call({"PresetId": 900})
        body = self.body(901, 900, selected=True)
        body["MultiPartyPreset"]["Name"] = "Recreated"
        self.call(body, SAVE, 4002)
        before = list(self.db.iterdump())
        reply = self.call({"PresetId": 900})
        self.assertEqual(reply["UserMultiPartyPreset"], self.group())
        self.assertTrue(
            any(p["Id"] == 900 and p["Name"] == "Recreated" for p in self.group()["Presets"])
        )
        self.assertEqual(list(self.db.iterdump()), before)
        self.reject({"PresetId": 901})

    def test_delete_last_expedition_slot_does_not_restore_the_imported_seed(self):
        self.call({"PresetId": 900})
        self.call({"PresetId": 901}, sequence=4002)
        self.assertEqual([p["Id"] for p in self.group()["Presets"]], [1700])
        self.open_session(reconnect=True)
        self.assertEqual(
            [
                p["Id"]
                for p in self.call({}, "/preset/get-presets")["UserMultiPartyPreset"]["Presets"]
            ],
            [1700],
        )

    def test_creation_appends_a_slot_with_native_empty_order_and_keeps_existing_rows(self):
        before = self.store.account.profile()
        body = self.body(target=903)
        self.call(body, SAVE)
        group = self.group()
        self.assertEqual(group["Presets"][:3], self.initial["Presets"])
        self.assertEqual(group["Presets"][-1]["Order"], 2)
        self.assertEqual(group["Presets"][-1]["Parties"], body["MultiPartyPreset"]["Parties"])
        self.assertEqual(self.store.account.profile(), before)

    def test_name_member_order_gear_and_party_changes_preserve_account_heroes_and_inventory(self):
        before = self.store.account.profile()
        body = self.body(901, selected=True)
        row = body["MultiPartyPreset"]
        row["Name"] = "Renamed"
        row["Parties"][0]["Characters"], row["Parties"][1]["Characters"] = (
            row["Parties"][1]["Characters"],
            row["Parties"][0]["Characters"],
        )
        row["Parties"][0]["Characters"].append(member(4, 11))
        del row["Parties"][0]["Characters"][0]["Weapon1"]
        self.call(body, SAVE)
        expected = copy.deepcopy(before)
        expected["User"]["SelectedPresetId"]["Expedition"] = 901
        expected["User"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        updated = next(p for p in self.group()["Presets"] if p["Id"] == 901)
        self.assertEqual(updated["Name"], "Renamed")
        self.assertIsNone(updated["Parties"][0]["Characters"][0]["Weapon1"])
        self.assertEqual(updated["Metadata"], "keep")
        self.assertEqual(updated["Parties"][0]["Metadata"], "keep-1")
        self.assertEqual(self.group()["Presets"][0], self.initial["Presets"][0])

    def test_saved_copy_can_be_selected_through_the_existing_selection_route(self):
        self.call(self.body(target=903), SAVE)
        self.call({"PresetId": 903}, "/preset/set-selected-preset", 4002)
        self.assertEqual(
            self.store.account.profile()["User"]["SelectedPresetId"]["Expedition"], 903
        )

    def test_empty_draft_can_be_saved_but_cannot_be_selected(self):
        body = self.body(target=903)
        for party in body["MultiPartyPreset"]["Parties"]:
            party["Characters"] = []
        self.call(body, SAVE)
        self.reject({"PresetId": 903}, "/preset/set-selected-preset", 4002)
        body["MultiPartyPreset"]["Order"] = 2
        body["SetSelected"] = True
        self.reject(body, SAVE, 4003)

    def test_save_retry_returns_later_state_without_overwriting_edits_or_resurrecting_rows(self):
        body = self.body()
        body["MultiPartyPreset"]["Name"] = "First"
        self.call(body, SAVE)
        later = copy.deepcopy(body)
        later["MultiPartyPreset"]["Name"] = "Later"
        self.call(later, SAVE, 4002)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(body, SAVE)["UserMultiPartyPreset"], self.group())
        self.assertEqual(list(self.db.iterdump()), before)
        self.call({"PresetId": 900}, DELETE, 4003)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(body, SAVE)["UserMultiPartyPreset"], self.group())
        self.assertEqual(list(self.db.iterdump()), before)

    def test_route_bound_identity_rejects_cross_operation_reuse(self):
        self.call({"PresetId": 901})
        self.reject(self.body(), SAVE)
        self.reject({"PresetType": 9, "Order": [0] * 20}, REORDER)

    def test_new_identical_save_is_a_noop_at_the_group_and_account_revision_ceiling(self):
        group = self.group()
        group["Cas"] = MAX_REVISION
        with self.db:
            self.db.execute(
                "INSERT INTO multi_party_preset_state VALUES(1,?)", (json.dumps(group),)
            )
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        self.call(self.body(selected=True), SAVE)
        self.assertEqual(self.group(), group)
        self.assertEqual(self.store.account.profile(), profile)
        body = self.body()
        body["MultiPartyPreset"]["Name"] = "Changed"
        self.reject(body, SAVE, 4002)
        self.reject({"PresetId": 900}, DELETE, 4003)

    def test_slot_creation_and_existing_order_changes_are_bounded(self):
        for ident in (True, 899, 920, 1700):
            body = self.body(target=ident)
            self.reject(body, SAVE)
        body = self.body(target=919)
        body["MultiPartyPreset"]["Order"] = 0
        self.reject(body, SAVE)
        body = self.body()
        body["MultiPartyPreset"]["Order"] = 1
        self.reject(body, SAVE)
        self.call(self.body(target=919), SAVE)
        self.assertEqual(self.group()["Presets"][-1]["Id"], 919)

    def test_malformed_multi_party_requests_and_foreign_modes_reject_without_writes(self):
        for body in (
            None,
            {},
            [],
            {"PresetId": True},
            {"PresetId": 899},
            {"PresetId": 920},
            {"PresetId": 1700},
            {"PresetId": 919},
            {"PresetId": 900, "Claim": True},
        ):
            self.reject(body)
        valid = self.body()
        for patch in (
            {"SetSelected": 1},
            {"SetSelected": None},
            {"Claim": True},
            {"MultiPartyPreset": None},
        ):
            self.reject(dict(valid, **patch), SAVE)
        for identity in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                delete(self.store.account, {"PresetId": 900}, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_parties_heroes_and_equipment_cannot_partially_edit_a_preset(self):
        for mutation in (
            lambda p: p.update(Parties=p["Parties"][:2]),
            lambda p: p["Parties"][0].update(Id=True),
            lambda p: p["Parties"][0].update(Id=2),
            lambda p: p["Parties"][0].update(Order=1),
            lambda p: p["Parties"][0].update(Characters=[member(9999, 11)]),
            lambda p: p["Parties"][0].update(Characters=[member(1, 9999)]),
            lambda p: p["Parties"][1].update(Characters=[member(1, 12)]),
            lambda p: p["Parties"][0]["Characters"].append(member(1, 11)),
            lambda p: p["Parties"][0]["Characters"][0].update(Experience=100),
            lambda p: p["Parties"][0].update(Name="bad\nname"),
            lambda p: p.update(Name="\ud800"),
            lambda p: p.update(Name="x" * 65),
        ):
            body = self.body()
            mutation(body["MultiPartyPreset"])
            self.reject(body, SAVE)

    def test_activation_and_signin_and_completed_account_guard_all_operations(self):
        body = self.body()
        self.session = BootstrapSession(self.store)
        self.reject({"PresetId": 900})
        self.reject(body, SAVE)
        self.open_session(reconnect=True)
        (self.references / TRIAL).unlink()
        self.reject({"PresetId": 900})
        self.reject(body, SAVE)
        self.reject({"PresetType": 9, "Order": [0, 1] + [0] * 18}, REORDER)
        (self.references / TRIAL).touch()
        with self.db:
            self.db.execute("DELETE FROM imported_account")
        self.reject({"PresetId": 900})
        self.reject(body, SAVE)

    def test_reorder_uses_multi_group_and_keeps_all_parties_and_other_presets(self):
        body = {"PresetType": 9, "Order": [1, 0] + [0] * 18}
        before = self.store.account.profile()
        expected = copy.deepcopy(self.initial)
        expected["Presets"][0]["Order"] = 1
        expected["Presets"][1]["Order"] = 0
        expected["Cas"] += 1
        self.assertEqual(self.call(body, REORDER), {"UserMultiPartyPreset": expected})
        self.assertEqual(self.group(), expected)
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM party_preset_state").fetchone(), (0,)
        )
        dump, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call(body, REORDER), {"UserMultiPartyPreset": expected})
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(self.db.total_changes, changes)

    def test_reorder_invalid_maps_cannot_change_other_mode_rows(self):
        for positions in (
            [],
            [0] * 19,
            [0] * 21,
            [0] * 20,
            [1, 1] + [0] * 18,
            [1, 0, 1] + [0] * 17,
            [20, 0] + [0] * 18,
            [True, 0] + [0] * 18,
        ):
            self.reject({"PresetType": 9, "Order": positions}, REORDER)
        self.reject({"PresetType": 9, "Order": [1, 0] + [0] * 18, "Claim": True}, REORDER)

    def test_reorder_delayed_retry_keeps_later_deletion_and_recreated_slot(self):
        order = {"PresetType": 9, "Order": [1, 0] + [0] * 18}
        self.call(order, REORDER)
        self.call({"PresetId": 901}, DELETE, 4002)
        self.call(self.body(target=901), SAVE, 4003)
        dump = list(self.db.iterdump())
        self.assertEqual(self.call(order, REORDER), {"UserMultiPartyPreset": self.group()})
        self.assertEqual(list(self.db.iterdump()), dump)

    def test_reopen_reconnect_and_fresh_login_keep_both_preset_resources(self):
        self.call(self.body(target=903), SAVE)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        for reconnect in (True, False):
            self.open_session(reconnect=reconnect)
            before = list(self.db.iterdump())
            read = self.call({}, "/preset/get-presets")
            self.assertEqual(read["UserMultiPartyPreset"], self.group())
            self.assertIn("UserPartyPreset2", read)
            self.assertTrue(any(p["Id"] == 903 for p in read["UserMultiPartyPreset"]["Presets"]))
            self.assertEqual(list(self.db.iterdump()), before)

    def test_receipt_failure_rolls_back_definition_selection_and_group_revision(self):
        with self.db:
            self.db.execute(
                "CREATE TRIGGER fail_multi BEFORE INSERT ON multi_preset_requests BEGIN SELECT RAISE(ABORT,'test failure'); END"
            )
        for route, body in (
            (DELETE, {"PresetId": 900}),
            (SAVE, self.body(target=903, selected=True)),
            (REORDER, {"PresetType": 9, "Order": [1, 0] + [0] * 18}),
        ):
            before = list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):
                self.call(body, route)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_equipment_protection_reads_the_mutable_multi_group_after_delete_or_edit(self):
        self.reject({"SellItems": {"11": 1}}, "/item/sell")
        body = self.body()
        del body["MultiPartyPreset"]["Parties"][0]["Characters"][0]["Weapon1"]
        self.call(body, SAVE)
        self.call({"SellItems": {"11": 1}}, "/item/sell", 4002)
        self.assertFalse(
            any(row["Id"] == 11 for row in self.store.account.profile()["User"]["ItemWeapons"])
        )

    def test_stale_or_invalid_unselected_gear_does_not_prevent_explicit_deletion(self):
        group = self.group()
        group["Presets"][0]["Parties"][0]["Characters"][0]["Weapon1"] = 9999
        with self.db:
            self.db.execute(
                "INSERT INTO multi_party_preset_state VALUES(1,?)", (json.dumps(group),)
            )
        self.call({"PresetId": 900})
        self.assertFalse(any(p["Id"] == 900 for p in self.group()["Presets"]))
