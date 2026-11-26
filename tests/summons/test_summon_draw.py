# SPDX-License-Identifier: Apache-2.0
"""Local draws commit costs, heroes, duplicate rewards and stable retry receipts."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales.heroes.characters import new_character
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from tests import FIXTURES

FIXTURE = FIXTURES / "summon_draw_catalog.json"


class SummonDrawTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "summon_draw_catalog.json"
        self.catalog_file.write_bytes(FIXTURE.read_bytes())
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db, self.references)
        self.account = self.store.account
        self.account.complete_prologue(
            "lab",
            {
                "IsMale": True,
                "VoiceType": 1,
                "Weapon1ItemId": 9010010,
                "Weapon2ItemId": 9080010,
                "BobLindaQuestGrade": 0,
            },
        )
        profile = self.account.profile()
        assets = {a["Id"]: a for a in profile["User"]["Assets"]}
        assets[70003]["Amount"] = 1000400
        profile["User"]["ItemStackables"] = [
            {"Id": 3, "ItemId": 110007, "Amount": 20},
            {"Id": 4, "ItemId": 110015, "Amount": 4},
        ]
        profile["User"]["ItemIdCounter"] = 4
        profile["UserShop"]["SelectedSummonCharacters"] = [101, 102, 103, 104, 105]
        self.save(profile)
        self.body = {"Count": 10, "SummonCostType": 3}

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def save(self, p):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
        self.db.commit()

    def draw(self, body=None, operation="draw-001"):
        return self.account.draw_summon_characters(self.body if body is None else body, operation)

    def test_ticket_ten_draws_commit_one_new_hero_duplicates_mileage_and_free_retry(self):
        expected = self.account.profile()
        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0):
            response = self.draw()
        expected["User"]["ItemStackables"][0]["Amount"] = 10
        expected["User"]["Characters"].append(new_character(2, 301))
        expected["User"]["CharacterIdCounter"] = 2
        expected["User"]["Cas"] += 1
        assets = {a["Id"]: a for a in expected["User"]["Assets"]}
        assets[70009]["Amount"] += 9
        assets[70014]["Amount"] += 10
        expected["UserRecord"]["SummonCharacterCount"] += 10
        expected["UserRecord"]["Cas"] += 1
        self.assertEqual(self.account.profile(), expected)
        results = response["Summons"]
        self.assertEqual(len(results), 10)
        self.assertEqual(
            results[0],
            {
                "Type": 1,
                "ItemId": 2,
                "SpecId": 301,
                "State": 1,
                "StateValue": 0,
                "Level": 1,
                "Rank": 0,
            },
        )
        self.assertTrue(
            all(r["State"] == 2 and r["StateValue"] == 1 and r["ItemId"] == 2 for r in results[1:])
        )
        self.account = GuestStore(self.db, self.references).account
        self.assertEqual(self.draw(), response)
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone(), (1,)
        )

    def test_free_gem_one_and_ten_costs_unique_wishlist_pool_and_duplicate_crystals(self):
        with patch(
            "guardian_tales.summons.summon_draw.secrets.randbelow",
            side_effect=lambda bound: bound - 1,
        ):
            one = self.draw({"Count": 1, "SummonCostType": 0}, "one")
            ten = self.draw({"Count": 10, "SummonCostType": 0}, "ten")
        self.assertEqual(one["Summons"][0]["SpecId"], 105)
        self.assertTrue(all(r["SpecId"] == 105 and r["State"] == 2 for r in ten["Summons"]))
        p = self.account.profile()
        a = {v["Id"]: v for v in p["User"]["Assets"]}
        self.assertEqual(a[70003]["Amount"], 1000400 - 300 - 2700)
        self.assertEqual(a[70003]["Spent"], 3000)
        self.assertEqual(a[70009]["Amount"], 500)
        self.assertEqual(a[70014]["Amount"], 11)
        self.assertEqual(p["User"]["ItemStackables"][0]["Amount"], 20)
        self.assertEqual(p["UserRecord"]["SummonCharacterCount"], 11)

    def test_duplicate_origin_mapping_preserves_an_evolved_owned_hero(self):
        p = self.account.profile()
        p["User"]["Characters"].append(new_character(2, 401))
        p["User"]["CharacterIdCounter"] = 2
        self.save(p)

        def choose(bound):
            return 99 if bound == 100 else 0

        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", side_effect=choose):
            response = self.draw({"Count": 1, "SummonCostType": 3})
        r = response["Summons"][0]
        self.assertEqual((r["ItemId"], r["SpecId"], r["State"], r["StateValue"]), (2, 101, 2, 50))
        self.assertEqual(self.account.profile()["User"]["Characters"], p["User"]["Characters"])

    def test_invalid_requests_choices_and_insufficient_balances_never_spend(self):
        before = self.account.profile()
        for body in (
            {},
            {"Count": True, "SummonCostType": 3},
            {"Count": 9, "SummonCostType": 3},
            self.body | {"SummonCostType": 4},
            self.body | {"Extra": 1},
        ):
            with self.assertRaises(ValueError):
                self.draw(body)
        with self.assertRaises(ValueError):
            self.draw(operation="")
        for kind in ("wishlist", "tickets", "gems"):
            p = json.loads(json.dumps(before))
            if kind == "wishlist":
                p["UserShop"]["SelectedSummonCharacters"] = [101]
            if kind == "tickets":
                p["User"]["ItemStackables"][0]["Amount"] = 9
            if kind == "gems":
                next(a for a in p["User"]["Assets"] if a["Id"] == 70003)["Amount"] = 2699
            self.save(p)
            with self.assertRaises(ValueError):
                self.draw(self.body | {"SummonCostType": 0 if kind == "gems" else 3})
            self.assertEqual(self.account.profile(), p)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone(), (0,)
        )

    def test_catalog_validation_and_reward_overflow_preserve_everything(self):
        before = self.account.profile()
        for mutate in ("category", "mapping", "weights", "assets"):
            v = json.loads(FIXTURE.read_bytes())
            if mutate == "category":
                v["heroes"]["301"]["category"] = "Unknown"
            if mutate == "mapping":
                v["origin_by_spec"]["401"] = 999
            if mutate == "weights":
                v["category_weights"]["Normal"] = True
            if mutate == "assets":
                v["mileage_asset_id"] = 70003
            self.catalog_file.write_text(json.dumps(v))
            with self.assertRaises(ValueError):
                self.draw()
            self.assertEqual(self.account.profile(), before)
        self.catalog_file.write_bytes(FIXTURE.read_bytes())
        before["User"]["Characters"].append(new_character(2, 301))
        before["User"]["CharacterIdCounter"] = 2
        next(a for a in before["User"]["Assets"] if a["Id"] == 70009)["Amount"] = 0x7FFFFFFF
        self.save(before)
        with (
            patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0),
            self.assertRaises(ValueError),
        ):
            self.draw()
        self.assertEqual(self.account.profile(), before)

    def test_failed_receipt_insert_rolls_back_payment_heroes_and_all_rewards(self):
        before = self.account.profile()
        self.db.execute(
            "CREATE TRIGGER reject_draw BEFORE INSERT ON character_summon_requests BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
        self.db.commit()
        with (
            patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0),
            self.assertRaises(sqlite3.IntegrityError),
        ):
            self.draw()
        self.assertEqual(self.account.profile(), before)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone(), (0,)
        )

    def test_receipt_conflicts_and_replays_return_current_state_without_restoring_it(self):
        body = {"Count": 1, "SummonCostType": 3}
        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0):
            original = self.draw(body)
        p = self.account.profile()
        next(a for a in p["User"]["Assets"] if a["Id"] == 70003)["Amount"] -= 1
        self.save(p)
        retry = self.draw(body)
        self.assertEqual(retry["Summons"], original["Summons"])
        self.assertEqual(retry["User"], p["User"])
        with self.assertRaises(ValueError):
            self.draw()
        self.assertEqual(self.account.profile(), p)

    def test_ticket_cost_can_span_stacks_and_preserves_other_ticket_kinds(self):
        p = self.account.profile()
        p["User"]["ItemStackables"][0]["Amount"] = 4
        p["User"]["ItemStackables"].append({"Id": 5, "ItemId": 110007, "Amount": 6})
        p["User"]["ItemIdCounter"] = 5
        self.save(p)
        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0):
            self.draw()
        self.assertEqual(
            self.account.profile()["User"]["ItemStackables"],
            [{"Id": 4, "ItemId": 110015, "Amount": 4}],
        )

    def test_selectable_ticket_single_uses_only_its_own_stack_and_retries_for_free(self):
        before = self.account.profile()
        body = {"Count": 1, "SummonCostType": 5}
        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0):
            response = self.draw(body)
        saved = self.account.profile()
        self.assertEqual(saved["User"]["ItemStackables"][0], before["User"]["ItemStackables"][0])
        self.assertEqual(saved["User"]["ItemStackables"][1]["Amount"], 3)
        self.assertEqual(
            next(a for a in saved["User"]["Assets"] if a["Id"] == 70003),
            next(a for a in before["User"]["Assets"] if a["Id"] == 70003),
        )
        self.assertEqual(self.draw(body), response)
        self.assertEqual(self.account.profile(), saved)

    def test_bootstrap_authentication_reconnect_and_fresh_request_identity(self):
        def packet(body, route="/summon/select-character", seq=27):
            return parse_packet(
                encode_packet(
                    Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=seq)
                )
            )

        request = packet({"Count": 1, "SummonCostType": 3})
        session = BootstrapSession(self.store)
        with self.assertRaises(PacketError):
            session.handle(request)
        session.handle(
            packet(
                {"AuthKind": 0, "AccessToken": "local-test", "Reconnect": False}, "/auth/sign-in", 3
            )
        )
        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0):
            first = read_json_body(parse_packet(encode_packet(session.handle(request))))
        saved = self.account.profile()
        reconnected = BootstrapSession(self.store)
        reconnected.handle(
            packet(
                {"AuthKind": 0, "AccessToken": "local-test", "Reconnect": True}, "/auth/sign-in", 28
            )
        )
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(reconnected.handle(request)))), first
        )
        self.assertEqual(self.account.profile(), saved)
        reconnected.handle(
            packet(
                {"AuthKind": 0, "AccessToken": "local-test", "Reconnect": False}, "/auth/sign-in", 3
            )
        )
        with patch("guardian_tales.summons.summon_draw.secrets.randbelow", return_value=0):
            reconnected.handle(request)
        self.assertEqual(self.account.profile()["User"]["ItemStackables"][0]["Amount"], 18)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM character_summon_requests").fetchone(), (2,)
        )
