# SPDX-License-Identifier: Apache-2.0
"""Free jewel upgrades always succeed once per identity and preserve currencies."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.items import inventory_item
from guardian_tales.jewel_upgrade import LOOSE, RELIC
from guardian_tales.protocol import PacketError
from guardian_tales.snapshots import CLIENT
from guardian_tales.village import INT_MAX, MAX_REVISION
from tests.account.test_snapshots import request as packet
from tests.village.test_village_harvest import NOW, VillageFixture


class JewelUpgradeTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.upgrade_catalog = {
            "client": CLIENT,
            "free": True,
            "always_succeed": True,
            "slot_count": 2,
            "relic_ids": [701],
            "jewels": {
                "501": {"grade": 1, "group_id": 3, "evolve_to": 502, "powder_full": 20},
                "502": {"grade": 2, "group_id": 3, "evolve_to": 503, "powder_full": 40},
                "503": {"grade": 3, "group_id": 3, "evolve_to": 0, "powder_full": 0},
            },
        }
        self.upgrade_path = self.references / "jewel_upgrade_mock_catalog.json"
        self.write_upgrade()
        profile = self.store.account.profile()
        for inventory_id, spec_id, amount in ((50, 501, 4), (51, 502, 2)):
            item = inventory_item(inventory_id, spec_id)
            item["Amount"] = amount
            profile["User"]["ItemStackables"].append(item)
        relic = inventory_item(52, 701)
        relic.update(Locked=True, JewelSlots=[501, 502], RelicOptions={"Synthetic": 9})
        profile["User"]["ItemMiscs"].append(relic)
        profile["User"]["ItemIdCounter"] = 52
        for asset in profile["User"]["Assets"]:
            if asset["Id"] in (70001, 70028):
                asset.update(Amount=0, Spent=321)
        self.save_profile(profile)
        self.request = {"RelicId": 52, "SlotIndex": 0, "UseJewelPowder": 1}
        self.loose = {"JewelId": 50, "UseJewelPowder": 1}

    def write_upgrade(self):
        self.upgrade_path.write_text(json.dumps(self.upgrade_catalog))

    def call(self, body=None, route=RELIC, sequence=519, now=NOW):
        return super().call(body, route, sequence, now)

    def relic(self, profile):
        return next(r for r in profile["User"]["ItemMiscs"] if r["Id"] == 52)

    def stack(self, profile, inventory_id):
        return next(r for r in profile["User"]["ItemStackables"] if r["Id"] == inventory_id)

    def test_locked_relic_changes_only_selected_socket_and_revision_with_zero_currency(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.relic(expected)["JewelSlots"][1] = 503
        expected["User"]["Cas"] += 1
        body = dict(self.request, SlotIndex=1)
        self.assertEqual(self.call(body), {"User": expected["User"], "Succeeded": True})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT before_spec,after_spec FROM jewel_upgrade_requests").fetchall(),
            [(502, 503)],
        )

    def test_lowest_powder_always_succeeds_and_new_operations_stop_at_maximum_grade(self):
        assets = self.store.account.profile()["User"]["Assets"]
        self.assertIs(self.call(self.request)["Succeeded"], True)
        self.assertIs(self.call(self.request, sequence=520)["Succeeded"], True)
        profile = self.store.account.profile()
        self.assertEqual(self.relic(profile)["JewelSlots"], [503, 502])
        self.assertEqual(profile["User"]["Assets"], assets)
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(self.request, sequence=521)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_loose_upgrade_moves_exactly_one_unit_into_existing_stack_without_any_asset_cost(self):
        before = self.store.account.profile()
        expected = copy.deepcopy(before)
        self.stack(expected, 50)["Amount"] -= 1
        self.stack(expected, 51)["Amount"] += 1
        expected["User"]["Cas"] += 1
        self.assertEqual(
            self.call(self.loose, LOOSE), {"User": expected["User"], "Succeeded": True}
        )
        self.assertEqual(self.store.account.profile(), expected)

    def test_single_loose_jewel_allocates_one_promoted_unit_and_preserves_its_lock(self):
        profile = self.store.account.profile()
        profile["User"]["ItemStackables"].remove(self.stack(profile, 51))
        self.stack(profile, 50).update(Amount=1, Locked=True)
        self.save_profile(profile)
        expected = copy.deepcopy(profile)
        self.stack(expected, 50)["Amount"] = 0
        item = inventory_item(53, 502)
        item["Locked"] = True
        expected["User"]["ItemStackables"].append(item)
        expected["User"]["ItemIdCounter"] = 53
        expected["User"]["Cas"] += 1
        self.call(self.loose, LOOSE)
        self.assertEqual(self.store.account.profile(), expected)
        writes = self.db.total_changes
        self.call(self.loose, LOOSE)
        self.assertEqual(writes, self.db.total_changes)

    def test_zero_destination_stack_is_reused_without_allocating_or_changing_its_metadata(self):
        profile = self.store.account.profile()
        self.stack(profile, 51).update(Amount=0, Locked=True, Options={"Synthetic": 4})
        self.save_profile(profile)
        expected = copy.deepcopy(profile)
        self.stack(expected, 50)["Amount"] -= 1
        self.stack(expected, 51)["Amount"] += 1
        expected["User"]["Cas"] += 1
        self.call(self.loose, LOOSE)
        self.assertEqual(self.store.account.profile(), expected)

    def test_old_retry_preserves_later_grade_and_resources_after_reopen_and_catalog_removal(self):
        self.call(self.request)
        self.call(self.request, sequence=520)
        profile = self.store.account.profile()
        self.asset(profile, 70028)["Amount"] = 27
        self.save_profile(profile)
        self.open_session(reconnect=True)
        self.upgrade_path.unlink()
        before = list(self.db.iterdump())
        reordered = {"UseJewelPowder": 1, "SlotIndex": 0, "RelicId": 52}
        self.assertEqual(self.call(reordered), {"User": profile["User"], "Succeeded": True})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_changed_parameters_or_route_cannot_reuse_one_identity(self):
        self.call(self.request)
        before = list(self.db.iterdump())
        self.reject_without_writes(dict(self.request, UseJewelPowder=2))
        with self.assertRaises(PacketError):
            self.call(self.loose, LOOSE)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_malformed_fields_quantities_slots_and_identities_are_atomic(self):
        for body in (
            None,
            {},
            dict(self.request, Extra=1),
            dict(self.request, UseJewelPowder=0),
            dict(self.request, UseJewelPowder=-1),
            dict(self.request, UseJewelPowder=True),
            dict(self.request, UseJewelPowder=1.0),
            dict(self.request, UseJewelPowder=21),
            dict(self.request, SlotIndex=True),
            dict(self.request, SlotIndex=-1),
            dict(self.request, SlotIndex=2),
            dict(self.request, RelicId=True),
            dict(self.request, RelicId="52"),
            dict(self.request, RelicId=701),
        ):
            with self.subTest(body=str(body)[:60]):
                self.reject_without_writes(body)
        for identity in (None, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.upgrade_jewel(self.request, identity, RELIC)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_targets_empty_unknown_maximum_sockets_and_ambiguous_inventory_reject(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: self.relic(p).update(ItemId=999),
            lambda p: self.relic(p).update(Amount=2),
            lambda p: self.relic(p).update(JewelSlots=None),
            lambda p: self.relic(p).update(JewelSlots=[]),
            lambda p: self.relic(p).update(JewelSlots=[0]),
            lambda p: self.relic(p).update(JewelSlots=[True]),
            lambda p: self.relic(p).update(JewelSlots=[999]),
            lambda p: self.relic(p).update(JewelSlots=[503]),
            lambda p: p["User"]["ItemWeapons"].append(copy.deepcopy(self.relic(p))),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save_profile(profile)
            self.reject_without_writes(self.request)
        self.save_profile(original)
        for mutate in (
            lambda p: self.stack(p, 50).update(Amount=0),
            lambda p: self.stack(p, 50).update(ItemId=999),
            lambda p: self.stack(p, 50).update(Locked=None),
            lambda p: p["User"]["ItemStackables"].append(dict(self.stack(p, 51), Id=55)),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save_profile(profile)
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.call(self.loose, LOOSE)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_missing_or_invalid_policy_and_broken_upgrade_graph_cannot_change_state(self):
        original = copy.deepcopy(self.upgrade_catalog)
        self.upgrade_path.unlink()
        self.reject_without_writes(self.request)
        for mutate in (
            lambda c: c.update(client={}),
            lambda c: c.update(free=False),
            lambda c: c.update(always_succeed=False),
            lambda c: c.update(slot_count=0),
            lambda c: c.update(relic_ids=[701, 701]),
            lambda c: c["jewels"]["501"].update(grade=True),
            lambda c: c["jewels"]["501"].update(evolve_to=999),
            lambda c: c["jewels"]["501"].update(evolve_to=501),
            lambda c: c["jewels"]["502"].update(group_id=4),
            lambda c: c["jewels"]["501"].update(powder_full=0),
            lambda c: c["jewels"]["503"].update(powder_full=1),
        ):
            self.upgrade_catalog = copy.deepcopy(original)
            mutate(self.upgrade_catalog)
            self.write_upgrade()
            self.reject_without_writes(self.request)

    def test_revision_stack_and_new_inventory_id_overflow_are_guarded(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Cas=MAX_REVISION),
            lambda p: p["User"].update(Cas=True),
            lambda p: self.stack(p, 51).update(Amount=INT_MAX),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save_profile(profile)
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.call(self.loose, LOOSE)
            self.assertEqual(list(self.db.iterdump()), before)
        for counter in (INT_MAX, 1):
            profile = copy.deepcopy(original)
            profile["User"]["ItemStackables"].remove(self.stack(profile, 51))
            profile["User"]["ItemIdCounter"] = counter
            self.save_profile(profile)
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.call(self.loose, LOOSE)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_late_write_failures_roll_back_sockets_stacks_ids_revisions_and_receipts(self):
        profile = self.store.account.profile()
        profile["User"]["ItemStackables"].remove(self.stack(profile, 51))
        self.save_profile(profile)
        for table, action in (("local_account", "UPDATE"), ("jewel_upgrade_requests", "INSERT")):
            self.db.execute(
                f"CREATE TRIGGER reject_upgrade BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            for body, route in ((self.loose, LOOSE), (self.request, RELIC)):
                with (
                    self.subTest(table=table, route=route),
                    self.assertRaises(sqlite3.IntegrityError),
                ):
                    self.store.account.upgrade_jewel(body, "rollback", route)
                self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_upgrade")
            self.db.commit()

    def test_authenticated_packet_reconnect_and_unfinished_fresh_account(self):
        with self.assertRaises(PacketError):
            BootstrapSession(self.store).handle(packet(RELIC, self.request))
        self.call(self.request)
        self.open_session(reconnect=True)
        writes = self.db.total_changes
        profile = self.store.account.profile()
        self.assertEqual(self.call(self.request), {"User": profile["User"], "Succeeded": True})
        self.assertEqual(writes, self.db.total_changes)
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.references).account
            before = account.profile()
            with self.assertRaises(ValueError):
                account.upgrade_jewel(self.loose, "unfinished", LOOSE)
            self.assertEqual(account.profile(), before)
