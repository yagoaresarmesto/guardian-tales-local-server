# SPDX-License-Identifier: Apache-2.0
"""Hero gear changes preserve inventory, development and newer retry choices."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.characters import new_character
from guardian_tales.hero_equipment import ROUTES
from guardian_tales.items import inventory_item
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, digest
from guardian_tales.village import MAX_REVISION
from tests.test_snapshots import request as packet
from tests.test_village_harvest import NOW, VillageFixture

WEAPONS = "/user/change-weapons"
ACCESSORY = "/user/change-accessory"
COSTUME = "/user/change-costume"
CARDS = "/user/change-orb"
MERCH = "/user/change-merch"
RELIC = "/user/change-relic"


class HeroEquipmentTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tables = {
            "heroes": [
                {
                    "Id": 1001,
                    "OriginId": 7,
                    "CompatibleWeapons": {"default": ["onehandsword", "shield", "accessory"]},
                },
                {"Id": 1002, "CompatibleWeapons": {"default": ["staff", "accessory"]}},
            ],
            "items": [
                {"Id": ident, "Type": "weapon", "WeaponType": kind}
                for ident, kind in (
                    (101, "onehandsword"),
                    (102, "shield"),
                    (110, "staff"),
                    (111, "onehandsword"),
                    (112, "accessory"),
                )
            ]
            + [
                {"Id": ident, "Type": kind}
                for ident, kind in (
                    (201, "orb"),
                    (202, "orb"),
                    (301, "merch"),
                    (401, "relic"),
                    (901, "material"),
                )
            ],
            "__checksum__": "synthetic-equipment",
        }
        self.tables["items"].extend(
            [
                {"Id": 501, "Type": "costume", "TargetCharacterIds": [7]},
                {"Id": 502, "Type": "supercostume", "TargetCharacterIds": [7, 1002]},
                {"Id": 503, "Type": "equipcostume", "TargetWeaponType": "staff"},
            ]
        )
        self.write_static()
        profile = self.store.account.profile()
        user = profile["User"]
        user["Characters"] = [
            new_character(1, 1001, 1, 2),
            new_character(2, 1001, 11),
            new_character(3, 1002),
        ]
        user["Characters"][0].update(Accessory1=12, Orb1=20, Experience=235, BlessLevel=3)
        user["Characters"][1].update(Orb1=21, Merch=30, Relic=40)
        user["ItemWeapons"] = [
            inventory_item(ident, spec)
            for ident, spec in ((1, 101), (2, 102), (10, 110), (11, 111), (12, 112))
        ]
        user["ItemWeapons"][3].update(Locked=True, Experience=987, EngraveCeiling=4)
        user["ItemMiscs"] = [
            inventory_item(ident, spec)
            for ident, spec in (
                (20, 201),
                (21, 202),
                (30, 301),
                (40, 401),
                (50, 501),
                (51, 502),
                (52, 503),
            )
        ]
        user["ItemStackables"] = [inventory_item(90, 901)]
        user["CharacterIdCounter"], user["ItemIdCounter"] = 3, 90
        self.save_profile(profile)
        self.request = {"CharacterId": 1, "Weapon1": 11, "Weapon2": None}

    def write_static(self):
        text = ""
        for name, value in self.tables.items():
            content = value if isinstance(value, str) else json.dumps(value)
            text += f"{name}\n{content}\n1\n{digest(content.encode())}\n"
        (self.references / "static_data_get.bin").write_bytes(compress(text.encode()))

    def call(self, body=None, route=WEAPONS, sequence=819, now=NOW):
        return super().call(body, route, sequence, now)

    def expected_response(self, profile):
        return {"User": {k: profile["User"][k] for k in ("Id", "Cas", "Characters")}}

    def reject_without_writes(self, body, route=WEAPONS):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, route)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_weapon_transfer_updates_both_holders_without_inventory_or_development_changes(self):
        expected = self.store.account.profile()
        expected["User"]["Characters"][0].update(Weapon1=11, Weapon2=None)
        expected["User"]["Characters"][1]["Weapon1"] = None
        expected["User"]["Cas"] += 1
        reads = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()
        static = (self.references / "static_data_get.bin").read_bytes()
        result = self.call(self.request)
        self.assertEqual(result, self.expected_response(expected))
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone(), reads
        )
        self.assertEqual((self.references / "static_data_get.bin").read_bytes(), static)
        self.open_session(reconnect=True)
        self.assertEqual(self.store.account.profile(), expected)

    def test_accessory_merch_and_relic_transfers_clear_only_the_previous_matching_slot(self):
        for sequence, (route, field, ident, target) in enumerate(
            (
                (ACCESSORY, "Accessory1", 12, 2),
                (MERCH, "Merch", 30, 1),
                (RELIC, "Relic", 40, 1),
            ),
            850,
        ):
            expected = self.store.account.profile()
            for hero in expected["User"]["Characters"]:
                if hero.get(field) == ident:
                    hero[field] = None
                if hero["Id"] == target:
                    hero[field] = ident
            expected["User"]["Cas"] += 1
            with self.subTest(route=route):
                self.assertEqual(
                    self.call({"CharacterId": target, field: ident}, route, sequence),
                    self.expected_response(expected),
                )
                self.assertEqual(self.store.account.profile(), expected)

    def test_both_card_slots_move_between_heroes_or_within_one_hero_without_duplicates(self):
        self.call({"CharacterId": 1, "Orb": 21, "Slot": 2}, CARDS)
        heroes = self.store.account.profile()["User"]["Characters"]
        self.assertEqual((heroes[0]["Orb1"], heroes[0]["Orb2"], heroes[1]["Orb1"]), (20, 21, None))
        self.call({"CharacterId": 1, "Orb": 20, "Slot": 2}, CARDS, sequence=820)
        heroes = self.store.account.profile()["User"]["Characters"]
        self.assertEqual((heroes[0]["Orb1"], heroes[0]["Orb2"]), (None, 20))
        self.call({"CharacterId": 1, "Orb": 21, "Slot": 1}, CARDS, sequence=821)
        heroes = self.store.account.profile()["User"]["Characters"]
        self.assertEqual((heroes[0]["Orb1"], heroes[0]["Orb2"]), (21, 20))

    def test_costume_uses_origin_and_can_be_swapped_transferred_and_removed(self):
        expected = self.store.account.profile()
        roster = expected["User"]["Characters"]
        for sequence, (hero, costume, worn) in enumerate(
            (
                (1, 50, [50, None, None]),
                (1, 51, [51, None, None]),
                (3, 51, [None, None, 51]),
                (3, None, [None, None, None]),
            ),
            860,
        ):
            with self.subTest(hero=hero, costume=costume):
                expected["User"]["Cas"] += 1
                for character, item in zip(roster, worn):
                    character["Costume"] = item
                response = self.call({"CharacterId": hero, "Costume": costume}, COSTUME, sequence)
                self.assertEqual(response, self.expected_response(expected))
                self.assertEqual(self.store.account.profile(), expected)
        self.open_session(reconnect=True)
        self.assertEqual(
            self.call({"CharacterId": 1, "Costume": 50}, COSTUME, 860),
            self.expected_response(expected),
        )

    def test_wrong_hero_weapon_skin_and_unowned_costume_are_rejected(self):
        for hero, costume in ((3, 50), (1, 52), (1, 501), (1, 20)):
            with self.subTest(hero=hero, costume=costume):
                self.reject_without_writes({"CharacterId": hero, "Costume": costume}, route=COSTUME)

    def test_null_and_zero_clear_slots_without_removing_owned_items(self):
        original = self.store.account.profile()
        for sequence, (route, fields) in enumerate(ROUTES.items(), 830):
            body = {"CharacterId": 1, **{field: None for field in fields}}
            if route == CARDS:
                body.update(Orb=0, Slot=1)
            self.call(body, route, sequence)
        profile = self.store.account.profile()
        for field in ("Weapon1", "Weapon2", "Accessory1", "Orb1", "Merch", "Relic"):
            self.assertIsNone(profile["User"]["Characters"][0][field])
        for key in ("ItemWeapons", "ItemMiscs", "ItemStackables", "Assets"):
            self.assertEqual(profile["User"][key], original["User"][key])

    def test_noop_at_revision_ceiling_records_receipt_once_without_rewriting_profile(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save_profile(profile)
        body = {"CharacterId": 1, "Weapon1": 1, "Weapon2": 2}
        before = self.db.total_changes
        self.assertEqual(self.call(body), self.expected_response(profile))
        self.assertEqual(self.db.total_changes, before + 1)
        before = self.db.total_changes
        self.call(dict(reversed(list(body.items()))))
        self.assertEqual(self.db.total_changes, before)

    def test_delayed_retry_after_reopen_keeps_later_gear_and_progression(self):
        self.call(self.request)
        self.call({"CharacterId": 1, "Weapon1": 1, "Weapon2": 2}, sequence=820)
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["Experience"] += 47
        self.save_profile(profile)
        self.open_session(reconnect=True)
        before = list(self.db.iterdump())
        self.assertEqual(self.call(self.request), self.expected_response(profile))
        self.assertEqual(list(self.db.iterdump()), before)

    def test_request_identity_cannot_be_reused_with_different_gear_or_route(self):
        self.call(self.request)
        for body, route in (
            (dict(self.request, Weapon1=1), WEAPONS),
            ({"CharacterId": 1, "Accessory1": 12}, ACCESSORY),
        ):
            with self.subTest(route=route):
                self.reject_without_writes(body, route=route)

    def test_malformed_slot_hero_and_inventory_ids_are_rejected_before_any_write(self):
        for body in (
            None,
            {},
            dict(self.request, Extra=True),
            dict(self.request, CharacterId=True),
            dict(self.request, CharacterId=1001),
            dict(self.request, Weapon1=True),
            dict(self.request, Weapon1="11"),
            dict(self.request, Weapon1=11.0),
            dict(self.request, Weapon1=-1),
            dict(self.request, Weapon1=1 << 31),
            dict(self.request, Weapon1=999),
            dict(self.request, Weapon1=111),
            dict(self.request, Weapon2=11),
        ):
            with self.subTest(body=body):
                self.reject_without_writes(body)
        for slot in (True, 0, 3, None, "1", 1.0):
            self.reject_without_writes({"CharacterId": 1, "Orb": 20, "Slot": slot}, route=CARDS)
        for identity in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.change_hero_equipment(self.request, identity, WEAPONS)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_slot_types_and_hero_weapon_compatibility_are_enforced_atomically(self):
        for body, route in (
            (dict(self.request, Weapon1=10), WEAPONS),
            (dict(self.request, Weapon1=2), WEAPONS),
            (dict(self.request, Weapon2=1), WEAPONS),
            ({"CharacterId": 1, "Accessory1": 11}, ACCESSORY),
            ({"CharacterId": 1, "Orb": 30, "Slot": 1}, CARDS),
            ({"CharacterId": 1, "Merch": 40}, MERCH),
            ({"CharacterId": 1, "Relic": 20}, RELIC),
            ({"CharacterId": 1, "Relic": 90}, RELIC),
        ):
            with self.subTest(route=route, body=body):
                self.reject_without_writes(body, route=route)

    def test_invalid_saved_roster_inventory_and_revision_cannot_partially_detach_equipment(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Cas=True),
            lambda p: p["User"].update(Cas=MAX_REVISION),
            lambda p: p["User"]["Characters"].append(copy.deepcopy(p["User"]["Characters"][0])),
            lambda p: p["User"]["Characters"][0].update(Orb2=True),
            lambda p: p["User"]["ItemMiscs"].append(copy.deepcopy(p["User"]["ItemWeapons"][0])),
            lambda p: p["User"]["ItemWeapons"][3].update(Amount=0),
            lambda p: p["User"]["ItemWeapons"][3].update(ItemId=True),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save_profile(profile)
            self.reject_without_writes(self.request)

    def test_missing_ambiguous_or_wrong_catalog_rejects_before_save(self):
        original = copy.deepcopy(self.tables)
        for mutate in (
            lambda t: t.pop("heroes"),
            lambda t: t["heroes"].append(t["heroes"][0]),
            lambda t: t["items"].append(t["items"][0]),
            lambda t: t["items"].clear(),
            lambda t: t["heroes"][0].update(CompatibleWeapons=None),
        ):
            self.tables = copy.deepcopy(original)
            mutate(self.tables)
            self.write_static()
            self.reject_without_writes(self.request)

    def test_registered_test_pin_can_be_equipped_without_altering_its_custom_stats(self):
        profile = self.store.account.profile()
        profile["User"]["ItemWeapons"].append(inventory_item(13, 9990003))
        self.save_profile(profile)
        spec = {
            "Id": 9990003,
            "Name": "local_test_pin_synthetic",
            "Type": "weapon",
            "WeaponType": "accessory",
            "Defense": 10000,
        }
        self.db.execute(
            "CREATE TABLE admin_test_item_grants (spec_id INTEGER PRIMARY KEY,spec TEXT)"
        )
        self.db.execute(
            "INSERT INTO admin_test_item_grants VALUES(?,?)", (spec["Id"], json.dumps(spec))
        )
        self.db.commit()
        before = self.db.execute("SELECT * FROM admin_test_item_grants").fetchall()
        self.call({"CharacterId": 1, "Accessory1": 13}, ACCESSORY)
        self.assertEqual(self.store.account.profile()["User"]["Characters"][0]["Accessory1"], 13)
        self.assertEqual(self.db.execute("SELECT * FROM admin_test_item_grants").fetchall(), before)

    def test_profile_or_receipt_failure_rolls_back_detachments_revision_and_identity(self):
        for table, action in (("local_account", "UPDATE"), ("hero_equipment_requests", "INSERT")):
            self.db.execute(
                f"CREATE TRIGGER reject_gear BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):
                self.call(self.request)
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_gear")
            self.db.commit()

    def test_unsigned_requests_cannot_change_equipment(self):
        self.session.signed_in = False
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.session.handle(packet(WEAPONS, self.request))
        self.assertEqual(list(self.db.iterdump()), before)
