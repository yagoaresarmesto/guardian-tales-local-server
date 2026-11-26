# SPDX-License-Identifier: Apache-2.0
"""Normal and Grade 6 equipment evolution through the native forge requests."""

import json
import unittest

from guardian_tales.items import inventory_item
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from guardian_tales.weapon_evolution import MYTH_ROUTE, ROUTE
from tests.account.test_snapshots import request
from tests.village.test_village_harvest import VillageFixture


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
        self.myth_prices = [
            dict(Rarity=5, OriginRarity=origin, Costs=[dict(ItemId=110018, Amount=amount)])
            for origin, amount in ((3, 500), (4, 1000))
        ]
        for base, origin in ((400, 3), (500, 4)):
            for rank in (4, 5):
                specs.append(
                    dict(
                        specs[4],
                        Id=base + rank,
                        Name=f"exclusive_{base}_{rank}",
                        NameWithoutRarity=f"exclusive_{base}",
                        OriginRarity=origin,
                        Rarity=rank,
                        EvolveTo={"Default": 999, "KakaoGlobal": base + 5} if rank == 4 else None,
                    )
                )
        tables = {
            "items": specs,
            "options": [{"Id": 7}],
            "weaponenhance": {"WeaponEvolve": self.prices, "WeaponMyth": self.myth_prices},
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
            for i, spec in enumerate((200, 201, 202, 203, 204, 300, 404, 504))
        ]
        user["ItemIdCounter"] = 57
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
        self.assertEqual((rows[0]["ItemId"], rows[5]["ItemId"]), (204, 301))
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

    def test_grade_six_retains_copy_and_resources_for_both_origin_rarities(self):
        profile = self.store.account.profile()
        first = profile["User"]["ItemWeapons"][6]
        first.update(
            Options=[dict(OptionId=7, Level=8, Locked=True, OptionSource=0)],
            LimitBreaks=0,
            EngraveCeiling=1,
            EngraveOptions=[dict(OptionId=9, Level=2)],
        )
        profile["User"]["Characters"][0]["Weapon"] = first["Id"]
        profile["User"]["ItemWeapons"][7]["LimitBreaks"] = 5
        self.save_profile(profile)
        for seq, index in ((51, 6), (52, 7)):
            item = profile["User"]["ItemWeapons"][index]
            body = {"targetWeaponId": item["Id"]}
            result = self.call(body, MYTH_ROUTE, seq)
            item["ItemId"] += 1
            profile["User"]["Cas"] += 1
            profile["UserRecord"]["Cas"] += 1
            profile["UserRecord"]["EvolveWeaponCount"]["5"] = seq - 50
            self.assertEqual(result, {"User": profile["User"], "UserRecord": profile["UserRecord"]})
            self.assertEqual(self.store.account.profile(), profile)
            self.open_session(reconnect=True)
            changes = self.db.total_changes
            self.assertEqual(self.call(body, MYTH_ROUTE, seq), result)
            self.assertEqual(changes, self.db.total_changes)
            with self.assertRaises(PacketError):
                self.call(body, MYTH_ROUTE, seq + 100)
        with self.assertRaises(PacketError):
            self.evolve([50], seq=52)

    def test_grade_six_rejects_training_invalid_forms_and_wrong_inventory_ids(self):
        p = self.store.account.profile()
        p["User"]["TrainingSlots"] = {"1": {"ItemId": 56}}
        self.save_profile(p)
        before = list(self.db.iterdump())
        for ident in (56, 50, 54, 404, 999, True):
            with self.subTest(ident=ident), self.assertRaises(PacketError):
                self.call({"targetWeaponId": ident}, MYTH_ROUTE, 51)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_native_forge_prices_keep_the_grade_six_material_icon(self):
        original = self.static.read_bytes()
        raw = decode(self.session.handle(request("/static-data/get", {})).body)
        table = json.loads(records(raw)[1]["weaponenhance"][1])
        self.assertEqual(table["WeaponEvolve"], [dict(s, GoldCost=0) for s in self.prices])
        self.assertEqual(
            table["WeaponMyth"],
            [dict(row, Costs=[dict(ItemId=110018, Amount=0)]) for row in self.myth_prices],
        )
        self.assertEqual(self.static.read_bytes(), original)
