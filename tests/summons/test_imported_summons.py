# SPDX-License-Identifier: Apache-2.0
"""Imported advanced heroes retain their progression through local draw operations."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales.accounts.snapshots import import_snapshot
from guardian_tales.heroes.characters import new_character
from guardian_tales.inventory.items import inventory_item
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from tests import FIXTURES
from tests.account.test_snapshots import synthetic_snapshot


class ImportedSummonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.references = self.root / "reference"
        self.references.mkdir()
        for name in ("summon_draw_catalog.json", "summon_selection_catalog.json"):
            (self.references / name).write_bytes((FIXTURES / name).read_bytes())
        catalog_path = self.references / "summon_draw_catalog.json"
        catalog = json.loads(catalog_path.read_text())
        catalog["heroes"]["2"] = {"rank": 0, "category": "Normal"}
        catalog["origin_by_spec"]["2"] = 2
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        snapshot = synthetic_snapshot()
        user = snapshot["profile"]["User"]
        user["ItemWeapons"].append(inventory_item(3, 9001))
        hero = new_character(2, 401, 3)
        hero.update(
            Experience=987654, LimitBreaks=5, BlessLevel=3, Knowledge=7, AwakeningTree="AQ=="
        )
        user["Characters"].append(hero)
        user["CharacterIdCounter"] = 2
        user["ItemStackables"] = [
            dict(inventory_item(4, 110007), Amount=12),
            dict(inventory_item(5, 110015), Amount=3),
            dict(inventory_item(6, 110099), Amount=0),
            dict(inventory_item(7, 110007), Amount=0),
        ]
        user["ItemIdCounter"] = 7
        assets = {row["Id"]: row for row in user["Assets"]}
        assets[70003].update(Amount=30000, Spent=90)
        assets[70009]["Amount"] = 25
        assets[70014]["Amount"] = 40
        assets[70012]["Spent"] = -200
        snapshot["profile"]["UserShop"]["SelectedSummonCharacters"] = [101, 102, 103, 104, 105]
        snapshot["profile"]["UserRecord"]["SummonCharacterCount"] = 1400
        source = self.root / "synthetic.json"
        source.write_text(json.dumps(snapshot), encoding="utf-8")
        self.state = self.root / "state"
        import_snapshot(source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.store = GuestStore(self.db, self.references)
        self.session = BootstrapSession(self.store)
        self.login(False)

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def call(self, route, body=None, sequence=31):
        request = parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps(body).encode(),
                    body_type=1,
                    api=route,
                    sequence_id=sequence,
                )
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(request))))

    def login(self, reconnect):
        return self.call(
            "/auth/sign-in",
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            1,
        )

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def draw_unique(self, body, sequence=31):
        with patch(
            "guardian_tales.summons.summon_draw.secrets.randbelow",
            side_effect=lambda bound: 99 if bound == 100 else 0,
        ):
            return self.call("/summon/select-character", body, sequence)

    def test_imported_wishlist_changes_only_choices_and_revision(self):
        before = self.store.account.profile()
        selected = [105, 104, 103, 102, 101]
        response = self.call("/summon/set-select-character", {"RequestOriginIds": selected})
        expected = copy.deepcopy(before)
        expected["UserShop"]["SelectedSummonCharacters"] = selected
        expected["UserShop"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(response, {"UserShop": expected["UserShop"]})
        self.call("/summon/set-select-character", {"RequestOriginIds": selected})
        self.assertEqual(self.store.account.profile(), expected)

    def test_imported_evolved_duplicate_preserves_hero_equipment_and_historical_state(self):
        before = self.store.account.profile()
        response = self.draw_unique({"Count": 1, "SummonCostType": 3})
        self.assertEqual(response["Summons"][0]["ItemId"], 2)
        self.assertEqual(response["Summons"][0]["State"], 2)
        self.assertEqual(response["Summons"][0]["StateValue"], 50)
        expected = copy.deepcopy(before)
        expected["User"]["ItemStackables"][0]["Amount"] -= 1
        assets = {row["Id"]: row for row in expected["User"]["Assets"]}
        assets[70009]["Amount"] += 50
        assets[70014]["Amount"] += 1
        expected["User"]["Cas"] += 1
        expected["UserRecord"]["SummonCharacterCount"] += 1
        expected["UserRecord"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        for route in ("/collection/list-all", "/preset/get-presets", "/lobby-village/enter"):
            self.call(route)
        self.assertEqual(self.store.account.profile(), expected)

    def test_ten_controller_draws_preserve_untouched_zero_stacks_and_existing_roster(self):
        before = self.store.account.profile()
        before["User"]["ItemStackables"][0]["Amount"] = 10
        self.save(before)
        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0):
            response = self.call("/summon/select-character", {"Count": 10, "SummonCostType": 3})
        after = self.store.account.profile()
        self.assertEqual(after["User"]["ItemStackables"], before["User"]["ItemStackables"][1:])
        self.assertEqual(after["User"]["Characters"][:2], before["User"]["Characters"])
        self.assertEqual(after["User"]["Characters"][2], new_character(3, 301))
        self.assertEqual(after["User"]["ItemWeapons"], before["User"]["ItemWeapons"])
        self.assertEqual(after["User"]["Party"], before["User"]["Party"])
        self.assertEqual([row["State"] for row in response["Summons"]], [1] + [2] * 9)
        self.assertEqual(after["UserRecord"]["SummonCharacterCount"], 1410)

    def test_one_and_ten_gem_draws_keep_current_state_on_a_receipt_retry(self):
        before = self.store.account.profile()
        first = self.draw_unique({"Count": 1, "SummonCostType": 0}, 31)
        self.draw_unique({"Count": 10, "SummonCostType": 0}, 32)
        after = self.store.account.profile()
        assets = {row["Id"]: row for row in after["User"]["Assets"]}
        self.assertEqual((assets[70003]["Amount"], assets[70003]["Spent"]), (27000, 3090))
        self.assertEqual(after["User"]["Characters"], before["User"]["Characters"])
        self.assertEqual(after["User"]["ItemStackables"], before["User"]["ItemStackables"])
        self.assertEqual(after["UserRecord"]["SummonCharacterCount"], 1411)
        assets[70003]["Amount"] -= 7
        self.save(after)
        retry = self.call("/summon/select-character", {"Count": 1, "SummonCostType": 0}, 31)
        self.assertEqual(retry["Summons"], first["Summons"])
        self.assertEqual(retry["User"], after["User"])
        self.assertEqual(self.store.account.profile(), after)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone()[0], 2
        )

    def test_selectable_controller_receipt_survives_reopen_and_fresh_logins_are_new_draws(self):
        body = {"Count": 1, "SummonCostType": 5}
        first = self.draw_unique(body)
        saved = self.store.account.profile()
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.store = GuestStore(self.db, self.references)
        self.session = BootstrapSession(self.store)
        self.login(True)
        self.assertEqual(self.call("/summon/select-character", body), first)
        self.assertEqual(self.store.account.profile(), saved)
        self.login(False)
        self.draw_unique(body)
        after = self.store.account.profile()
        self.assertEqual(after["User"]["ItemStackables"][0], saved["User"]["ItemStackables"][0])
        self.assertEqual(after["User"]["ItemStackables"][1]["Amount"], 1)
        self.assertEqual(after["User"]["Characters"], saved["User"]["Characters"])
        self.assertEqual(after["UserRecord"]["SummonCharacterCount"], 1402)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone()[0], 2
        )

    def test_invalid_or_unsupported_operations_and_receipt_failure_never_spend(self):
        before = self.store.account.profile()
        for route, body in (
            ("/summon/select-character", {"Count": 1, "SummonCostType": 1}),
            ("/summon/select-character", {"Count": True, "SummonCostType": 3}),
            ("/summon/set-select-character", {"RequestOriginIds": [101, 101]}),
            ("/user/mark-tutorial", {}),
        ):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(route, body)
            self.assertEqual(self.store.account.profile(), before)
        self.db.execute(
            "CREATE TRIGGER reject_imported_draw BEFORE INSERT ON character_summon_requests BEGIN SELECT RAISE(ABORT, 'synthetic'); END"
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.draw_unique({"Count": 1, "SummonCostType": 3})
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone()[0], 0
        )

    def test_unmapped_imported_hero_origin_rejects_without_spending(self):
        before = self.store.account.profile()
        before["User"]["Characters"][1]["CharacterId"] = 9999999
        self.save(before)
        with self.assertRaises(PacketError):
            self.draw_unique({"Count": 1, "SummonCostType": 3})
        self.assertEqual(self.store.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone()[0], 0
        )


if __name__ == "__main__":
    unittest.main()
