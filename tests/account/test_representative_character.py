# SPDX-License-Identifier: Apache-2.0
"""Owned portrait selection persists without losing inventory or newer choices."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.accounts.representative_character import ROUTE
from guardian_tales.heroes.characters import new_character
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.settlement.village import MAX_REVISION
from tests.account.test_snapshots import synthetic_snapshot


class RepresentativeCharacterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.store = GuestStore(self.db)
        snapshot = synthetic_snapshot()
        user = snapshot["profile"]["User"]
        user["Characters"].extend(
            new_character(i, spec) for i, spec in ((7, 70007), (19, 70019), (0x7FFFFFFF, 70031))
        )
        user["CharacterIdCounter"] = 0x7FFFFFFF
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

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            route="/auth/sign-in",
            sequence=1,
        )

    def call(self, body, route=ROUTE, sequence=821):
        packet = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        reply = self.session.handle(packet)
        self.assertEqual(reply.sequence_id, sequence)
        return read_json_body(parse_packet(encode_packet(reply)))

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def response(self, profile):
        user = profile["User"]
        return {"User": {k: user[k] for k in ("Id", "Cas", "RepresentativeCharacterId")}}

    def reject_without_writes(self, body, sequence=821):
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def unrelated_rows(self):
        return [
            row
            for row in self.db.iterdump()
            if not row.startswith('INSERT INTO "local_account"')
            and not row.startswith('INSERT INTO "representative_character_requests"')
        ]

    def test_each_owned_inventory_id_changes_only_portrait_and_revision(self):
        source = self.source.read_bytes()
        other = self.unrelated_rows()
        for sequence, character in enumerate((7, 19, 0x7FFFFFFF, 1), 821):
            expected = copy.deepcopy(self.store.account.profile())
            expected["User"]["RepresentativeCharacterId"] = character
            expected["User"]["Cas"] += 1
            reply = self.call({"CharacterId": character}, sequence=sequence)
            self.assertEqual(reply, self.response(expected))
            self.assertLess(len(json.dumps(reply).encode()), 256)
            self.assertEqual(self.store.account.profile(), expected)
            card = self.call({"UserId": 9400}, route="/user/get-user-profile-card")
            self.assertEqual(card["UserProfileCard"]["User"], expected["User"])
            self.assertEqual(self.unrelated_rows(), other)
            self.assertEqual(self.source.read_bytes(), source)

    def test_large_arbitrary_roster_requires_no_catalog_or_fixed_hero_list(self):
        profile = self.store.account.profile()
        ids = [101 + 13 * i for i in range(200)]
        profile["User"]["Characters"].extend(new_character(i, 40000 + i) for i in ids)
        self.save(profile)
        for sequence, character in enumerate((ids[0], ids[63], ids[127], ids[-1]), 831):
            reply = self.call({"CharacterId": character}, sequence=sequence)
            self.assertEqual(reply["User"]["RepresentativeCharacterId"], character)
            self.assertLess(len(json.dumps(reply).encode()), 256)
        self.assertEqual(
            self.store.account.profile()["User"]["Characters"], profile["User"]["Characters"]
        )

    def test_choice_survives_restart_fetch_and_delayed_retry_without_losing_newer_edits(self):
        self.call({"CharacterId": 7})
        self.call({"CharacterId": 19}, sequence=822)
        profile = self.store.account.profile()
        profile["User"]["Characters"][1]["Experience"] += 37
        self.save(profile)
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session(reconnect=True)
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        self.assertEqual(self.call({"CharacterId": 7}), self.response(profile))
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(self.call(None, route="/auth/fetch-account"), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(profile["User"]["RepresentativeCharacterId"], 19)

    def test_reused_request_with_another_character_rejects_without_writes(self):
        self.call({"CharacterId": 7})
        self.reject_without_writes({"CharacterId": 19})

    def test_fresh_signin_allows_a_new_selection_with_reused_sequence(self):
        self.call({"CharacterId": 7})
        self.open_session(reconnect=False)
        reply = self.call({"CharacterId": 19})
        self.assertEqual(reply["User"]["RepresentativeCharacterId"], 19)

    def test_unchanged_choice_is_idempotent_even_at_maximum_revision(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save(profile)
        changes = self.db.total_changes
        self.assertEqual(self.call({"CharacterId": 1}), self.response(profile))
        self.assertEqual(self.db.total_changes, changes + 1)
        changes = self.db.total_changes
        self.assertEqual(self.call({"CharacterId": 1}), self.response(profile))
        self.assertEqual(self.db.total_changes, changes)
        self.reject_without_writes({"CharacterId": 7}, sequence=822)

    def test_malformed_unknown_and_spec_ids_cannot_change_the_account(self):
        for body in (
            None,
            {},
            [],
            True,
            {"CharacterId": True},
            {"CharacterId": 7.0},
            {"CharacterId": "7"},
            {"CharacterId": None},
            {"CharacterId": []},
            {"CharacterId": 0},
            {"CharacterId": -1},
            {"CharacterId": 0x80000000},
            {"CharacterId": 2},
            {"CharacterId": 70007},
            {"CharacterId": 999},
            {"characterId": 7},
            {"CharacterId": 7, "UserId": 9400},
        ):
            with self.subTest(body=body):
                self.reject_without_writes(body)
        for identity in (None, "", "x" * 201, True):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.select_representative_character({"CharacterId": 7}, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_saved_roster_revision_owner_and_selection_are_not_repaired(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Id=True),
            lambda p: p["User"].update(Cas=True),
            lambda p: p["User"].update(Cas=-1),
            lambda p: p["User"].update(Cas=MAX_REVISION + 1),
            lambda p: p["User"].update(Characters=None),
            lambda p: p["User"].update(Characters=[]),
            lambda p: p["User"]["Characters"].append(copy.deepcopy(p["User"]["Characters"][0])),
            lambda p: p["User"]["Characters"][0].update(Id=True),
            lambda p: p["User"].update(RepresentativeCharacterId=True),
            lambda p: p["User"].update(RepresentativeCharacterId="1"),
            lambda p: p["User"].update(RepresentativeCharacterId=999),
            lambda p: p["User"].pop("RepresentativeCharacterId"),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject_without_writes({"CharacterId": 7})

    def test_null_or_default_saved_portrait_can_select_an_owned_character(self):
        for sequence, current in enumerate((None, 0), 841):
            profile = self.store.account.profile()
            profile["User"]["RepresentativeCharacterId"] = current
            self.save(profile)
            reply = self.call({"CharacterId": 7}, sequence=sequence)
            self.assertEqual(reply["User"]["RepresentativeCharacterId"], 7)

    def test_profile_and_receipt_failures_roll_back_the_entire_selection(self):
        for table, action in (
            ("local_account", "UPDATE"),
            ("representative_character_requests", "INSERT"),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_portrait BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.store.account.select_representative_character({"CharacterId": 7}, "rollback")
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_portrait")
            self.db.commit()

    def test_existing_import_gets_receipt_storage_without_reimporting_or_rewriting_profile(self):
        original = self.store.account.profile()
        reads = self.db.execute("SELECT * FROM imported_account").fetchall()
        self.db.execute("DROP TABLE representative_character_requests")
        self.db.commit()
        self.open_session(reconnect=True)
        self.assertEqual(self.store.account.profile(), original)
        self.assertEqual(self.db.execute("SELECT * FROM imported_account").fetchall(), reads)
        self.assertEqual(self.call({"CharacterId": 7})["User"]["RepresentativeCharacterId"], 7)

    def test_authentication_and_completed_fresh_prologue_are_required(self):
        unauthenticated = BootstrapSession(self.store)
        packet = parse_packet(
            encode_packet(Packet(0, b'{"CharacterId":7}', body_type=1, api=ROUTE, sequence_id=821))
        )
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            unauthenticated.handle(packet)
        self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db).account
            original = account.profile()
            with self.assertRaises(ValueError):
                account.select_representative_character({"CharacterId": 1}, "unfinished")
            self.assertEqual(account.profile(), original)
            account.complete_prologue(
                "Synthetic",
                {
                    "IsMale": True,
                    "VoiceType": 0,
                    "Weapon1ItemId": 101,
                    "Weapon2ItemId": 102,
                    "BobLindaQuestGrade": 0,
                },
            )
            profile = account.profile()
            profile["User"]["Characters"].append(new_character(23, 1023))
            with db:
                db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            result = account.select_representative_character({"CharacterId": 23}, "fresh")
            self.assertEqual(result["User"]["RepresentativeCharacterId"], 23)
