# SPDX-License-Identifier: Apache-2.0
"""Weapon candidates refresh caches and wishlist changes preserve all other progress."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.settlement.village import MAX_REVISION
from guardian_tales.summons.weapon_selection import ROUTE
from tests import FIXTURES
from tests.account.test_snapshots import synthetic_snapshot


class WeaponSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.static = {
            "items": [
                {
                    "Id": spec,
                    "Type": "weapon",
                    "Rarity": rank,
                    "OriginRarity": rank,
                    "Summonable": True,
                    "Limited": False,
                }
                for spec, rank in (
                    (101, 0),
                    (201, 2),
                    (501, 4),
                    (502, 4),
                    (503, 4),
                    (504, 4),
                    (505, 4),
                    (506, 4),
                )
            ],
            "constants": {"SummonWeaponBaseLevel": 19},
            "weaponenhance": {
                "Constants": {"MagicMetalPerSummonWeapon": 10},
                "LevelExps": [{"Level": i, "TotalExps": (i + 1) * 100} for i in range(20)],
            },
        }
        self.write_static()
        for name in ("summon_selection_catalog.json", "summon_draw_catalog.json"):
            (self.root / name).write_bytes((FIXTURES / name).read_bytes())
        self.store = GuestStore(self.db, self.root)
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["ItemStackables"].append(
            {"Id": 10, "ItemId": 110015, "Amount": 20}
        )
        snapshot["profile"]["User"]["ItemIdCounter"] = 10
        self.source = self.root / "synthetic-import.json"
        self.source.write_text(json.dumps(snapshot), encoding="utf-8")
        with self.db:
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        self.save(snapshot["profile"])
        self.open_session()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def write_static(self):
        lines = []
        for name, value in self.static.items():
            content = json.dumps(value, separators=(",", ":"))
            lines.extend((name, content, "1", digest(content.encode())))
        (self.root / "static_data_get.bin").write_bytes(
            compress(("\n".join(lines) + "\n").encode())
        )

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def open_session(self):
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": True},
            route="/auth/sign-in",
            sequence=1,
        )

    def call(self, body=None, route=ROUTE, sequence=1001, session=None):
        packet = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        return read_json_body(parse_packet(encode_packet((session or self.session).handle(packet))))

    def reject(self, body):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_catalog_contains_native_weapon_rows_and_preserves_hero_rows_without_writes(self):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.db.execute("PRAGMA query_only=ON")
        entry = self.call(route="/summon/enter")
        catalog = self.call(route="/summon/on-event")
        self.assertEqual(entry["Checksum"], catalog["Checksum"])
        self.assertEqual(
            catalog["SelectableCharacter"],
            json.loads((self.root / "summon_selection_catalog.json").read_text())["characters"],
        )
        self.assertEqual(
            catalog["SelectableWeapon"],
            [
                {
                    "Id": i,
                    "ItemId": i,
                    "SummonCategory": "Exclusive",
                    "SummonEventType": "Weapon",
                    "IsNew": False,
                }
                for i in range(501, 507)
            ],
        )
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_weapon_categories_and_media_collections_match_native_model_types(self):
        catalog = self.call(route="/summon/on-event")
        native_item_categories = {"None", "Normal", "Exclusive"}
        self.assertTrue(
            all(
                row["SummonCategory"] in native_item_categories
                for row in catalog["SelectableWeapon"]
            )
        )
        self.assertTrue(
            all(row["SummonCategory"] == "Exclusive" for row in catalog["SelectableWeapon"])
        )
        for key in (
            "StartDashSeason",
            "StartDashCharacter",
            "StartDashRewards",
            "PaidGemStepUpEventSeason",
            "PaidGemStepUpEventCharacter",
            "PaidGemStepUpEventReward",
        ):
            self.assertIsInstance(catalog[key], list)

    def test_combined_checksum_refreshes_when_weapons_or_heroes_change(self):
        first = self.call(route="/summon/enter")["Checksum"]
        self.static["items"].append(
            {
                "Id": 507,
                "Type": "weapon",
                "Rarity": 4,
                "OriginRarity": 4,
                "Summonable": True,
                "Limited": False,
            }
        )
        self.write_static()
        second = self.call(route="/summon/enter")["Checksum"]
        self.assertNotEqual(first, second)
        path = self.root / "summon_selection_catalog.json"
        heroes = json.loads(path.read_text())
        heroes["characters"][0]["IsNew"] = True
        path.write_text(json.dumps(heroes), encoding="utf-8")
        third = self.call(route="/summon/on-event")["Checksum"]
        self.assertNotEqual(second, third)
        self.assertEqual(third, self.call(route="/summon/enter")["Checksum"])

    def test_ordered_replacement_partial_lists_and_clear_change_only_wishlist_and_shop_revision(
        self,
    ):
        source = self.source.read_bytes()
        imported = self.db.execute("SELECT * FROM imported_account").fetchall()
        for selected in ([501, 502, 503, 504, 505], [505, 504, 503, 502, 501], [506], []):
            expected = copy.deepcopy(self.store.account.profile())
            expected["UserShop"]["SelectedSummonWeapons"] = selected
            expected["UserShop"]["Cas"] += 1
            self.assertEqual(
                self.call({"RequestItemIds": selected}), {"UserShop": expected["UserShop"]}
            )
            self.assertEqual(self.store.account.profile(), expected)
            self.assertEqual(self.source.read_bytes(), source)
            self.assertEqual(self.db.execute("SELECT * FROM imported_account").fetchall(), imported)

    def test_identical_selection_is_a_noop_with_writes_disabled_and_maximum_revision(self):
        self.call({"RequestItemIds": [501]})
        profile = self.store.account.profile()
        profile["UserShop"]["Cas"] = MAX_REVISION
        self.save(profile)
        self.db.execute("PRAGMA query_only=ON")
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"RequestItemIds": [501]}), {"UserShop": profile["UserShop"]})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.reject({"RequestItemIds": [502]})

    def test_invalid_unknown_inventory_hero_and_non_epic_ids_are_rejected(self):
        for body in (
            None,
            [],
            {},
            True,
            {"RequestItemIds": None},
            {"RequestItemIds": [True]},
            {"RequestItemIds": [-1]},
            {"RequestItemIds": [0]},
            {"RequestItemIds": [501.0]},
            {"RequestItemIds": [501, 501]},
            {"RequestItemIds": [501, 502, 503, 504, 505, 506]},
            {"RequestItemIds": [1]},
            {"RequestItemIds": [101]},
            {"RequestItemIds": [201]},
            {"RequestItemIds": [999]},
            {"RequestItemIds": [501], "Extra": 1},
        ):
            with self.subTest(body=body):
                self.reject(body)

    def test_invalid_saved_shop_state_is_not_silently_repaired(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["UserShop"].update(UserId=True),
            lambda p: p["UserShop"].update(Cas=-1),
            lambda p: p["UserShop"].update(SelectedSummonWeapons=None),
            lambda p: p["UserShop"].update(SelectedSummonWeapons=[501, 501]),
            lambda p: p["UserShop"].update(SelectedSummonWeapons=[True]),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject({"RequestItemIds": [501]})

    def test_saved_outdated_design_can_be_replaced_without_granting_or_spending(self):
        profile = self.store.account.profile()
        profile["UserShop"]["SelectedSummonWeapons"] = [999]
        self.save(profile)
        self.assertEqual(
            self.call({"RequestItemIds": [501]})["UserShop"]["SelectedSummonWeapons"], [501]
        )

    def test_missing_corrupt_or_ineligible_catalog_cannot_save_a_choice(self):
        path = self.root / "static_data_get.bin"
        original = path.read_bytes()
        path.unlink()
        self.reject({"RequestItemIds": [501]})
        path.write_bytes(b"invalid")
        self.reject({"RequestItemIds": [501]})
        path.write_bytes(original)
        self.static["items"][2]["Limited"] = True
        self.write_static()
        self.reject({"RequestItemIds": [501]})

    def test_selection_survives_reopening_and_existing_import_needs_no_migration(self):
        self.call({"RequestItemIds": [506, 505, 504, 503, 502]})
        profile = self.store.account.profile()
        tables = self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session()
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(
            self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), tables
        )
        self.assertEqual(self.call(route="/auth/fetch-account"), profile)

    def test_failed_write_rolls_back_selection_and_keeps_all_currencies(self):
        self.db.execute(
            "CREATE TRIGGER reject_wishlist BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT,'test'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call({"RequestItemIds": [501]})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_wishlist_drives_subsequent_draws_and_selection_itself_spends_nothing(self):
        self.call({"RequestItemIds": [501, 502, 503, 504, 506]})
        before = self.store.account.profile()
        with patch(
            "guardian_tales.summons.weapon_summon.secrets.randbelow", side_effect=lambda n: n - 1
        ):
            reply = self.call(
                {"Count": 1, "SummonCostType": 5}, route="/summon/select-weapon", sequence=1002
            )
        self.assertEqual(reply["Summons"][0]["SpecId"], 506)
        self.assertEqual(
            reply["User"]["ItemStackables"][0]["Amount"],
            before["User"]["ItemStackables"][0]["Amount"] - 1,
        )
        self.assertEqual(reply["UserShop"]["SelectedSummonWeapons"], [501, 502, 503, 504, 506])

    def test_authentication_and_completed_prologue_are_required_for_saving(self):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call({"RequestItemIds": [501]}, session=BootstrapSession(self.store))
        self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            store = GuestStore(db, self.root)
            with self.assertRaises(ValueError):
                store.account.read(ROUTE, {"RequestItemIds": [501]})

    def test_weapon_only_catalog_is_available_without_the_optional_hero_selection_file(self):
        (self.root / "summon_selection_catalog.json").unlink()
        catalog = self.call(route="/summon/on-event")
        self.assertEqual(catalog["SelectableCharacter"], [])
        self.assertEqual(len(catalog["SelectableWeapon"]), 6)
        self.assertEqual(catalog["Checksum"], self.call(route="/summon/enter")["Checksum"])
