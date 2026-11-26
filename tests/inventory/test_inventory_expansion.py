# SPDX-License-Identifier: Apache-2.0
"""Free storage upgrades use catalog targets and survive reconnects and retries."""

import json
import sqlite3
import unittest

from guardian_tales.inventory.inventory_expansion import ROUTE
from guardian_tales.modes.guild.raid_static import compress, decode, digest, records
from guardian_tales.runtime.protocol import PacketError
from guardian_tales.settlement.village import MAX_REVISION
from tests.account.test_snapshots import request
from tests.village.test_village_harvest import VillageFixture


class InventoryExpansionTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.static = self.references / "static_data_get.bin"
        self.steps = [
            {
                "InvenExpandCount": n,
                "InvenExpandCost": 3 * n,
                "InvenTotalExpandCost": 3 * n * (n + 1) // 2,
            }
            for n in range(1, 6)
        ]
        self.write_static()

    def write_static(self, slots=7):
        tables = {
            "constants": json.dumps(
                {"InvenExpandAmount": slots, "DefaultInventoryLimit": 90, "ChangeNickCost": 80}
            ),
            "inventoryexpansion": json.dumps(self.steps),
            "__checksum__": "synthetic",
        }
        text = "".join(
            f"{key}\n{value}\n4\n{digest(value.encode())}\n" for key, value in tables.items()
        )
        self.static.write_bytes(compress(text.encode()))

    def expand(self, step, sequence):
        return self.call({"TargetStep": step}, ROUTE, sequence)

    def test_single_multiple_and_max_with_empty_wallet(self):
        expected = self.store.account.profile()
        for asset in expected["User"]["Assets"]:
            asset["Amount"] = 0
        self.save_profile(expected)
        user = expected["User"]
        for sequence, target in enumerate((1, 3, 5), 51):
            user["InvenLimitAdj"] = 7 * target
            user["Cas"] += 1
            reply = self.expand(target, sequence)
            self.assertEqual(reply, {"User": {k: user[k] for k in ("Id", "Cas", "InvenLimitAdj")}})
            self.assertEqual(self.store.account.profile(), expected)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(reconnect=True)
        for target, sequence in ((3, 52), (5, 54), (1, 55)):
            self.assertEqual(self.expand(target, sequence), reply)
        self.assertEqual(self.store.account.profile(), expected)

    def test_invalid_requests_do_not_change_capacity_or_receipts(self):
        self.expand(2, 51)
        before = list(self.db.iterdump())
        for step, sequence in ((4, 51), (True, 52), ("3", 52), (0, 52), (-1, 52), (6, 52)):
            with self.subTest(step=step, sequence=sequence), self.assertRaises(PacketError):
                self.expand(step, sequence)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_catalog_and_saved_capacity_determine_the_result(self):
        self.steps += [{"InvenExpandCount": 6, "InvenExpandCost": 120, "InvenTotalExpandCost": 800}]
        self.write_static(slots=9)
        profile = self.store.account.profile()
        del profile["User"]["InvenLimitAdj"]
        self.save_profile(profile)
        self.assertEqual(self.expand(6, 51)["User"]["InvenLimitAdj"], 54)
        profile = self.store.account.profile()
        profile["User"].update(InvenLimitAdj=62, Cas=MAX_REVISION)
        self.save_profile(profile)
        self.assertEqual(self.expand(6, 52)["User"]["InvenLimitAdj"], 62)
        self.assertEqual(self.store.account.profile(), profile)

    def test_client_get_and_check_serve_free_steps_and_preserve_the_external_catalog(self):
        original = self.static.read_bytes()
        result = self.session.handle(request("/static-data/get", {})).body
        tables = records(decode(result))[1]
        self.assertEqual(
            json.loads(tables["inventoryexpansion"][1]),
            [dict(row, InvenExpandCost=0, InvenTotalExpandCost=0) for row in self.steps],
        )
        self.assertEqual(
            json.loads(tables["constants"][1]),
            {
                "InvenExpandAmount": 7,
                "DefaultInventoryLimit": 90,
                "ChangeNickCost": 0,
            },
        )
        checksum = tables["__checksum__"][1]
        for prior, current in (("synthetic", False), (checksum, True)):
            check = self.call({"Checksum": prior}, "/static-data/check-update")
            self.assertEqual(check["UpToDate"], current)
            self.assertEqual(check["Checksum"], checksum)
        self.assertEqual(self.static.read_bytes(), original)
