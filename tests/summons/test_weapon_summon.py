# SPDX-License-Identifier: Apache-2.0
"""Weapon draws preserve existing gear and freeze atomic payment/reward receipts."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.items import inventory_item
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.raid_static import compress, digest
from guardian_tales.village import INT_MAX, MAX_REVISION
from guardian_tales.weapon_summon import ROUTE, weapon_catalog
from tests import FIXTURES
from tests.account.test_snapshots import synthetic_snapshot

RANDOM = "guardian_tales.weapon_summon.secrets.randbelow"


class WeaponSummonTests(unittest.TestCase):
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
                    (102, 1),
                    (201, 2),
                    (202, 3),
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
                "LevelExps": [{"Level": i, "TotalExps": (i + 1) * 100} for i in range(25)],
            },
        }
        self.write_static()
        self.policy = self.root / "summon_draw_catalog.json"
        self.policy.write_bytes((FIXTURES / "summon_draw_catalog.json").read_bytes())
        self.store = GuestStore(self.db, self.root)
        snapshot = synthetic_snapshot()
        user = snapshot["profile"]["User"]
        assets = {a["Id"]: a for a in user["Assets"]}
        assets[70003].update(Amount=10000, Spent=0)
        user["ItemStackables"] = [
            {"Id": i, "ItemId": spec, "Amount": count}
            for i, spec, count in (
                (10, 110007, 4),
                (11, 110007, 6),
                (12, 110015, 20),
                (13, 110007, 0),
                (14, 8888, 99),
            )
        ]
        user["ItemMiscs"].append(inventory_item(50, 220001))
        user["ItemIdCounter"] = 50
        user["ItemWeapons"][0].update(Locked=True, SyntheticEngraving=[1, 2, 3])
        snapshot["profile"]["UserShop"]["SelectedSummonWeapons"] = [501, 502, 503, 504, 505]
        snapshot["profile"]["UserRecord"]["SummonWeaponCount"] = 12121
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

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            route="/auth/sign-in",
            sequence=1,
        )

    def call(self, body, sequence=941, route=ROUTE, session=None):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        response = (session or self.session).handle(request)
        self.assertEqual(response.sequence_id, sequence)
        return read_json_body(parse_packet(encode_packet(response)))

    def reject(self, body=None):
        body = {"Count": 10, "SummonCostType": 0} if body is None else body
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with patch(RANDOM, side_effect=AssertionError("Rejected draw reached RNG")):
            with self.assertRaises(PacketError):
                self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_ten_gem_draws_preserve_all_old_gear_and_commit_only_expected_fields(self):
        expected = copy.deepcopy(self.store.account.profile())
        original_source = self.source.read_bytes()
        before_reads = self.db.execute("SELECT * FROM imported_account").fetchall()
        with patch(RANDOM, return_value=0):
            response = self.call({"Count": 10, "SummonCostType": 0})
        user, record = expected["User"], expected["UserRecord"]
        assets = {a["Id"]: a for a in user["Assets"]}
        assets[70003]["Amount"] -= 2700
        assets[70003]["Spent"] += 2700
        assets[70008]["Amount"] += 100
        assets[70014]["Amount"] += 10
        user["ItemIdCounter"] += 10
        user["Cas"] += 1
        for item_id in range(51, 61):
            item = inventory_item(item_id, 101)
            item["Experience"] = 1900
            user["ItemWeapons"].append(item)
        record["SummonWeaponCount"] += 10
        record["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            response,
            {
                "User": user,
                "UserShop": expected["UserShop"],
                "UserRecord": record,
                "Summons": [
                    {
                        "Type": 0,
                        "ItemId": i,
                        "SpecId": 101,
                        "State": 1,
                        "StateValue": 0,
                        "Level": 19,
                        "Rank": 0,
                    }
                    for i in range(51, 61)
                ],
            },
        )
        self.assertEqual(self.source.read_bytes(), original_source)
        self.assertEqual(self.db.execute("SELECT * FROM imported_account").fetchall(), before_reads)

    def test_ordinary_tickets_drain_stacks_in_id_order_and_keep_untouched_empty_stacks(self):
        before = self.store.account.profile()
        with patch(RANDOM, return_value=0):
            self.call({"Count": 10, "SummonCostType": 3})
        user = self.store.account.profile()["User"]
        self.assertEqual(user["ItemStackables"], before["User"]["ItemStackables"][2:])
        self.assertEqual(
            next(a for a in user["Assets"] if a["Id"] == 70003),
            next(a for a in before["User"]["Assets"] if a["Id"] == 70003),
        )

    def test_selectable_tickets_one_draw_and_repeated_designs_deliver_distinct_weapons(self):
        with patch(RANDOM, side_effect=lambda bound: bound - 1):
            one = self.call({"Count": 1, "SummonCostType": 5})
            ten = self.call({"Count": 10, "SummonCostType": 5}, sequence=942)
        results = one["Summons"] + ten["Summons"]
        self.assertEqual({r["SpecId"] for r in results}, {505})
        self.assertEqual(len({r["ItemId"] for r in results}), 11)
        self.assertTrue(all(r["Type"] == 0 and r["StateValue"] == 0 for r in results))
        user = self.store.account.profile()["User"]
        self.assertEqual(next(i for i in user["ItemStackables"] if i["Id"] == 12)["Amount"], 9)
        self.assertEqual(next(a for a in user["Assets"] if a["Id"] == 70009)["Amount"], 0)

    def test_story_pool_and_single_gem_cost_follow_configured_local_categories(self):
        with patch(RANDOM, side_effect=[75, 0]):
            response = self.call({"Count": 1, "SummonCostType": 0})
        self.assertEqual(response["Summons"][0]["SpecId"], 201)
        self.assertEqual(
            next(a for a in response["User"]["Assets"] if a["Id"] == 70003)["Amount"], 9700
        )

    def test_saved_results_survive_reopening_without_payment_reroll_or_stale_profile_restore(self):
        with patch(RANDOM, return_value=0):
            original = self.call({"Count": 10, "SummonCostType": 0})
        profile = self.store.account.profile()
        profile["User"]["ItemWeapons"][-1]["Experience"] += 77
        profile["User"]["ItemWeapons"].pop(-2)
        profile["User"]["Characters"][0]["Experience"] += 19
        profile["UserShop"]["SelectedSummonWeapons"] = []
        self.save(profile)
        self.policy.unlink()
        (self.root / "static_data_get.bin").unlink()
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session(reconnect=True)
        self.db.execute("PRAGMA query_only=ON")
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with patch(RANDOM, side_effect=AssertionError("Retry rerolled")):
            repeated = self.call({"SummonCostType": 0, "Count": 10})
        self.assertEqual(repeated["Summons"], original["Summons"])
        self.assertEqual(repeated["User"], profile["User"])
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_conflicting_receipt_rejects_and_fresh_login_permits_a_new_paid_draw(self):
        with patch(RANDOM, return_value=0):
            self.call({"Count": 1, "SummonCostType": 0})
            self.reject({"Count": 10, "SummonCostType": 0})
            self.open_session(reconnect=False)
            self.call({"Count": 10, "SummonCostType": 0})
        self.assertEqual(self.store.account.profile()["UserRecord"]["SummonWeaponCount"], 12132)

    def test_insufficient_gems_or_wrong_ticket_kind_rejects_before_any_roll_or_payment(self):
        profile = self.store.account.profile()
        next(a for a in profile["User"]["Assets"] if a["Id"] == 70003)["Amount"] = 2699
        self.save(profile)
        self.reject()
        profile["User"]["ItemStackables"] = [
            i for i in profile["User"]["ItemStackables"] if i["ItemId"] != 110007
        ]
        self.save(profile)
        self.reject({"Count": 10, "SummonCostType": 3})

    def test_malformed_and_unimplemented_payment_variants_reject_without_writes(self):
        for body in (
            [],
            {},
            True,
            {"Count": True, "SummonCostType": 0},
            {"Count": 10, "SummonCostType": False},
            {"Count": 10.0, "SummonCostType": 0},
            {"Count": 2, "SummonCostType": 0},
            {"Count": 10, "SummonCostType": 1},
            {"Count": 10, "SummonCostType": 2},
            {"Count": 10, "SummonCostType": 4},
            {"Count": 10, "SummonCostType": 0, "Gift": True},
        ):
            with self.subTest(body=body):
                self.reject(body)
        for identity in (None, "", True, "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.draw_summon_weapons({"Count": 1, "SummonCostType": 0}, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_or_missing_wishlist_does_not_spend_resources(self):
        original = self.store.account.profile()
        for selected in (
            None,
            [],
            [501],
            [501] * 5,
            [501, 502, 503, 504, 101],
            [501, 502, 503, 504, True],
            [501, 502, 503, 504, 999],
        ):
            profile = copy.deepcopy(original)
            profile["UserShop"]["SelectedSummonWeapons"] = selected
            self.save(profile)
            self.reject()

    def test_allocator_revision_reward_and_lifetime_counter_overflows_reject_atomically(self):
        original = self.store.account.profile()
        for section, field, value in (
            ("User", "ItemIdCounter", INT_MAX - 9),
            ("User", "Cas", MAX_REVISION),
            ("UserRecord", "Cas", MAX_REVISION),
            ("UserRecord", "SummonWeaponCount", INT_MAX - 9),
        ):
            profile = copy.deepcopy(original)
            profile[section][field] = value
            self.save(profile)
            self.reject()
        for asset, field, value in (
            (70008, "Amount", INT_MAX - 99),
            (70014, "Amount", INT_MAX - 9),
            (70003, "Spent", MAX_REVISION - 2699),
        ):
            profile = copy.deepcopy(original)
            next(a for a in profile["User"]["Assets"] if a["Id"] == asset)[field] = value
            self.save(profile)
            self.reject()

    def test_ambiguous_inventory_invalid_balances_and_wrong_resource_owners_are_not_repaired(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(ItemIdCounter=2),
            lambda p: p["User"]["ItemMiscs"].append(copy.deepcopy(p["User"]["ItemWeapons"][0])),
            lambda p: p["User"]["ItemStackables"][0].update(Amount=-1),
            lambda p: p["User"]["Assets"].append(copy.deepcopy(p["User"]["Assets"][0])),
            lambda p: next(a for a in p["User"]["Assets"] if a["Id"] == 70003).update(Amount=True),
            lambda p: p["UserRecord"].update(UserId=9401),
            lambda p: p["UserShop"].update(UserId=True),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject()

    def test_external_catalog_failures_reject_without_payment(self):
        original = copy.deepcopy(self.static)
        for mutate in (
            lambda v: v.pop("items"),
            lambda v: v.update(items=[]),
            lambda v: v["items"].append(copy.deepcopy(v["items"][0])),
            lambda v: v["constants"].update(SummonWeaponBaseLevel=True),
            lambda v: v["weaponenhance"]["LevelExps"][0].update(Level=True),
            lambda v: v["weaponenhance"]["Constants"].update(MagicMetalPerSummonWeapon=-1),
        ):
            self.static = copy.deepcopy(original)
            mutate(self.static)
            self.write_static()
            self.reject()

    def test_pools_exclude_evolved_limited_non_summonable_and_mythic_definitions(self):
        for spec, rank, origin, limited, summonable in (
            (701, 4, 0, False, True),
            (702, 4, 4, True, True),
            (703, 4, 4, False, False),
            (704, 5, 5, False, True),
        ):
            self.static["items"].append(
                {
                    "Id": spec,
                    "Type": "weapon",
                    "Rarity": rank,
                    "OriginRarity": origin,
                    "Limited": limited,
                    "Summonable": summonable,
                }
            )
        self.write_static()
        candidates = weapon_catalog((self.root / "static_data_get.bin").read_bytes())[0]
        self.assertTrue(all(spec not in candidates for spec in (701, 702, 703, 704)))
        self.assertIn(506, candidates)
        with patch(RANDOM, side_effect=lambda bound: bound - 1):
            response = self.call({"Count": 10, "SummonCostType": 0})
        self.assertEqual({r["SpecId"] for r in response["Summons"]}, {505})

    def test_profile_and_receipt_write_failures_roll_back_every_cost_and_reward(self):
        for table, action in (("local_account", "UPDATE"), ("weapon_summon_requests", "INSERT")):
            self.db.execute(
                f"CREATE TRIGGER reject_draw BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with patch(RANDOM, return_value=0), self.assertRaises(sqlite3.IntegrityError):
                self.store.account.draw_summon_weapons(
                    {"Count": 10, "SummonCostType": 0}, "rollback"
                )
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_draw")
            self.db.commit()

    def test_rng_failure_does_not_persist_a_partial_payment(self):
        before = list(self.db.iterdump())
        with patch(RANDOM, side_effect=RuntimeError("test")), self.assertRaises(RuntimeError):
            self.store.account.draw_summon_weapons(
                {"Count": 10, "SummonCostType": 0}, "random-failure"
            )
        self.assertEqual(list(self.db.iterdump()), before)

    def test_existing_import_adds_receipt_storage_without_reimport_or_profile_rewrite(self):
        profile = self.store.account.profile()
        reads = self.db.execute("SELECT * FROM imported_account").fetchall()
        self.db.execute("DROP TABLE weapon_summon_requests")
        self.db.commit()
        self.open_session(reconnect=True)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(self.db.execute("SELECT * FROM imported_account").fetchall(), reads)
        with patch(RANDOM, return_value=0):
            self.assertEqual(len(self.call({"Count": 10, "SummonCostType": 0})["Summons"]), 10)

    def test_authentication_and_completed_prologue_are_required(self):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call({"Count": 10, "SummonCostType": 0}, session=BootstrapSession(self.store))
        self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.root).account
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.draw_summon_weapons({"Count": 1, "SummonCostType": 0}, "unfinished")
            self.assertEqual(list(db.iterdump()), before)

    def test_completed_fresh_account_can_draw_from_its_saved_weapon_wishlist(self):
        with sqlite3.connect(":memory:") as db:
            store = GuestStore(db, self.root)
            store.account.complete_prologue(
                "Synthetic",
                {
                    "IsMale": True,
                    "VoiceType": 0,
                    "Weapon1ItemId": 101,
                    "Weapon2ItemId": 102,
                    "BobLindaQuestGrade": 0,
                },
            )
            profile = store.account.profile()
            profile["UserShop"]["SelectedSummonWeapons"] = [501, 502, 503, 504, 505]
            next(a for a in profile["User"]["Assets"] if a["Id"] == 70003)["Amount"] = 300
            with db:
                db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            session = BootstrapSession(store)
            self.call(
                {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": False},
                route="/auth/sign-in",
                sequence=1,
                session=session,
            )
            with patch(RANDOM, return_value=0):
                response = self.call({"Count": 1, "SummonCostType": 0}, session=session)
            self.assertEqual(len(response["Summons"]), 1)
            self.assertEqual(response["UserRecord"]["SummonWeaponCount"], 1)
