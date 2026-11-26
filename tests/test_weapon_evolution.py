# SPDX-License-Identifier: Apache-2.0
"""Normal equipment evolution through the native forge request."""

import json
import unittest

from guardian_tales.items import inventory_item
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from guardian_tales.weapon_evolution import ROUTE
from tests.test_snapshots import request
from tests.test_village_harvest import VillageFixture


class WeaponEvolutionTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        specs = [
            dict(
                Id=200 + i,
                Name=f"sword_{i}",
                NameWithoutRarity="sword",
                WeaponType="onehandsword",
                Type="weapon",
                OriginRarity=0,
                Rarity=i,
                MinOptions=0,
                MaxOptions=0,
                EvolveTo={"Default": 201 + i},
            )
            for i in range(6)
        ]
        for spec in specs[1:]:
            spec.update(
                MinOptions=1,
                MaxOptions=1,
                Options=[dict(OptionId=7, Probability=1, MinLevel=spec["Rarity"], MaxLevel=10)],
            )
        specs.extend(
            dict(
                specs[i],
                Id=300 + i,
                Name=f"shield_{i}",
                NameWithoutRarity="shield",
                WeaponType="shield",
                EvolveTo={"Default": 999, "KakaoGlobal": 301} if i == 0 else None,
            )
            for i in range(2)
        )
        self.prices = [dict(Rarity=i, GoldCost=100 * i + 1) for i in range(4)]
        tables = {
            "items": specs,
            "options": [{"Id": 7}],
            "weaponenhance": {"WeaponEvolve": self.prices, "WeaponMyth": [{"GoldCost": 123}]},
        }
        values = {k: json.dumps(v) for k, v in tables.items()}
        values["__checksum__"] = "base"
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(
            compress(
                "".join(f"{k}\n{v}\n1\n{digest(v.encode())}\n" for k, v in values.items()).encode()
            )
        )
        profile = self.store.account.profile()
        user = profile["User"]
        self.asset(profile, 70001)["Amount"] = 0
        user["ItemWeapons"] = [
            dict(inventory_item(50 + i, spec), Experience=123, Locked=True)
            for i, spec in enumerate((200, 201, 202, 203, 204, 300))
        ]
        user["ItemIdCounter"] = 55
        user["ItemWeapons"][3]["Options"] = [dict(OptionId=7, Level=6, Locked=True, OptionSource=0)]
        user["Characters"][0]["Weapon"] = 53
        self.save_profile(profile)

    def evolve(self, ids, *, to_max=False, seq=51, discount=False):
        return self.call(
            {"WeaponIds": ids, "EvolveToMaxRarity": to_max, "discountBuff": discount}, ROUTE, seq
        )

    def test_all_starting_ranks_evolve_once_and_keep_each_copy(self):
        before = self.store.account.profile()["User"]
        result = self.evolve([50, 51, 52, 53], discount=True)
        user = result["User"]
        self.assertEqual(user["Assets"], before["Assets"])
        self.assertEqual(user["Characters"], before["Characters"])
        self.assertEqual(user["ItemIdCounter"], before["ItemIdCounter"])
        self.assertEqual(user["Cas"], before["Cas"] + 1)
        for index in range(4):
            old, new = before["ItemWeapons"][index], user["ItemWeapons"][index]
            self.assertEqual(new, dict(old, ItemId=old["ItemId"] + 1, Options=new["Options"]))
            self.assertEqual(new["Options"][0]["OptionId"], 7)
            self.assertGreaterEqual(new["Options"][0]["Level"], index + 1)
        self.assertEqual(user["ItemWeapons"][3]["Options"], before["ItemWeapons"][3]["Options"])
        self.assertEqual(result["UserRecord"]["EvolveWeaponCount"], dict.fromkeys("1234", 1))
        self.open_session(reconnect=True)
        before_retry = self.db.total_changes
        self.assertEqual(result, self.evolve([53, 52, 51, 50], discount=True))
        self.assertEqual(self.db.total_changes, before_retry)
        with self.assertRaises(PacketError):
            self.evolve([50], to_max=True)

    def test_max_stops_at_each_familys_normal_limit(self):
        result = self.evolve([50, 55], to_max=True)
        rows = result["User"]["ItemWeapons"]
        self.assertEqual((rows[0]["ItemId"], rows[-1]["ItemId"]), (204, 301))
        self.assertEqual(
            result["UserRecord"]["EvolveWeaponCount"], {"1": 2, "2": 1, "3": 1, "4": 1}
        )
        with self.assertRaises(PacketError):
            self.evolve([50], seq=52)

    def test_bad_batch_is_atomic(self):
        before = list(self.db.iterdump())
        for ids in ([50, 54], [50, 999], [50, 50], [True], []):
            with self.subTest(ids=ids), self.assertRaises(PacketError):
                self.evolve(ids)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_native_price_overlay_only_changes_normal_evolution_cost(self):
        original = self.static.read_bytes()
        raw = decode(self.session.handle(request("/static-data/get", {})).body)
        table = json.loads(records(raw)[1]["weaponenhance"][1])
        self.assertEqual(table["WeaponEvolve"], [dict(s, GoldCost=0) for s in self.prices])
        self.assertEqual(table["WeaponMyth"], [{"GoldCost": 123}])
        self.assertEqual(self.static.read_bytes(), original)
