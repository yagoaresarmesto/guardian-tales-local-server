# SPDX-License-Identifier: Apache-2.0
"""Preset response size stays independent of inventory and retains current retry state."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import read_json_body
from guardian_tales.presets import current_group
from guardian_tales.protocol import Packet, decode_frame, encode_wire
from tests.teams.test_preset_edit import PresetFixture


class PresetPayloadTests(PresetFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        profile = self.store.account.profile()
        template = profile["User"]["ItemWeapons"][0]
        for ident in range(3, 503):
            profile["User"]["ItemWeapons"].append(dict(copy.deepcopy(template), Id=ident))
        profile["User"]["SelectedPresetId"]["GuildRaidAndConquest"] = 713
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.initial_profile = profile

    def check_payload(self, response):
        user = self.store.account.profile()["User"]
        self.assertEqual(
            response["User"],
            {"Id": user["Id"], "Cas": user["Cas"], "SelectedPresetId": user["SelectedPresetId"]},
        )
        self.assertEqual(user["ItemWeapons"], self.initial_profile["User"]["ItemWeapons"])
        self.assertEqual(user["Characters"], self.initial_profile["User"]["Characters"])
        self.assertEqual(user["Assets"], self.initial_profile["User"]["Assets"])
        self.assertEqual(response["User"]["SelectedPresetId"]["Rift"], 101)
        self.assertEqual(response["User"]["SelectedPresetId"]["GuildRaidAndConquest"], 713)
        body = json.dumps(response, separators=(",", ":")).encode()
        full = dict(response, User=user)
        self.assertLess(len(body), len(json.dumps(full).encode()) // 10)
        wire = encode_wire(Packet(1, body=body, body_type=1, sequence_id=31), 123, nonce=5)
        self.assertEqual(read_json_body(decode_frame(wire, 123)), response)
        if "UserPartyPreset2" in response:
            self.assertEqual(response["UserPartyPreset2"], current_group(self.db))
        return body

    def test_selection_and_reconnect_retry_have_small_current_resources(self):
        first = self.call({"PresetId": 402}, "/preset/set-selected-preset")
        self.assertLess(len(self.check_payload(first)), 512)
        self.call({"PresetId": 401}, "/preset/set-selected-preset", 32)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        before = list(self.db.iterdump())
        retry = self.call({"PresetId": 402}, "/preset/set-selected-preset")
        self.assertEqual(retry["User"]["SelectedPresetId"]["InfiniteTower"], 401)
        self.check_payload(retry)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_edit_keeps_full_group_and_same_wire_size_after_inventory_growth(self):
        body = self.body()
        body["PartyPreset"]["Name"] = "Edited"
        first = self.call(body)
        size = len(self.check_payload(first))
        profile = self.store.account.profile()
        profile["User"]["ItemStackables"] = [{"Id": v, "Amount": 10} for v in range(1000)]
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.assertEqual(len(self.check_payload(self.call(body))), size)
        self.assertEqual(self.store.account.profile(), profile)

    def test_selected_delete_returns_zero_pointer_and_complete_remaining_group(self):
        response = self.call({"PresetId": 401}, "/preset/delete-preset")
        self.check_payload(response)
        self.assertEqual(response["User"]["SelectedPresetId"]["InfiniteTower"], 0)
        self.assertEqual([p["Id"] for p in response["UserPartyPreset2"]["Presets"]], [101, 402])
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"PresetId": 401}, "/preset/delete-preset"), response)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_create_and_apply_returns_full_new_definition_with_compact_choice(self):
        (self.references / "orbital_preset_catalog.json").write_text(
            json.dumps(
                {"client": {"version": "3.57.0", "version_code": 431, "region": "eu"}, "count": 5}
            )
        )
        body = self.body(selected=True)
        body["PartyPreset"].update(Id=403, Order=999)
        response = self.call(body)
        self.check_payload(response)
        self.assertEqual(response["User"]["SelectedPresetId"]["InfiniteTower"], 403)
        self.assertEqual(
            [p["Id"] for p in response["UserPartyPreset2"]["Presets"]], [101, 401, 402, 403]
        )
