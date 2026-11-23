# SPDX-License-Identifier: Apache-2.0
"""Exercise the local panel against a synthetic catalog and disposable working save."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.inventory_panel.server import InventoryServer
from guardian_tales.raid_static import compress, digest
from guardian_tales.reference import ReferenceData
from guardian_tales.state_lock import StateLock


def prepare_inventory(root):
    pool = dict(OptionId=7, Probability=1, MinLevel=1, MaxLevel=3)
    option = dict(OptionId=7, Level=1, Locked=False)
    catalog = {
        "items": [
            dict(Id=1, Name="test_ticket", Type="ticket", MaxCount=10),
            dict(Id=2, Name="test_card", Type="card"),
            dict(
                Id=3,
                Name="test_ring",
                Type="weapon",
                WeaponType="accessory",
                Options=[pool],
                MinOptions=1,
                MaxOptions=1,
            ),
            dict(
                Id=4,
                Name="test_relic",
                Type="relic",
                OriginRarity=4,
                BaseOptions=[[pool]],
                ChangeOptions=[[pool]],
            ),
        ],
        "buffs": [],
        "options": [dict(Id=7, Name="relic_base_hp_scale", Class="HpScale", HpScaleAdd=0.01)],
        "__checksum__": {},
    }
    records = []
    for key, value in catalog.items():
        content = json.dumps(value)
        records.extend((key, content, "1", digest(content.encode())))
    (root / "static_data_get.bin").write_bytes(compress(("\n".join(records) + "\n").encode()))
    profile = {
        "User": {
            "Id": 1,
            "Cas": 10,
            "Characters": [],
            "ItemWeapons": [
                dict(Id=11, ItemId=3, Locked=True, Amount=1, Options=[dict(option, OptionSource=0)])
            ],
            "ItemMiscs": [
                dict(
                    Id=12,
                    ItemId=4,
                    Locked=False,
                    Amount=1,
                    RelicOptions=[dict(option, OptionSource=1), dict(option, OptionSource=2)],
                )
            ],
            "ItemStackables": [
                dict(Id=13, ItemId=1, Amount=5, Locked=False),
                dict(Id=14, ItemId=2, Amount=1, Locked=False),
            ],
        }
    }
    database = root / "server.sqlite3"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "CREATE TABLE local_account (id INTEGER PRIMARY KEY, schema_version INTEGER, profile TEXT)"
        )
        db.execute("INSERT INTO local_account VALUES(1, 3, ?)", (json.dumps(profile),))
    return database


class InventoryPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        database = prepare_inventory(self.root)
        self.server = self.enterContext(
            InventoryServer(0, database, ReferenceData(self.root), self.root)
        )
        thread = Thread(target=self.server.serve_forever, args=(0.02,))
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.shutdown)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def call(self, path, body=None, **headers):
        request = Request(
            self.origin + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Origin": self.origin, "Content-Type": "application/json", **headers},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response) if path.startswith("/api/") else response.read()

    def test_views_and_referenced_static_assets(self):
        import re

        for section in ("equipment", "relics", "consumables"):
            page = self.call("/" + section)
            self.assertIn(b'lang="en"', page)
            for asset in re.findall(rb'(?:href|src)="(/[^"]+\.(?:css|js))"', page):
                self.assertTrue(self.call(asset.decode()))
        self.assertTrue(self.call("/inventory-dom.js"))
        self.assertTrue(self.call("/equipment-options.js"))

    def test_consumable_filter_limits_lock_and_stale_edits(self):
        path = "/api/game/consumables"
        (stack,) = self.call(path)["rows"]
        self.assertEqual(stack["id"], 13)
        edit = dict(id=stack["id"], version=stack["version"], amount=9)
        with StateLock(self.root):
            self.assertFalse(self.call("/api/game/status")["writable"])
            with self.assertRaises(HTTPError) as locked:
                self.call(path, edit)
            self.assertEqual(locked.exception.code, 423)
        for body, origin, status in (
            (edit, "http://example.invalid", 403),
            (dict(edit, amount=11), self.origin, 400),
        ):
            with self.assertRaises(HTTPError) as refused:
                self.call(path, body, Origin=origin)
            self.assertEqual(refused.exception.code, status)
        self.assertEqual(self.call(path)["rows"][0]["amount"], 5)
        self.assertEqual(self.call(path, edit)["amount"], 9)
        with self.assertRaises(HTTPError) as stale:
            self.call(path, dict(edit, amount=8))
        self.assertEqual(stale.exception.code, 409)
        self.assertEqual(self.call(path)["rows"][0]["amount"], 9)

    def test_equipment_and_relic_respect_catalog_and_preserve_other_slots(self):
        path = "/api/game/equipment"
        state = self.call(path)
        (item,) = state["rows"]
        body = dict(
            id=item["id"], version=item["version"], revision=state["revision"], options={"7": 4}
        )
        with self.assertRaises(HTTPError) as invalid:
            self.call(path, body)
        self.assertEqual(invalid.exception.code, 400)
        self.call(path, dict(body, options={"7": 3}, lockedValues={"7": 3}))
        (row,) = self.call(path)["rows"][0]["options"]
        self.assertEqual((row["Level"], row["Locked"]), (3, True))
        path = "/api/game/relics"
        state = self.call(path)
        (relic,) = state["copies"]
        change = dict(group="main", slot=0, option=7, level=3)
        body = dict(
            id=relic["id"], revision=state["revision"], version=relic["version"], changes=[change]
        )
        with self.assertRaises(HTTPError) as invalid:
            self.call(path, dict(body, changes=[dict(change, level=4)]))
        self.assertEqual(invalid.exception.code, 400)
        self.call(path, body)
        (relic,) = self.call(path)["copies"]
        self.assertEqual((relic["main"][0]["Level"], relic["bonus"][0]["Level"]), (3, 1))
