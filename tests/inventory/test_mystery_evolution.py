# SPDX-License-Identifier: Apache-2.0
"""Exercise both native mystery evolution requests and their persisted outcomes."""

import json
import unittest
from unittest.mock import patch

from guardian_tales.items import inventory_item
from guardian_tales.mystery_evolution import AUTO, MANUAL
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from tests.account.test_snapshots import request
from tests.village.test_village_harvest import VillageFixture


class MysteryEvolutionTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        items = [
            dict(
                Id=100 + i,
                Type="weapon",
                Name=f"gear_{i}",
                WeaponType="shield",
                Rarity=i,
                Limited=False,
                Composable=True,
                MinOptions=0,
                MaxOptions=0,
            )
            for i in range(6)
        ]
        items[4].update(
            MinOptions=1,
            MaxOptions=1,
            Options=[dict(OptionId=7, Probability=1, MinLevel=3, MaxLevel=3)],
        )
        items.extend(
            [
                dict(items[4], Id=200, Name="excluded", Composable=False),
                dict(items[4], Id=201, Name="limited", Limited=True),
                dict(items[4], Id=202, Name="future", VersionFrom={"KakaoGlobal": "v99.0"}),
                dict(items[4], Id=203, Name="exclusive", ExclusiveCharacterId=440),
            ]
        )
        tables = dict(
            items=items,
            options=[{"Id": 7}],
            weaponenhance={
                "WeaponCompose": [
                    dict(
                        Rarity=i,
                        Probability=([0.5, 1] if i < 4 else None),
                        GoldCost=20,
                        ExclusiveProbability=(0.05 if i == 3 else -1),
                    )
                    for i in range(5)
                ]
            },
        )
        values = {name: json.dumps(table) for name, table in tables.items()}
        values["__checksum__"] = "base"
        (self.references / "static_data_get.bin").write_bytes(
            compress(
                "".join(f"{k}\n{v}\n3\n{digest(v.encode())}\n" for k, v in values.items()).encode()
            )
        )
        p = self.store.account.profile()
        user = p["User"]
        user["ItemWeapons"] = [
            dict(inventory_item(50 + rank * 3 + slot, 100 + rank), Experience=40 + slot)
            for rank in range(6)
            for slot in range(3)
        ]
        user["ItemIdCounter"] = 80
        self.save_profile(p)

    def manual(self, target, materials, seq=51):
        return self.call({"TargetWeaponId": target, "SourceWeaponIds": materials}, MANUAL, seq)

    def auto(self, groups, seq=51):
        return self.call({"ComposeRequests": groups}, AUTO, seq)

    def test_auto_evolves_all_four_ranks_in_one_request_and_replays_once(self):
        original = self.store.account.profile()["User"]
        groups = [[base, base + 1, base + 2] for base in (50, 53, 56, 59)]
        with patch("guardian_tales.mystery_evolution.RANDOM.random", return_value=0.6):
            response = self.auto(groups)
        by_id = {row["Id"]: row for row in response["User"]["ItemWeapons"]}
        for rank, (target, *materials) in enumerate(groups):
            self.assertEqual(by_id[target]["ItemId"], 101 + rank)
            self.assertEqual(by_id[target]["Experience"], 40)
            for ident in materials:
                self.assertEqual(
                    by_id[ident], next(i for i in original["ItemWeapons"] if i["Id"] == ident)
                )
        self.assertEqual(original["Assets"], response["User"]["Assets"])
        self.assertEqual(
            by_id[59]["Options"], [dict(OptionId=7, Level=3, Locked=False, OptionSource=0)]
        )
        self.assertEqual(response["UserRecord"]["ComposeWeaponCount"], dict.fromkeys("1234", 1))
        before = self.db.total_changes
        self.assertEqual(self.auto(list(reversed(groups))), response)
        self.assertEqual(self.db.total_changes, before)
        with self.assertRaises(PacketError):
            self.manual(50, [51, 52])

    def test_manual_four_star_can_roll_exclusive(self):
        with patch("guardian_tales.mystery_evolution.RANDOM.random", return_value=0.01):
            response = self.manual(59, [60])
        self.assertTrue(response["Succeeded"])
        target = next(i for i in response["User"]["ItemWeapons"] if i["Id"] == 59)
        self.assertEqual(target["ItemId"], 203)
        self.open_session(reconnect=True)
        self.assertEqual(self.manual(59, [60]), response)

    def test_failed_roll_is_replayed_even_after_another_request(self):
        original = self.store.account.profile()["User"]
        with patch("guardian_tales.mystery_evolution.RANDOM.random", return_value=0.99):
            failed = self.manual(59, [60])
            self.assertFalse(failed["Succeeded"])
            self.assertEqual(failed["User"]["ItemWeapons"], original["ItemWeapons"])
            self.assertEqual(failed["User"]["Assets"], original["Assets"])
            later = self.manual(50, [51, 52], 52)
        with patch("guardian_tales.mystery_evolution.RANDOM.random", side_effect=AssertionError):
            replay = self.manual(59, [60])
        self.assertFalse(replay["Succeeded"])
        self.assertEqual(replay["User"], later["User"])

    def test_invalid_batch_does_not_partly_evolve_inventory(self):
        p = self.store.account.profile()
        next(i for i in p["User"]["ItemWeapons"] if i["Id"] == 61)["Locked"] = True
        self.save_profile(p)
        for groups in (
            [],
            [[59]],
            [[62, 63]],
            [[65, 66]],
            [[59, 61]],
            [[59, 56]],
            [[59, 59]],
            [[50, 51, 52], [53, 51]],
            [[50, 51, 52], [59, 999]],
            [[True, 50]],
        ):
            with self.subTest(groups=groups), self.assertRaises(PacketError):
                self.auto(groups)
            self.assertEqual(self.store.account.profile(), p)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM mystery_evolution_requests").fetchone()[0], 0
        )

    def test_client_loads_zero_prices_with_original_rates(self):
        source = (self.references / "static_data_get.bin").read_bytes()
        before = json.loads(records(decode(source))[1]["weaponenhance"][1])
        body = self.session.handle(request("/static-data/get", {})).body
        after = json.loads(records(decode(body))[1]["weaponenhance"][1])
        self.assertEqual(
            after["WeaponCompose"], [dict(row, GoldCost=0) for row in before["WeaponCompose"]]
        )
        self.assertEqual((self.references / "static_data_get.bin").read_bytes(), source)
