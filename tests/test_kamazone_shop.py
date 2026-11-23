# SPDX-License-Identifier: Apache-2.0
"""Season-bound shop entry/closing preserves the existing map and saved account."""

import copy
import json
import unittest
from unittest.mock import patch

from guardian_tales import kamazone_run as run
from guardian_tales import kamazone_shop as shop
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.protocol import PacketError
from tests import test_kamazone_run as fixtures
from tests.test_snapshots import request


class KamazoneShopTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazoneRunTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.db, self.root, self.session = self.owner.db, self.owner.root, self.owner.session
        self.owner.owner.practice("disable")
        mode = self.owner.fixture.tables["kamazonland2"]
        for row in mode["FloorPresets"]:
            if row["Id"] in (110, 111):
                for kind in run.PROBABILITIES:
                    row[kind + "Prob"] = int((row["Id"], kind) in ((110, "Normal"), (111, "Shop")))
        mode["Artifacts"] = [
            *[dict(Id=i, Kind="Normal", Lootable=True, Price=100 * i) for i in range(1, 6)],
            dict(Id=6, Kind="Normal", Lootable=False, Price=100),
            dict(Id=70, Kind="Normal", Lootable=True, Price=80),
            dict(Id=701, Kind="Effect", Lootable=True, Price=50),
            dict(Id=801, Kind="Curse", Lootable=True, Price=-50),
        ]
        for season in mode["Seasons"]:
            season["Artifacts"] = [1, 2, 3, 4, 5, 6, 701, 801] if season["Id"] == 43 else [70]
            season["ArtifactsException"] = [5] if season["Id"] == 43 else []
        self.owner.fixture.write_source()
        self.owner.owner.command("select", "--season-id", "43")
        self.owner.owner.enable()
        self.owner.owner.save({"174": 1}, 950)
        self.sequence = 7000
        self.before = list(self.db.iterdump()), self.db.total_changes
        self.files = {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != run.STATE}
        self.static = self.session.handle(request("/static-data/get", {})).body
        self.source = self.session.store.references.read_bytes("static_data_get.bin")
        self.initial = self.call(run.CHALLENGE, {"Difficulty": 3})["UserKamazonLand"]
        self.path = self.root / run.STATE
        value = run.load(self.session.store.references)
        self.map = copy.deepcopy(run.floor_nodes(self.source, 43, value["seed"]))

    def call(self, route, body, sequence=None):
        self.sequence += 1
        packet = request(route, body)
        packet["sequence_id"] = self.sequence if sequence is None else sequence
        reply = self.session.handle(packet)
        self.assertEqual(
            (reply.packet_type, reply.body_type, reply.sequence_id), (1, 1, packet["sequence_id"])
        )
        return json.loads(reply.body)

    def entry(self):
        return self.call("/kamazonland/enter", {"IsPartial": False})["UserKamazonLand"]

    def open(self, sequence=None):
        return self.call(run.START, {"NodeId": 111}, sequence)["UserKamazonLand"]

    def reject(self, route, body):
        before = self.path.read_bytes()
        with self.assertRaises(PacketError):
            self.call(route, body)
        self.assertEqual(self.path.read_bytes(), before)

    def unchanged(self, user):
        self.assertEqual((list(self.db.iterdump()), self.db.total_changes), self.before)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != run.STATE}, self.files
        )
        self.assertEqual(self.session.handle(request("/static-data/get", {})).body, self.static)
        self.assertEqual(
            run.floor_nodes(self.source, 43, run.load(self.session.store.references)["seed"]),
            self.map,
        )
        for key in (
            "Hps",
            "KamazonPoint",
            "KamazonPointTotal",
            "Benefits",
            "SilverCoin",
            "Artifacts",
            "Curses",
        ):
            self.assertEqual(user[key], self.initial[key], key)

    def test_empty_party_can_open_original_price_seasonal_stock_and_resume_without_rerolls(self):
        opened = self.open()
        node = next(n for n in opened["Nodes"] if n["Id"] == 111)
        self.assertEqual((node["Type"], node["State"], node["BattleMonsters"]), ("Shop", 1, []))
        self.assertEqual(len(node["ShopArtifacts"]), 3)
        self.assertTrue({int(i) for i in node["ShopArtifacts"]} <= {1, 2, 3, 4})
        self.assertTrue(
            all(type(sold) is bool and not sold for sold in node["ShopArtifacts"].values())
        )
        self.assertEqual((node["ShopCurses"], node["ShopEffectArtifacts"]), ({}, {}))
        self.assertEqual(opened["Characters"], [])
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.session.request_epoch = "reopened-shop"
        self.assertEqual(self.entry(), opened)
        self.assertEqual(self.open(), opened)
        self.unchanged(opened)

    def test_close_shop_marks_it_complete_and_allows_the_next_connected_battle(self):
        opened = self.open()
        closed = self.call(shop.CLOSE, {"NodeId": 111}, 850)
        self.assertEqual(
            set(closed), {"NewSeason", "UserKamazonLand", "ChoiceEffectResults", "AddedItems"}
        )
        self.assertEqual((closed["ChoiceEffectResults"], closed["AddedItems"]), ([], []))
        user = closed["UserKamazonLand"]
        self.assertEqual(next(n for n in user["Nodes"] if n["Id"] == 111)["State"], 11)
        self.assertFalse(run.load(self.session.store.references)["stage_started"])
        self.assertEqual(user["Progress"], opened["Progress"])
        self.call(run.SELECT, {"CharacterIds": self.owner.characters})
        self.call(run.START, {"NodeId": 120})
        current = self.call(run.BATTLE, dict(NodeId=120, Formation=[12, 3, 19, 9]))[
            "UserKamazonLand"
        ]
        before = self.path.read_bytes()
        self.assertEqual(self.call(shop.CLOSE, {"NodeId": 111}, 850)["UserKamazonLand"], current)
        self.assertEqual(self.path.read_bytes(), before)
        self.reject(shop.CLOSE, {"NodeId": 111})
        self.unchanged(current)

    def test_shop_entry_and_explicit_close_retries_never_reroll_or_reopen_closed_stock(self):
        self.open(851)
        closed = self.call(shop.CLOSE, {"NodeId": 111}, 852)["UserKamazonLand"]
        self.assertEqual(self.call(shop.CLOSE, {"NodeId": 111})["UserKamazonLand"], closed)
        before = self.path.read_bytes()
        self.assertEqual(self.open(851), closed)
        self.assertEqual(self.path.read_bytes(), before)
        self.reject(run.START, {"NodeId": 111})
        self.unchanged(closed)

    def test_adjacency_open_phase_and_combat_type_guards_apply_to_shop_nodes(self):
        self.reject(shop.CLOSE, {"NodeId": 111})
        self.reject(run.START, {"NodeId": 120})
        self.open()
        self.call(run.SELECT, {"CharacterIds": self.owner.characters})
        self.reject(run.START, {"NodeId": 120})
        self.reject(run.BATTLE, dict(NodeId=111, Formation=[12, 3, 19, 9]))
        for body in ({}, {"NodeId": True}, {"NodeId": 110}, {"NodeId": 111, "Extra": 1}):
            self.reject(shop.CLOSE, body)
        self.unchanged(self.entry())

    def test_legacy_run_without_shop_field_reads_without_writes_and_can_open_a_shop(self):
        legacy = json.loads(self.path.read_bytes())
        del legacy["shops"]
        self.path.write_text(json.dumps(legacy))
        before = self.path.read_bytes()
        self.assertEqual(self.entry(), self.initial)
        self.assertEqual(self.path.read_bytes(), before)
        self.open()
        self.assertIn("111", json.loads(self.path.read_bytes())["shops"])
        self.unchanged(self.entry())

    def test_invalid_foreign_or_nonshop_saved_stock_is_rejected_without_writes(self):
        self.open()
        saved = self.path.read_bytes()
        for stock in (
            {"111": {"70": False}},
            {"111": {"5": False}},
            {"111": {"1": 1}},
            {"120": {"1": False}},
            {"111": {}},
        ):
            value = json.loads(saved)
            value["shops"] = stock
            self.path.write_text(json.dumps(value))
            self.reject("/kamazonland/enter", {"IsPartial": False})
        self.path.write_bytes(saved)
        self.unchanged(self.entry())

    def test_authentication_and_failed_open_close_publication_preserve_the_account_and_run(self):
        for route, body in ((run.START, {"NodeId": 111}), (shop.CLOSE, {"NodeId": 111})):
            self.session.signed_in = False
            self.reject(route, body)
            self.session.signed_in = True
            with patch(
                "guardian_tales.kamazone_run.atomic_write", side_effect=OSError("synthetic")
            ):
                self.reject(route, body)
            if route == run.START:
                self.open()
        self.unchanged(self.entry())

    def test_stock_uses_the_selected_seasons_catalog_and_excludes_special_goods(self):
        for seed in range(5):
            self.assertEqual(shop.stock(self.source, 41, seed, 111), {"70": False})
            self.assertTrue(set(shop.stock(self.source, 43, seed, 111)) <= {"1", "2", "3", "4"})
        self.unchanged(self.entry())
