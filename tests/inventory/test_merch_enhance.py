# SPDX-License-Identifier: Apache-2.0
"""Exercise mixed-material forge requests on an imported save through the protocol."""

import copy
import json
import unittest

from guardian_tales.inventory.items import inventory_item
from guardian_tales.inventory.merch_enhance import ROUTE
from guardian_tales.modes.guild.raid_static import compress, decode, digest, records
from guardian_tales.runtime.protocol import PacketError
from tests.account.test_snapshots import request
from tests.village.test_village_harvest import VillageFixture


class MerchEnhanceTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.forge = {
            "Constants": {"DuplicateExpBonus": 3},
            "MerchLevels": [
                dict(Level=i, ExpNeeded=cost, ExpReward=gain, GoldNeeded=[30, 40, 50])
                for i, (cost, gain) in enumerate(
                    (
                        ([100, 200, 300], [11, 22, 33]),
                        ([300, 400, 500], [50, 60, 70]),
                        ([0] * 3, [88] * 3),
                    )
                )
            ],
            "MerchEvolves": [
                dict(Rarity=i, ProgressNeeded=cost, ProgressReward=gain, GoldNeeded=[20, 30, 40])
                for i, (cost, gain) in enumerate(
                    (
                        ([50, 0, 0], [50, 0, 0]),
                        ([75, 80, 0], [100, 50, 0]),
                        ([0] * 3, [175, 130, 70]),
                    )
                )
            ],
        }
        self.items = (
            [
                dict(
                    Id=i,
                    Type="merch",
                    GroupId=group,
                    OriginRarity=origin,
                    Rarity=rarity,
                    EvolveTo=next_id,
                )
                for i, group, origin, rarity, next_id in (
                    (1000, 1000, 0, 0, 1001),
                    (1001, 1000, 0, 1, 1002),
                    (1002, 1000, 0, 2, 0),
                    (2001, 2001, 1, 1, 0),
                )
            ]
            + [
                dict(Id=ident, Type="merchenhance", ExpReward=xp, GoldNeeded=30)
                for ident, xp in ((3000, 17), (3001, 29), (3002, 39))
            ]
            + [dict(Id=4000, Type="merchmaterial", GoldNeeded=25)]
        )
        values = {
            "merch": json.dumps(self.forge),
            "items": json.dumps(self.items),
            "__checksum__": "base",
        }
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(
            compress(
                "".join(
                    f"{key}\n{value}\n3\n{digest(value.encode())}\n"
                    for key, value in values.items()
                ).encode()
            )
        )
        p = self.store.account.profile()
        user = p["User"]
        user["ItemMiscs"] = [
            dict(inventory_item(51, 1000), Locked=True),
            dict(inventory_item(52, 1001), Experience=100),
            inventory_item(53, 2001),
        ]
        user["ItemStackables"] = [
            dict(inventory_item(n, spec), Amount=10)
            for n, spec in ((54, 3000), (55, 3001), (56, 3002), (57, 4000))
        ]
        user["Characters"][0]["Merch"] = 51
        user["ItemIdCounter"] = 57
        self.asset(p, 70001)["Amount"] = 0
        self.save_profile(p)

    def enhance(self, sources, sequence=51, **changes):
        return self.call(
            dict({"ItemId": 51, "SourceItems": sources, "discountBuff": False}, **changes),
            ROUTE,
            sequence,
        )

    def test_mixed_copies_and_glues_free_with_retry_and_multistar_cap(self):
        expected = self.store.account.profile()
        sources = {"52": 1, "53": 1, "54": 2, "55": 1, "56": 1}
        target = expected["User"]["ItemMiscs"][0]
        target.update(Experience=177, EvolveProgress=100, ItemId=1001)
        expected["User"]["Cas"] += 1
        self.assertEqual(self.enhance(sources), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.open_session(reconnect=True)
        self.assertEqual(
            self.enhance(dict(reversed(list(sources.items())))), {"User": expected["User"]}
        )
        with self.assertRaises(PacketError):
            self.enhance({"55": 1})
        target.update(Experience=400, EvolveProgress=125, ItemId=1002)
        expected["User"]["Cas"] += 1
        self.assertEqual(
            self.enhance(sources | {"56": 10}, 52, discountBuff=True), {"User": expected["User"]}
        )
        self.assertEqual(self.store.account.profile(), expected)
        with self.assertRaises(PacketError):
            self.enhance(sources, 53)
        self.assertEqual(self.store.account.profile(), expected)

    def test_glue_and_other_families_only_raise_experience(self):
        expected = self.store.account.profile()
        expected["User"]["Cas"] += 1
        expected["User"]["ItemMiscs"][0]["Experience"] = 90
        self.enhance({"54": 4, "53": 1})
        self.assertEqual(self.store.account.profile(), expected)

    def test_evolution_at_max_level_preserves_directly_granted_rarity(self):
        expected = self.store.account.profile()
        target = expected["User"]["ItemMiscs"][0]
        target.update(ItemId=1001, Experience=400, EvolveProgress=0)
        self.save_profile(expected)
        expected["User"]["Cas"] += 1
        target.update(ItemId=1002, EvolveProgress=125)
        self.assertEqual(self.enhance({"52": 1}), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)

    def test_single_material_can_cross_multiple_rarity_thresholds(self):
        expected = self.store.account.profile()
        expected["User"]["ItemMiscs"][1].update(ItemId=1002, Experience=0)
        self.save_profile(expected)
        expected["User"]["Cas"] += 1
        expected["User"]["ItemMiscs"][0].update(ItemId=1002, EvolveProgress=125, Experience=14)
        self.assertEqual(self.enhance({"52": 1}), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)

    def test_rejects_invalid_mixed_batches_without_partial_writes(self):
        p = self.store.account.profile()
        p["User"]["ItemMiscs"][1]["Locked"] = True
        self.save_profile(p)
        before = list(self.db.iterdump())
        for sources in (
            {"54": 1, "57": 1},
            {"54": 11},
            {"54": 0},
            {"51": 1},
            {"52": 1},
            {"53": 2},
            {"999": 1},
            {"054": 1},
            {"54": True},
            {},
        ):
            with self.subTest(sources=sources), self.assertRaises(PacketError):
                self.enhance(sources)
        with self.assertRaises(PacketError):
            self.enhance({"53": 1}, ItemId=54)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_client_prices_are_zero_and_matching_catalog_is_preserved(self):
        original = self.static.read_bytes()
        result = records(decode(self.session.handle(request("/static-data/get", {})).body))[1]
        expected = copy.deepcopy(self.forge)
        for table in ("MerchLevels", "MerchEvolves"):
            for row in expected[table]:
                row["GoldNeeded"] = [0, 0, 0]
        self.assertEqual(json.loads(result["merch"][1]), expected)
        self.assertEqual(
            json.loads(result["items"][1]),
            [dict(s, GoldNeeded=0) if s["Type"] == "merchenhance" else s for s in self.items],
        )
        checksum = result["__checksum__"][1]
        self.assertNotEqual(checksum, "base")
        self.assertTrue(self.call({"Checksum": checksum}, "/static-data/check-update")["UpToDate"])
        self.assertEqual(self.static.read_bytes(), original)
