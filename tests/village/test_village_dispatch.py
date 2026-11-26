# SPDX-License-Identifier: Apache-2.0
"""Preparing a dispatch opens one persistent event for the selected village base."""

import copy
import json
import sqlite3
import unittest

from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, digest
from guardian_tales.village import current_village
from guardian_tales.village_dispatch import PREPARE
from tests.village.test_village_harvest import VillageFixture


class VillageDispatchTests(VillageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        data = {
            "LobbyBuildings": [
                {"Id": 801, "PortalType": "DispatchBase", "IsOpened": True, "DispatchId": 7},
                {"Id": 802, "PortalType": "DispatchBase", "IsOpened": False, "DispatchId": 7},
            ],
            "Dispatches": [{"Id": 7, "StartEvents": [81, 82]}],
            "DispatchEvents": [{"Id": 81}, {"Id": 82}],
        }
        content = json.dumps(data)
        self.static = self.references / "static_data_get.bin"
        self.static.write_bytes(
            compress(f"lobbyvillage\n{content}\n1\n{digest(content.encode())}\n".encode())
        )
        self.initial["Buildings"].append({"Id": 15, "SpecId": 801, "Status": 0, "EndTime": 0})
        self.initial["Dispatches"] = [{"Id": 16, "StartEventId": 99}]
        self.save_village(self.initial)
        self.body = {"dispatchBuildingId": 15}

    def test_prepared_event_survives_reopen_and_new_request(self):
        profile = self.store.account.profile()
        village = self.call(self.body, PREPARE)["UserLobbyVillage"]
        start = village["Dispatches"][-1]["StartEventId"]
        self.assertIn(start, (81, 82))
        expected = copy.deepcopy(self.initial)
        expected["Cas"] += 1
        expected["Dispatches"].append(
            dict(Id=15, DispatchId=7, StartEventId=start, StartRewardGroupId=0, FinishEventId=0)
        )
        self.assertEqual(village, expected)
        self.open_session(reconnect=True)
        self.assertEqual(self.call(None, "/lobby-village/enter")["UserLobbyVillage"], expected)
        self.assertEqual(self.call(self.body, PREPARE, sequence=52), {"UserLobbyVillage": expected})
        self.assertEqual(self.store.account.profile(), profile)

    def test_old_retry_cannot_recreate_an_event_or_overwrite_later_progress(self):
        self.call(self.body, PREPARE)
        progressed = current_village(self.db)
        progressed["Dispatches"].pop()
        progressed["Cas"] += 1
        self.save_village(progressed)
        self.static.unlink()
        writes = self.db.total_changes
        self.assertEqual(self.call(self.body, PREPARE), {"UserLobbyVillage": progressed})
        with self.assertRaises(PacketError):
            self.call({"dispatchBuildingId": 1}, PREPARE)
        self.assertEqual(self.db.total_changes, writes)

    def test_rejects_busy_closed_wrong_or_unowned_building_without_writes(self):
        for field, value in (("Status", 4), ("SpecId", 802), ("SpecId", 3001), ("Id", 25)):
            village = copy.deepcopy(self.initial)
            village["Buildings"][-1][field] = value
            self.save_village(village)
            with self.subTest(change=(field, value)), self.assertRaises(PacketError):
                self.call(self.body, PREPARE)
            self.assertEqual(current_village(self.db), village)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM village_dispatch_prepare_requests").fetchone(),
            (0,),
        )

    def test_invalid_or_unsigned_requests_and_failed_receipt_change_nothing(self):
        for body in (
            None,
            {},
            {"dispatchBuildingId": True},
            {"dispatchBuildingId": 15, "reward": 7},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, PREPARE)
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.call(self.body, PREPARE)
        self.session.signed_in = True
        self.db.execute(
            "CREATE TRIGGER fail_prepare BEFORE INSERT ON village_dispatch_prepare_requests "
            "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.body, PREPARE)
        self.assertEqual(current_village(self.db), self.initial)
