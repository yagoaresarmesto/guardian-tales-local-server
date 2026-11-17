# SPDX-License-Identifier: Apache-2.0
"""Natural stamina recharge preserves timers, caps and unrelated imported state."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.campaign import CHARGED_STAMINA
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.snapshots import CLIENT, import_snapshot
from guardian_tales.stamina_regen import MAX_REVISION, charge_stamina
from tests.test_snapshots import synthetic_snapshot

ROUTE = "/user/charge-stamina"


class StaminaRegenTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.references = self.root / "references"
        self.references.mkdir()
        self.catalog = self.references / "stamina_regen_catalog.json"
        self.catalog.write_text(
            json.dumps({"client": CLIENT, "base_max": 5, "interval_minutes": 10})
        )
        snapshot = synthetic_snapshot()
        stamina = next(
            a for a in snapshot["profile"]["User"]["Assets"] if a["Id"] == CHARGED_STAMINA
        )
        stamina.update(Amount=3, Spent=-9, MaxAdj=2, NextCharge="2026-11-17T12:10:00.1234567+00:00")
        self.source = self.root / "synthetic.json"
        self.source.write_text(json.dumps(snapshot))
        self.state = self.root / "state"
        import_snapshot(self.source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.store = GuestStore(self.db, self.references)
        self.now = datetime(2026, 11, 17, 12, 10, 0, 123457, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def stamina(self, profile):
        return next(a for a in profile["User"]["Assets"] if a["Id"] == CHARGED_STAMINA)

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))

    def charge(self, now=None, body=None):
        return self.store.account.charge_stamina(body, self.now if now is None else now)

    def test_tick_changes_only_charged_amount_anchor_and_revision(self):
        before = self.store.account.profile()
        source = self.source.read_bytes()
        expected = copy.deepcopy(before)
        self.stamina(expected).update(Amount=4, NextCharge="2026-11-17T12:20:00.1234567+00:00")
        expected["User"]["Cas"] += 1
        self.assertEqual(self.charge(), {"User": expected["User"]})
        self.assertEqual(self.store.account.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)

    def test_seventh_fractional_digit_does_not_charge_early_and_timezones_match(self):
        before = list(self.db.iterdump())
        self.charge(self.now - timedelta(microseconds=1))
        self.assertEqual(list(self.db.iterdump()), before)
        profile = self.store.account.profile()
        self.stamina(profile)["NextCharge"] = "2026-11-17T14:10:00.1234567+02:00"
        self.save(profile)
        result = self.charge(self.now + timedelta(minutes=10))
        stamina = next(a for a in result["User"]["Assets"] if a["Id"] == CHARGED_STAMINA)
        self.assertEqual(stamina["Amount"], 5)
        self.assertEqual(stamina["NextCharge"], "2026-11-17T12:30:00.1234567+00:00")

    def test_catchup_caps_at_adjusted_maximum_and_retry_reopen_does_not_double_charge(self):
        original = self.store.account.profile()
        self.charge(self.now + timedelta(hours=2))
        profile = self.store.account.profile()
        self.assertEqual(self.stamina(profile)["Amount"], 7)
        self.assertEqual(self.stamina(profile)["Spent"], -9)
        self.assertEqual(profile["User"]["Cas"], original["User"]["Cas"] + 1)
        self.assertEqual(self.stamina(profile)["NextCharge"], "2026-11-17T14:20:00.1234567+00:00")
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.store = GuestStore(self.db, self.references)
        before = list(self.db.iterdump())
        self.charge(self.now + timedelta(hours=3))
        self.assertEqual(list(self.db.iterdump()), before)

    def test_missing_anchor_future_anchor_and_over_cap_balance_are_preserved(self):
        original = self.store.account.profile()
        for amount, timestamp in (
            (3, None),
            (3, "2026-11-18T12:10:00+00:00"),
            (20, "2026-11-17T10:00:00+00:00"),
        ):
            profile = copy.deepcopy(original)
            self.stamina(profile).update(Amount=amount, NextCharge=timestamp)
            self.save(profile)
            before = list(self.db.iterdump())
            self.charge()
            self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_assets_timers_revisions_and_clocks_reject_without_writes(self):
        original = self.store.account.profile()
        invalid = [
            ("Amount", True),
            ("Amount", -1),
            ("MaxAdj", "2"),
            ("MaxAdj", -5),
            ("NextCharge", "2026-11-17T12:00:00"),
            ("NextCharge", "2026-02-30T12:00:00Z"),
            ("NextCharge", "2026-11-17T12:00:00.12345678Z"),
            ("NextCharge", 10),
        ]
        for field, value in invalid:
            profile = copy.deepcopy(original)
            self.stamina(profile)[field] = value
            self.save(profile)
            before = list(self.db.iterdump())
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.charge()
            self.assertEqual(list(self.db.iterdump()), before)
        for revision in (True, -1, MAX_REVISION):
            profile = copy.deepcopy(original)
            profile["User"]["Cas"] = revision
            self.save(profile)
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.charge()
            self.assertEqual(list(self.db.iterdump()), before)
        self.save(original)
        before = list(self.db.iterdump())
        for now in (datetime(2026, 11, 17), "now"):
            with self.assertRaises(ValueError):
                self.charge(now)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_catalog_and_asset_ambiguity_rejections_are_atomic(self):
        valid = {"client": CLIENT, "base_max": 5, "interval_minutes": 10}
        for value in (
            {},
            dict(valid, client={}),
            dict(valid, base_max=0),
            dict(valid, interval_minutes=True),
            dict(valid, interval_minutes=0),
        ):
            self.catalog.write_text(json.dumps(value))
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.charge()
            self.assertEqual(list(self.db.iterdump()), before)
        self.catalog.unlink()
        with self.assertRaises(ValueError):
            self.charge()
        self.catalog.write_text(json.dumps(valid))
        profile = self.store.account.profile()
        profile["User"]["Assets"].append(copy.deepcopy(self.stamina(profile)))
        self.save(profile)
        before = list(self.db.iterdump())
        with self.assertRaises(ValueError):
            self.charge()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_wire_authentication_empty_body_and_extra_parameters(self):
        session = BootstrapSession(self.store)

        def call(route, body):
            packet = parse_packet(
                encode_packet(
                    Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=25)
                )
            )
            return read_json_body(parse_packet(encode_packet(session.handle(packet))))

        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            call(ROUTE, None)
        self.assertEqual(list(self.db.iterdump()), before)
        call("/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": False})
        with patch.object(
            self.store.account,
            "charge_stamina",
            side_effect=lambda body: charge_stamina(self.store.account, body, self.now),
        ):
            for body in ([], False, 0, {"Count": 1}, {"Now": "2099-01-01"}):
                before = list(self.db.iterdump())
                with self.assertRaises(PacketError):
                    call(ROUTE, body)
                self.assertEqual(list(self.db.iterdump()), before)
            first = call(ROUTE, None)
            before = list(self.db.iterdump())
            self.assertEqual(call(ROUTE, {}), first)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_failed_update_rolls_back_timer_and_balance_and_retry_charges_once(self):
        self.db.execute(
            "CREATE TRIGGER fail_regen BEFORE UPDATE ON local_account BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.DatabaseError):
            self.charge()
        self.assertEqual(list(self.db.iterdump()), before)
        self.db.execute("DROP TRIGGER fail_regen")
        self.db.commit()
        self.charge()
        self.assertEqual(self.stamina(self.store.account.profile())["Amount"], 4)
