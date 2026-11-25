# SPDX-License-Identifier: Apache-2.0
"""The village building's shop is an authenticated, read-only popup."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from guardian_tales.lobby import village_shop
from guardian_tales.protocol import PacketError
from guardian_tales.snapshots import preserved_read
from tests.test_village_harvest import VillageFixture

SHOP = "/lobby-village/enter-shop"


class VillageShopTests(VillageFixture, unittest.TestCase):
    def test_expired_import_with_ids_only_opens_without_writes_or_a_refresh_loop(self):
        current = dict(
            self.initial,
            NextShopRefreshTime="2000-01-01T00:00:00+00:00",
            SaleProductIds=[51, 52],
            PurchasedShopItemCount={"51": 1},
        )
        self.save_village(current)
        before = self.db.total_changes
        reply = self.call(None, SHOP)
        self.assertEqual(reply["LobbyVillageShopItems"], [])
        deadline = datetime.fromisoformat(reply["UserLobbyVillage"]["NextShopRefreshTime"])
        self.assertGreater(deadline, datetime.now(timezone.utc))
        self.assertEqual(
            reply["UserLobbyVillage"], dict(current, NextShopRefreshTime=deadline.isoformat())
        )
        self.assertEqual(self.call({}, SHOP), reply)
        self.assertEqual(
            preserved_read(self.db, "/lobby-village/enter")["UserLobbyVillage"], current
        )
        self.assertEqual(self.db.total_changes, before)

    def test_current_clock_and_supplied_product_rows_are_forwarded(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        deadline = (now + timedelta(hours=2)).isoformat()
        reads = json.loads(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        )
        entry = reads["/lobby-village/enter"]["value"]
        entry["UserLobbyVillage"]["NextShopRefreshTime"] = deadline
        offers = [{"Id": 52, "DailyPurchasableCount": 2}, {"Id": 51, "DailyPurchasableCount": 1}]
        entry["LobbyVillageShopItems"] = offers
        with self.db:
            self.db.execute("UPDATE imported_account SET startup_reads=?", (json.dumps(reads),))
        self.assertEqual(
            village_shop(self.db, None, now),
            {"LobbyVillageShopItems": offers, "UserLobbyVillage": entry["UserLobbyVillage"]},
        )

    def test_entry_rejects_purchase_parameters_and_requires_sign_in(self):
        before = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call({"amount": 1}, SHOP)
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.call(None, SHOP)
        self.assertEqual(self.db.total_changes, before)
