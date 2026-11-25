# SPDX-License-Identifier: Apache-2.0
"""Native relic inlaying opens an empty socket and spends its ticket exactly once."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.items import inventory_item
from guardian_tales.jewel_socket import ROUTE
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, digest
from tests.test_village_harvest import NOW, VillageFixture


class JewelSocketTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.rules = {
            "constants": {"InlaidCount": {"KakaoGlobal": 1}},
            "InlaidCount": [{"Count": 1, "CountUpNeeded": 1}, {"Count": 2, "CountUpNeeded": 3}],
        }
        self.items = [
            {"Id": 701, "Type": "relic", "OriginRarity": 4},
            {"Id": 702, "Type": "relic", "OriginRarity": 3},
            {"Id": 703, "Name": "inlaid_ticket", "Type": "ticket"},
        ]
        self.write_rules()
        profile = self.store.account.profile()
        relic = inventory_item(51, 701)
        relic.update(Locked=True, RelicOptions={"Example": 10})
        user = profile["User"]
        user["ItemMiscs"].extend([relic, inventory_item(52, 702)])
        user["ItemStackables"].append(inventory_item(53, 703))
        user["Characters"][0]["Relic"] = 51
        user["ItemIdCounter"] = 53
        self.save_profile(profile)

    def write_rules(self):
        text = ""
        for name, value in (("items", self.items), ("inlaid", self.rules)):
            content = json.dumps(value)
            text += f"{name}\n{content}\n1\n{digest(content.encode())}\n"
        (self.references / "static_data_get.bin").write_bytes(compress(text.encode()))

    def call(self, body=None, route=ROUTE, sequence=51, now=NOW):
        return super().call(body, route, sequence, now)

    def test_open_equipped_locked_relic_then_retry_after_reconnect(self):
        expected = self.store.account.profile()
        user = expected["User"]
        user["ItemMiscs"][-2]["JewelSlots"] = [0]
        user["ItemStackables"].pop()
        user["Cas"] += 1
        record = expected["UserRecord"]
        record["Misc"]["InlaidCount"] += 1
        record["Cas"] += 1
        self.assertEqual(self.call({"RelicId": 51}), {"User": user, "UserRecord": record})
        self.assertEqual(self.store.account.profile(), expected)
        self.open_session(reconnect=True)
        (self.references / "static_data_get.bin").unlink()
        writes = self.db.total_changes
        self.assertEqual(self.call({"RelicId": 51}), {"User": user, "UserRecord": record})
        self.assertEqual(self.db.total_changes, writes)
        self.reject_without_writes({"RelicId": 52})

    def test_next_slot_uses_configured_price_and_retains_previous_jewel(self):
        self.rules["constants"]["InlaidCount"]["KakaoGlobal"] = 2
        self.write_rules()
        profile = self.store.account.profile()
        user = profile["User"]
        user["ItemMiscs"][-2]["JewelSlots"] = [901]
        user["ItemStackables"].append(dict(inventory_item(54, 703), Amount=3))
        self.save_profile(profile)
        response = self.call({"RelicId": 51})["User"]
        self.assertEqual(response["ItemMiscs"][-2]["JewelSlots"], [901, 0])
        self.assertEqual(
            [(i["Id"], i["Amount"]) for i in response["ItemStackables"] if i["ItemId"] == 703],
            [(54, 1)],
        )
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call({"RelicId": 51}, sequence=52)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_open_first_socket_on_save_with_empty_slots_and_no_misc_record(self):
        profile = self.store.account.profile()
        profile["UserRecord"]["Misc"] = None
        profile["User"]["ItemMiscs"][-2]["JewelSlots"] = []
        self.save_profile(profile)
        response = self.call({"RelicId": 51})
        self.assertEqual(response["User"]["ItemMiscs"][-2]["JewelSlots"], [0])
        self.assertEqual(response["UserRecord"]["Misc"], {"InlaidCount": 1})

    def test_ineligible_relic_invalid_request_and_insufficient_tickets(self):
        for body in (
            None,
            {"RelicId": 52},
            {"RelicId": 53},
            {"RelicId": 701},
            {"RelicId": True},
            {"RelicId": 51, "SlotIndex": 0},
        ):
            with self.subTest(body=body):
                self.reject_without_writes(body)
        profile = self.store.account.profile()
        profile["User"]["ItemStackables"].pop()
        self.save_profile(profile)
        self.reject_without_writes({"RelicId": 51})

    def test_duplicate_material_stacks_or_missing_rules_do_not_change_inventory(self):
        profile = self.store.account.profile()
        invalid = copy.deepcopy(profile)
        invalid["User"]["ItemStackables"].append(inventory_item(53, 703))
        self.save_profile(invalid)
        self.reject_without_writes({"RelicId": 51})
        self.save_profile(profile)
        self.rules["InlaidCount"].pop(0)
        self.write_rules()
        self.reject_without_writes({"RelicId": 51})

    def test_receipt_failure_rolls_back_slot_ticket_and_record(self):
        before = self.store.account.profile()
        self.db.execute(
            "CREATE TRIGGER reject_inlay BEFORE INSERT ON jewel_socket_requests "
            "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.call({"RelicId": 51})
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM jewel_socket_requests").fetchone(), (0,)
        )
