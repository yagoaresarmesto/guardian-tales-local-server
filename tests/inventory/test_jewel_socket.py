# SPDX-License-Identifier: Apache-2.0
"""Native relic inlaying opens an empty socket and spends its ticket exactly once."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.inventory.items import inventory_item
from guardian_tales.inventory.jewel_socket import ATTACH, DETACH, ROUTE, create_tables
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.protocol import PacketError
from tests.village.test_village_harvest import NOW, VillageFixture


class JewelSocketTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.rules = {
            "constants": {"InlaidCount": {"KakaoGlobal": 1}, "DetachCost": 300},
            "InlaidCount": [{"Count": 1, "CountUpNeeded": 1}, {"Count": 2, "CountUpNeeded": 3}],
        }
        self.items = [
            {"Id": 701, "Type": "relic", "OriginRarity": 4},
            {"Id": 702, "Type": "relic", "OriginRarity": 3},
            {"Id": 703, "Name": "inlaid_ticket", "Type": "ticket"},
            {"Id": 901, "Type": "jewel", "GroupId": 1},
            {"Id": 902, "Type": "jewel", "GroupId": 1},
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

    def prepare_jewels(self, old=0, locked=False):
        profile = self.store.account.profile()
        user = profile["User"]
        user["ItemMiscs"][-2].update(JewelSlots=[old], Locked=locked)
        user["ItemStackables"].append(inventory_item(54, 902))
        user["ItemIdCounter"] = 54
        for ident, amount in ((70003, 240), (70002, 100)):
            self.asset(profile, ident).update(Amount=amount, Spent=15)
        self.save_profile(profile)
        return profile

    def test_attach_and_detach_uses_one_owned_unit_and_returns_to_same_stack(self):
        before = self.prepare_jewels(locked=True)
        socket = {"RelicId": 51, "SlotIndex": 0}
        attach = dict(socket, JewelId=54, Destruction=False)
        mounted = self.call(attach, ATTACH)
        self.assertEqual(mounted["User"]["ItemMiscs"][-2]["JewelSlots"], [902])
        self.assertEqual(mounted["User"]["ItemStackables"][-1]["Amount"], 0)
        self.assertEqual(mounted["User"]["Assets"], before["User"]["Assets"])
        self.assertEqual(
            mounted["UserRecord"]["Misc"]["AttachJewelCount"],
            before["UserRecord"]["Misc"]["AttachJewelCount"] + 1,
        )
        self.open_session(reconnect=True)
        self.assertEqual(self.call(dict(socket, JewelId=54), ATTACH), mounted)
        with self.assertRaises(PacketError):
            self.call(socket, DETACH, sequence=52)
        self.assertEqual(self.store.account.profile()["User"], mounted["User"])
        profile = self.store.account.profile()
        profile["User"]["ItemMiscs"][-2]["Locked"] = False
        self.save_profile(profile)
        returned = self.call(socket, DETACH, sequence=53)
        self.assertEqual(returned["User"]["ItemMiscs"][-2]["JewelSlots"], [0])
        self.assertEqual(returned["User"]["ItemStackables"], before["User"]["ItemStackables"])
        self.assertEqual(returned["User"]["Characters"], before["User"]["Characters"])
        self.assertEqual(
            returned["UserRecord"]["Misc"]["DetachJewelCount"],
            before["UserRecord"]["Misc"]["DetachJewelCount"] + 1,
        )
        for ident, amount, spent in ((70003, 0, 255), (70002, 40, 75)):
            balance = self.asset(returned, ident)
            self.assertEqual((balance["Amount"], balance["Spent"]), (amount, spent))
        self.assertEqual(self.call(socket, DETACH, sequence=53), returned)
        # Replaying the old attach must not re-equip the returned jewel.
        self.assertEqual(self.call(attach, ATTACH), returned)

    def test_replace_and_return_old_jewel_or_explicitly_destroy_it(self):
        request = {"RelicId": 51, "SlotIndex": 0, "JewelId": 54}
        initial = self.prepare_jewels(old=901)
        for sequence, destroy in enumerate((False, True), start=60):
            with self.subTest(destroy=destroy):
                self.save_profile(initial)
                result = self.call(dict(request, Destruction=destroy), ATTACH, sequence)
                self.assertEqual(result["User"]["ItemMiscs"][-2]["JewelSlots"], [902])
                matches = [r for r in result["User"]["ItemStackables"] if r["ItemId"] == 901]
                self.assertEqual([r["Amount"] for r in matches], [] if destroy else [1])
                self.assertEqual(self.asset(result, 70003)["Amount"], 240 if destroy else 0)
                before = list(self.db.iterdump())
                with self.assertRaises(PacketError):
                    self.call(dict(request, Destruction=not destroy), ATTACH, sequence)
                self.assertEqual(list(self.db.iterdump()), before)

    def test_rejected_jewel_actions_leave_slot_balances_and_counters_intact(self):
        initial = self.prepare_jewels(old=901)
        socket = {"RelicId": 51, "SlotIndex": 0}
        attach = dict(socket, JewelId=54, Destruction=False)
        for route, request, edit in (
            (ATTACH, dict(attach, SlotIndex=1), None),
            (ATTACH, dict(attach, JewelId=902), None),
            (ATTACH, dict(attach, Destruction=1), None),
            (ATTACH, attach, lambda p: p["User"]["ItemStackables"][-1].update(Locked=True)),
            (ATTACH, attach, lambda p: p["User"]["ItemStackables"][-1].update(Amount=0)),
            (ATTACH, attach, lambda p: self.asset(p, 70002).update(Amount=0)),
            (DETACH, socket, lambda p: p["User"]["ItemMiscs"][-2].update(JewelSlots=[0])),
            (DETACH, socket, lambda p: p["User"]["ItemMiscs"][-2].update(JewelSlots=[999])),
            (DETACH, socket, lambda p: self.asset(p, 70002).update(Amount=0)),
        ):
            profile = copy.deepcopy(initial)
            if edit:
                edit(profile)
            self.save_profile(profile)
            before = list(self.db.iterdump())
            with self.subTest(route=route, request=request), self.assertRaises(PacketError):
                self.call(request, route)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_original_inlay_receipts_survive_upgrade_and_reject_other_actions(self):
        self.call({"RelicId": 51})
        with self.db:
            self.db.execute("ALTER TABLE jewel_socket_requests RENAME TO new_receipts")
            self.db.execute(
                "CREATE TABLE jewel_socket_requests "
                "(operation_id TEXT PRIMARY KEY, relic_id INTEGER NOT NULL)"
            )
            self.db.execute(
                "INSERT INTO jewel_socket_requests SELECT operation_id,relic_id FROM new_receipts"
            )
            self.db.execute("DROP TABLE new_receipts")
            create_tables(self.db)
        before = list(self.db.iterdump())
        self.call({"RelicId": 51})
        with self.assertRaises(PacketError):
            self.call({"RelicId": 51, "SlotIndex": 0}, DETACH)
        self.assertEqual(list(self.db.iterdump()), before)
