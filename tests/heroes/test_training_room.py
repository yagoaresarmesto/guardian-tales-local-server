# SPDX-License-Identifier: Apache-2.0
"""Training Room entry preserves saved slots, benefits, inventory and cooldowns."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.heroes.training_room import BOOST_FIELDS, ROUTE
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.settlement.village import MAX_REVISION
from tests.account.test_snapshots import synthetic_snapshot


def saved_slots():
    return {
        str(ident): {
            "Id": ident,
            "CharacterId": 1 if ident == 1 else 0,
            "ItemId": 1 if ident in (2, 5) else 0,
            "NextReactivateTime": (
                None
                if ident == 1
                else "2020-02-03T04:05:06+00:00" if ident % 2 else "2099-02-03T04:05:06+09:00"
            ),
            **{key: (ident + index) % 2 == 0 for index, key in enumerate(BOOST_FIELDS)},
            "PreservedMetadata": {"Value": ident},
        }
        for ident in range(1, 7)
    }


class TrainingRoomTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.store = GuestStore(self.db, self.root)
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["TrainingSlots"] = saved_slots()
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

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def open_session(self):
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": True}, "/auth/sign-in"
        )

    def call(self, body=None, route=ROUTE):
        packet = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=2101)
            )
        )
        return read_json_body(parse_packet(encode_packet(self.session.handle(packet))))

    def assert_read(self, body=None):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        profile = self.store.account.profile()
        expected = {"User": {key: profile["User"][key] for key in ("Id", "Cas", "TrainingSlots")}}
        self.assertEqual(self.call(body), expected)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        return expected

    def reject(self, body=None):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_imported_active_and_empty_slots_return_current_compact_user_without_changes(self):
        expected = self.assert_read()
        self.assertEqual(expected["User"]["TrainingSlots"], saved_slots())
        self.assertNotIn("Characters", expected["User"])
        self.assertNotIn("ItemWeapons", expected["User"])

    def test_native_empty_transport_null_and_empty_object_frames_are_equivalent(self):
        expected = self.assert_read()
        self.assertEqual(self.assert_read({}), expected)
        request = parse_packet(
            encode_packet(Packet(0, b"", body_type=0, api=ROUTE, sequence_id=2102))
        )
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(self.session.handle(request)))), expected
        )
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_query_only_database_keeps_assignments_benefits_cooldowns_and_all_saved_rows(self):
        self.db.execute("PRAGMA query_only=ON")
        self.assert_read()
        self.assert_read({})

    def test_empty_saved_map_does_not_initialize_or_unlock_training_slots(self):
        profile = self.store.account.profile()
        profile["User"]["TrainingSlots"] = {}
        self.save(profile)
        self.assertEqual(self.assert_read()["User"]["TrainingSlots"], {})

    def test_expired_future_nullable_and_fractional_timezone_values_are_preserved_verbatim(self):
        profile = self.store.account.profile()
        for ident, stamp in enumerate(
            (
                None,
                "0001-01-01T00:00:00+00:00",
                "2020-01-01T00:00:00Z",
                "2099-12-31T12:00:00+09:00",
                "2026-11-20T12:00:00.1234567+00:00",
                "2026-11-20T00:00:00-07:30",
            ),
            1,
        ):
            profile["User"]["TrainingSlots"][str(ident)]["NextReactivateTime"] = stamp
        self.save(profile)
        self.assert_read()

    def test_sparse_native_records_and_unknown_fields_are_retained_without_filling_defaults(self):
        profile = self.store.account.profile()
        profile["User"]["TrainingSlots"] = {"1": {"Id": 1, "FutureMetadata": [1, 2]}}
        self.save(profile)
        self.assertEqual(
            self.assert_read()["User"]["TrainingSlots"], profile["User"]["TrainingSlots"]
        )

    def test_bad_parameters_cannot_unlock_join_leave_or_reactivate_slots(self):
        for body in (True, False, 0, "", [], {"IsPartial": False}, {"SlotId": 1}, {"UserId": 1}):
            self.reject(body)

    def test_invalid_saved_owner_revision_and_slot_identity_reject_without_repairs(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Id=True),
            lambda p: p["User"].update(Cas=True),
            lambda p: p["User"].update(Cas=-1),
            lambda p: p["User"].update(Cas=MAX_REVISION + 1),
            lambda p: p["User"].update(TrainingSlots=None),
            lambda p: p["User"].update(TrainingSlots=[]),
            lambda p: p["User"]["TrainingSlots"].update({"01": {"Id": 1}}),
            lambda p: p["User"]["TrainingSlots"]["1"].update(Id=2),
            lambda p: p["User"]["TrainingSlots"]["1"].update(Id=True),
            lambda p: p["User"]["TrainingSlots"].update({"2": None}),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject()

    def test_invalid_assignment_flags_and_cooldown_types_reject_without_writes(self):
        original = self.store.account.profile()
        for field, value in (
            ("CharacterId", True),
            ("CharacterId", -1),
            ("CharacterId", "1"),
            ("ItemId", 1.0),
            ("ItemId", None),
            ("ItemId", 0x80000000),
            ("IsEvolve", 1),
            ("IsMyth", None),
            ("IsEngraving", "true"),
            ("NextReactivateTime", True),
            ("NextReactivateTime", "invalid"),
            ("NextReactivateTime", "2026-11-20T12:00:00"),
        ):
            profile = copy.deepcopy(original)
            profile["User"]["TrainingSlots"]["1"][field] = value
            self.save(profile)
            self.reject()

    def test_reopening_repetition_and_response_mutation_cannot_change_saved_training_data(self):
        expected = self.assert_read()
        reply = self.call()
        reply["User"]["TrainingSlots"]["1"]["CharacterId"] = 99
        self.assertEqual(self.call(), expected)
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session()
        self.assertEqual(self.assert_read(), expected)

    def test_response_size_stays_independent_of_inventory_and_maximum_revision_can_be_read(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save(profile)
        before = len(json.dumps(self.assert_read()))
        profile["User"]["ItemStackables"] = [{"Id": i, "Amount": 3} for i in range(10000, 11000)]
        self.save(profile)
        self.assertEqual(len(json.dumps(self.assert_read())), before)

    def test_authentication_prologue_and_mutating_room_routes_remain_guarded(self):
        self.session.signed_in = False
        self.reject()
        self.open_session()
        for route in (
            "/training-room/join/v2",
            "/training-room/leave",
            "/training-room/unlock",
            "/training-room/reactivate",
            "/training-room/reactivate/v2",
        ):
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.call({}, route)
            self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.root).account
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.read(ROUTE)
            self.assertEqual(list(db.iterdump()), before)
            account.complete_prologue(
                "Initial",
                {
                    "IsMale": True,
                    "VoiceType": 0,
                    "Weapon1ItemId": 101,
                    "Weapon2ItemId": 102,
                    "BobLindaQuestGrade": 0,
                },
            )
            self.assertEqual(account.read(ROUTE)["User"]["TrainingSlots"], {})
