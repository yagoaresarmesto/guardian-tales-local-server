# SPDX-License-Identifier: Apache-2.0
"""Regular hero/weapon banners debit paid gems and enforce persisted daily limits."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from guardian_tales.heroes.characters import new_character
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.settlement.village import MAX_REVISION
from guardian_tales.summons.summon_payment import CHARACTER_ROUTE, WEAPON_ROUTE
from tests import FIXTURES
from tests.account.test_snapshots import synthetic_snapshot

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
CLOCK = "guardian_tales.summons.summon_payment.utc_now"
RANDOM = "guardian_tales.summons.summon_draw.secrets.randbelow"


class PaidSummonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.static = {
            "constants": {
                "GemsForSummonDiscount": 100,
                "GemsForSummon": 300,
                "PaidGemforSummonTen": 2700,
                "SummonWeaponBaseLevel": 19,
            },
            "items": [
                {
                    "Id": spec,
                    "Type": "weapon",
                    "Summonable": True,
                    "Limited": False,
                    "Rarity": rank,
                    "OriginRarity": rank,
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
            "weaponenhance": {
                "Constants": {"MagicMetalPerSummonWeapon": 10},
                "LevelExps": [{"Level": i, "TotalExps": (i + 1) * 100} for i in range(25)],
            },
        }
        self.write_static()
        policy = json.loads((FIXTURES / "summon_draw_catalog.json").read_text())
        policy["heroes"]["2"] = {"rank": 0, "category": "Normal"}
        policy["origin_by_spec"]["2"] = 2
        (self.root / "summon_draw_catalog.json").write_text(json.dumps(policy), encoding="utf-8")
        self.store = GuestStore(self.db, self.root)
        snapshot = synthetic_snapshot()
        assets = {a["Id"]: a for a in snapshot["profile"]["User"]["Assets"]}
        assets[70002].update(Amount=10000, Spent=17)
        assets[70003].update(Amount=10000, Spent=29)
        snapshot["profile"]["UserShop"].update(
            SelectedSummonCharacters=[],
            SelectedSummonWeapons=[],
            LastDiscountSummonCharacter={"512": "2026-11-19T12:00:00+00:00"},
            LastDiscountSummonWeapon={"512": "2026-11-19T12:00:00+00:00"},
        )
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
        reply = self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            route="/auth/sign-in",
            sequence=1,
        )
        self.assertEqual(reply["StartOfDay"], "00:00:00")

    def body(self, cost=1, count=1):
        return {"IsPickUp": False, "PickUpKey": 0, "Count": count, "SummonCostType": cost}

    def call(self, body=None, route=WEAPON_ROUTE, sequence=971, session=None):
        body = self.body() if body is None else body
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        with patch(CLOCK, return_value=NOW), patch(RANDOM, return_value=0):
            reply = (session or self.session).handle(request)
        self.assertEqual(reply.sequence_id, sequence)
        return read_json_body(parse_packet(encode_packet(reply)))

    def asset(self, profile, identity):
        return next(a for a in profile["User"]["Assets"] if a["Id"] == identity)

    def reject(self, body=None, route=WEAPON_ROUTE, sequence=972):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, route, sequence)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_daily_weapon_debits_only_paid_gems_and_preserves_other_banner_timestamps(self):
        original = self.store.account.profile()
        source = self.source.read_bytes()
        response = self.call()
        expected = copy.deepcopy(original)
        for k, delta in (("Amount", -100), ("Spent", 100)):
            self.asset(expected, 70002)[k] += delta
        expected["User"]["ItemWeapons"] = response["User"]["ItemWeapons"]
        expected["User"]["ItemIdCounter"] += 1
        expected["User"]["Cas"] += 1
        self.asset(expected, 70008)["Amount"] += 10
        self.asset(expected, 70014)["Amount"] += 1
        expected["UserRecord"]["SummonWeaponCount"] += 1
        expected["UserRecord"]["Cas"] += 1
        expected["UserShop"]["LastDiscountSummonWeapon"]["0"] = NOW.isoformat()
        expected["UserShop"]["Cas"] += 1
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(len(response["Summons"]), 1)
        self.assertEqual(self.source.read_bytes(), source)

    def test_regular_hero_banner_draws_without_a_selected_wishlist(self):
        response = self.call(route=CHARACTER_ROUTE)
        self.assertEqual(response["Summons"][0]["Type"], 1)
        self.assertEqual(self.asset(response, 70002)["Amount"], 9900)
        self.assertEqual(response["UserShop"]["SelectedSummonCharacters"], [])
        self.assertEqual(response["UserShop"]["LastDiscountSummonCharacter"]["0"], NOW.isoformat())

    def test_character_and_weapon_daily_limits_are_independent(self):
        self.call(route=CHARACTER_ROUTE)
        response = self.call()
        self.assertEqual(self.asset(response, 70002)["Amount"], 9800)
        for kind in ("Character", "Weapon"):
            self.assertEqual(
                response["UserShop"]["LastDiscountSummon" + kind]["0"], NOW.isoformat()
            )
        self.reject(route=CHARACTER_ROUTE)
        self.reject()

    def test_same_day_new_request_or_new_login_rejects_but_exact_retry_is_free(self):
        first = self.call()
        self.reject()
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call(), first)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.open_session(reconnect=False)
        self.reject(sequence=971)

    def test_next_utc_day_allows_a_new_discount_and_offset_timestamps_are_compared_in_utc(self):
        for stamp in ("2026-11-20T00:59:59+01:00", "2026-11-19T23:59:59+00:00"):
            profile = self.store.account.profile()
            profile["UserShop"]["LastDiscountSummonWeapon"]["0"] = stamp
            self.save(profile)
            self.open_session(reconnect=False)
            self.call()
        profile = self.store.account.profile()
        profile["UserShop"]["LastDiscountSummonWeapon"]["0"] = "2026-11-20T01:00:00+01:00"
        self.save(profile)
        self.open_session(reconnect=False)
        self.reject(sequence=971)

    def test_full_price_paid_one_and_ten_draws_do_not_use_the_daily_discount(self):
        before = self.store.account.profile()
        for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
            for seq, count in ((981, 1), (982, 10)):
                self.assertEqual(len(self.call(self.body(4, count), route, seq)["Summons"]), count)
        after = self.store.account.profile()
        self.assertEqual(self.asset(after, 70002)["Amount"], 4000)
        self.assertEqual(self.asset(after, 70003), self.asset(before, 70003))
        self.assertEqual(after["UserShop"], before["UserShop"])

    def test_regular_banner_free_gems_and_ordinary_tickets_keep_existing_payment_rules(self):
        before = self.store.account.profile()
        for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
            self.call(self.body(0), route)
        after = self.store.account.profile()
        self.assertEqual(self.asset(after, 70003)["Amount"], 9400)
        self.assertEqual(self.asset(after, 70002), self.asset(before, 70002))
        self.assertEqual(after["UserShop"], before["UserShop"])
        after["User"]["ItemIdCounter"] += 1
        after["User"]["ItemStackables"].append(
            {"Id": after["User"]["ItemIdCounter"], "ItemId": 110007, "Amount": 2}
        )
        self.save(after)
        for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
            self.call(self.body(3), route, sequence=972)
        current = self.store.account.profile()
        self.assertFalse(any(i["ItemId"] == 110007 for i in current["User"]["ItemStackables"]))
        self.assertEqual(self.asset(current, 70002), self.asset(after, 70002))
        self.assertEqual(self.asset(current, 70003), self.asset(after, 70003))

    def test_insufficient_paid_balance_never_falls_back_to_free_gems(self):
        profile = self.store.account.profile()
        self.asset(profile, 70002)["Amount"] = 99
        self.save(profile)
        for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
            self.reject(route=route)

    def test_reconnect_retry_keeps_current_progress_and_survives_removed_price_data(self):
        first = self.call()
        profile = self.store.account.profile()
        profile["User"]["ItemWeapons"][-1]["Experience"] += 17
        self.save(profile)
        (self.root / "static_data_get.bin").unlink()
        (self.root / "summon_draw_catalog.json").unlink()
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session(reconnect=True)
        self.db.execute("PRAGMA query_only=ON")
        before, changes = list(self.db.iterdump()), self.db.total_changes
        repeated = self.call()
        self.assertEqual(repeated["Summons"], first["Summons"])
        self.assertEqual(repeated["User"], profile["User"])
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_pickups_event_payments_and_malformed_regular_requests_reject(self):
        for mutate in (
            lambda b: b.update(IsPickUp=True),
            lambda b: b.update(IsPickUp=0),
            lambda b: b.update(PickUpKey=512),
            lambda b: b.update(PickUpKey=False),
            lambda b: b.update(Count=10),
            lambda b: b.update(SummonCostType=2),
            lambda b: b.update(SummonCostType=5),
            lambda b: b.update(Count=True),
            lambda b: b.update(SummonCostType=True),
            lambda b: b.pop("PickUpKey"),
        ):
            body = self.body()
            mutate(body)
            for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
                self.reject(body, route)

    def test_paid_and_discount_modes_are_not_enabled_on_wishlist_routes(self):
        for route in ("/summon/select-character", "/summon/select-weapon"):
            for cost in (1, 4):
                self.reject({"Count": 1, "SummonCostType": cost}, route)

    def test_invalid_package_shop_revision_or_daily_timestamp_rejects_without_repair(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["UserShop"].update(DiscountSummonPackage={}),
            lambda p: p["UserShop"].update(Cas=MAX_REVISION),
            lambda p: p["UserShop"].update(LastDiscountSummonWeapon=None),
            lambda p: p["UserShop"]["LastDiscountSummonWeapon"].update({"0": "invalid"}),
            lambda p: p["UserShop"]["LastDiscountSummonWeapon"].update(
                {"0": "2026-11-20T00:00:00"}
            ),
            lambda p: p["UserShop"]["LastDiscountSummonWeapon"].update(
                {"0": "2026-11-21T00:00:00+00:00"}
            ),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject()

    def test_user_record_and_spending_limits_reject_before_persisting_payment(self):
        original = self.store.account.profile()
        for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
            for mutate in (
                lambda p: p["User"].update(Cas=MAX_REVISION),
                lambda p: p["UserRecord"].update(Cas=MAX_REVISION),
                lambda p: p["UserRecord"].update(UserId=1),
                lambda p: self.asset(p, 70002).update(Spent=MAX_REVISION - 99),
            ):
                profile = copy.deepcopy(original)
                mutate(profile)
                self.save(profile)
                self.reject(route=route)

    def test_missing_duplicate_or_invalid_paid_gem_balances_reject(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Assets=[a for a in p["User"]["Assets"] if a["Id"] != 70002]),
            lambda p: p["User"]["Assets"].append(copy.deepcopy(self.asset(p, 70002))),
            lambda p: self.asset(p, 70002).update(Amount=True),
            lambda p: self.asset(p, 70002).update(Spent=-1),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
                self.reject(route=route)

    def test_missing_and_corrupt_paid_prices_fail_without_charge(self):
        original = copy.deepcopy(self.static)
        for value in (None, True, 0, "100"):
            self.static = copy.deepcopy(original)
            self.static["constants"]["GemsForSummonDiscount"] = value
            self.write_static()
            for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
                self.reject(route=route)

    def test_failed_receipt_rolls_back_paid_cost_timestamp_and_grants_for_both_kinds(self):
        for route, table in (
            (CHARACTER_ROUTE, "character_summon_requests"),
            (WEAPON_ROUTE, "weapon_summon_requests"),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_paid BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):
                self.call(route=route)
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_paid")
            self.db.commit()

    def test_regular_duplicate_hero_keeps_evolved_owned_hero_and_credits_crystals(self):
        profile = self.store.account.profile()
        hero = new_character(2, 401, 3)
        hero.update(Experience=987654, LimitBreaks=5)
        profile["User"]["Characters"].append(hero)
        profile["User"]["CharacterIdCounter"] = 2
        self.save(profile)
        request = parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps(self.body()).encode(),
                    body_type=1,
                    api=CHARACTER_ROUTE,
                    sequence_id=971,
                )
            )
        )
        with patch(CLOCK, return_value=NOW), patch(RANDOM, side_effect=[99, 0]):
            reply = read_json_body(parse_packet(encode_packet(self.session.handle(request))))
        self.assertEqual(reply["User"]["Characters"], profile["User"]["Characters"])
        self.assertEqual(reply["Summons"][0]["State"], 2)
        self.assertEqual(
            self.asset(reply, 70009)["Amount"], self.asset(profile, 70009)["Amount"] + 50
        )

    def test_authentication_and_completed_prologue_are_required(self):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(session=BootstrapSession(self.store))
        self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            store = GuestStore(db, self.root)
            with self.assertRaises(ValueError):
                store.account.draw_summon_weapons(self.body(), "unfinished", regular=True)

    def test_regular_fresh_account_needs_no_wishlist_or_save_reimport(self):
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
            self.asset(profile, 70002)["Amount"] = 500
            with db:
                db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            session = BootstrapSession(store)
            self.call(
                {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": False},
                route="/auth/sign-in",
                sequence=1,
                session=session,
            )
            for route in (CHARACTER_ROUTE, WEAPON_ROUTE):
                self.assertEqual(len(self.call(route=route, session=session)["Summons"]), 1)
            self.assertEqual(self.asset(store.account.profile(), 70002)["Amount"], 300)

    def test_conflicting_paid_request_cannot_reuse_a_frozen_receipt(self):
        self.call()
        self.reject(self.body(4), sequence=971)
