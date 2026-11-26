# SPDX-License-Identifier: Apache-2.0
"""Equipment choices, debit and retry behavior through the native game route."""

import json
import unittest

from guardian_tales.inventory.items import inventory_item
from guardian_tales.inventory.selection_box import ROUTE
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.protocol import PacketError
from tests.village.test_village_harvest import VillageFixture


class SelectionBoxTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        items = [
            dict(
                Id=51,
                Type="selectionbox",
                Rewards=[
                    dict(ItemId=200, Level=0, Amount=1),
                    dict(ItemId=201, Level=1, Amount=1),
                    dict(CharacterId=40, Level=4),
                ],
            ),
            dict(Id=200, Type="weapon", MinOptions=0, MaxOptions=0),
            dict(
                Id=201,
                Type="weapon",
                MinOptions=1,
                MaxOptions=1,
                Options=[dict(OptionId=9, Probability=1, MinLevel=2, MaxLevel=4)],
            ),
            dict(Id=202, Type="enhancehammer"),
        ]
        tables = dict(
            items=items,
            options=[{"Id": 9}],
            constants={"DefaultInventoryLimit": 3},
            weaponenhance={"LevelExps": [{"Level": 0, "TotalExps": 200}]},
        )
        parts = []
        for key, value in tables.items():
            data = json.dumps(value)
            parts.append(f"{key}\n{data}\n1\n{digest(data.encode())}\n")
        (self.references / "static_data_get.bin").write_bytes(compress("".join(parts).encode()))
        profile = self.store.account.profile()
        profile["User"].update(
            ItemWeapons=[],
            ItemMiscs=[],
            ItemStackables=[dict(inventory_item(90, 51), Amount=2)],
            InvenLimitAdj=0,
            ItemIdCounter=90,
        )
        self.save_profile(profile)

    def test_chosen_weapon_consumes_one_box_and_replays_the_original_roll(self):
        first = self.call({"boxId": 51, "index": 1}, ROUTE, 51)
        item = first["AddedItems"][0]
        self.assertEqual((item["Id"], item["ItemId"], item["Experience"]), (91, 201, 200))
        self.assertEqual(item["Options"][0]["OptionId"], 9)
        self.assertIn(item["Options"][0]["Level"], range(2, 5))
        self.assertEqual(first["User"]["ItemWeapons"], [item])
        self.assertEqual(first["User"]["ItemStackables"][0]["Amount"], 1)
        second = self.call({"boxId": 90, "index": 0}, ROUTE, 52)
        self.assertEqual(second["User"]["ItemStackables"], [])
        self.assertEqual(second["AddedItems"], [inventory_item(92, 200)])
        self.open_session(reconnect=True)
        changes = self.db.total_changes
        replay = self.call({"boxId": 51, "index": 1}, ROUTE, 51)
        self.assertEqual(replay["User"], second["User"])
        self.assertEqual(replay["AddedItems"], [item])
        with self.assertRaises(PacketError):
            self.call({"boxId": 51, "index": 0}, ROUTE, 51)
        with self.assertRaises(PacketError):
            self.call({"boxId": 51, "index": 1}, ROUTE, 53)
        self.assertEqual(self.db.total_changes, changes)

    def test_invalid_choices_and_full_inventory_preserve_box_and_save(self):
        profile = self.store.account.profile()
        for box, index in ((51, -1), (51, True), (51, 2), (51, 3), (123, 0)):
            with self.subTest(box=box, index=index), self.assertRaises(PacketError):
                self.call({"boxId": box, "index": index}, ROUTE)
        self.assertEqual(self.store.account.profile(), profile)
        user = profile["User"]
        user["ItemWeapons"] = [inventory_item(1, 200), inventory_item(2, 201)]
        user["ItemStackables"].append(inventory_item(3, 202))
        self.save_profile(profile)
        with self.assertRaises(PacketError):
            self.call({"boxId": 51, "index": 0}, ROUTE)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM selection_box_requests").fetchone()[0], 0
        )
