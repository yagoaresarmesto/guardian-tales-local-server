# SPDX-License-Identifier: Apache-2.0
"""Nickname changes preserve currencies, progress, guild identity and retry order."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.account_name import ROUTE, valid_name
from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.village import MAX_REVISION
from tests.test_snapshots import synthetic_snapshot


class AccountNameTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.store = GuestStore(self.db)
        snapshot = synthetic_snapshot()
        self.source = self.root / "original.json"
        self.source.write_text(json.dumps(snapshot), encoding="utf-8")
        self.original = self.source.read_bytes()
        profile = snapshot["profile"]
        profile["GuildMember"] = {
            "UserId": profile["User"]["Id"],
            "Cas": 31,
            "Name": profile["User"]["Name"],
            "GuildId": 71,
            "Achievement": {"Id": 1, "Points": 23},
            "AttendanceCount": 19,
        }
        with self.db:
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        self.save(profile)
        self.open_session()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            route="/auth/sign-in",
            sequence=1,
        )

    def call(self, body, route=ROUTE, sequence=931):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        reply = self.session.handle(request)
        self.assertEqual(reply.sequence_id, sequence)
        return read_json_body(parse_packet(encode_packet(reply)))

    def reject(self, body, sequence=931):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def unrelated(self):
        return [
            r
            for r in self.db.iterdump()
            if not r.startswith(
                ('INSERT INTO "local_account"', 'INSERT INTO "account_name_requests"')
            )
        ]

    def test_changes_only_names_and_revisions_without_charging_or_word_filtering(self):
        other = self.unrelated()
        for sequence, name in enumerate(
            ("Renamed", "admin", "GM", "\u65e5\u672c\u8a9e", "\U0001f600" * 5), 931
        ):
            expected = self.store.account.profile()
            expected["User"].update(Name=name, Cas=expected["User"]["Cas"] + 1)
            expected["GuildMember"].update(Name=name, Cas=expected["GuildMember"]["Cas"] + 1)
            reply = self.call({"Name": name}, sequence=sequence)
            self.assertEqual(reply["User"], {k: expected["User"][k] for k in ("Id", "Cas", "Name")})
            self.assertEqual(reply["GuildMember"], expected["GuildMember"])
            self.assertEqual(self.store.account.profile(), expected)
            self.assertEqual(self.unrelated(), other)
            self.assertEqual(self.source.read_bytes(), self.original)
        card = self.call({"UserId": expected["User"]["Id"]}, route="/user/get-user-profile-card")
        self.assertEqual(card["UserProfileCard"]["User"]["Name"], name)
        guild = self.call(None, route="/guild/get-my-guild")
        self.assertEqual(guild["GuildMembers"][0]["Name"], name)

    def test_rename_needs_no_free_or_paid_gems_tickets_or_external_catalog(self):
        profile = self.store.account.profile()
        for asset in profile["User"]["Assets"]:
            asset["Amount"] = 0
        profile["GuildMember"] = None
        self.save(profile)
        expected = copy.deepcopy(profile)
        expected["User"].update(Name="NoGems", Cas=profile["User"]["Cas"] + 1)
        reply = self.call({"Name": "NoGems"})
        self.assertEqual(set(reply), {"User"})
        self.assertEqual(self.store.account.profile(), expected)

    def test_restart_and_delayed_retry_keep_latest_name_and_other_newer_progress(self):
        self.call({"Name": "Earlier"})
        self.call({"Name": "Latest"}, sequence=932)
        expected = self.store.account.profile()
        expected["User"]["Characters"][0]["Experience"] += 13
        self.save(expected)
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session(reconnect=True)
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"Name": "Earlier"})["User"]["Name"], "Latest")
        self.assertEqual(self.call(None, route="/auth/fetch-account"), expected)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_request_identity_reuse_rejects_and_fresh_signin_gets_new_identity(self):
        self.call({"Name": "Earlier"})
        self.reject({"Name": "Latest"})
        self.open_session(reconnect=False)
        self.assertEqual(self.call({"Name": "Latest"})["User"]["Name"], "Latest")

    def test_same_name_at_maximum_revision_records_only_one_receipt(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = profile["GuildMember"]["Cas"] = MAX_REVISION
        self.save(profile)
        changes = self.db.total_changes
        self.call({"Name": profile["User"]["Name"]})
        self.assertEqual(self.db.total_changes, changes + 1)
        self.call({"Name": profile["User"]["Name"]})
        self.assertEqual(self.db.total_changes, changes + 1)
        self.assertEqual(self.store.account.profile(), profile)
        self.reject({"Name": "Overflow"}, sequence=932)

    def test_invalid_names_and_extra_fields_never_write(self):
        for value in (
            None,
            True,
            7,
            1.5,
            [],
            {},
            "",
            "A",
            "A" * 11,
            "\nHi",
            "A\x7f",
            "\ud800A",
            "\U0001f600" * 6,
        ):
            with self.subTest(value=repr(value)):
                self.reject({"Name": value})
        for body in (
            None,
            {},
            [],
            True,
            {"name": "Other"},
            {"Name": "Other", "Cost": 0},
            {"Name": "Other", "UserId": 1},
        ):
            self.reject(body)
        for identity in (None, True, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.change_name({"Name": "Other"}, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_utf16_boundaries_match_signup_validator_without_lexical_rules(self):
        for name in ("AB", "A" * 10, "\U0001f600", "\U0001f600" * 5, "A B", "admin"):
            self.assertTrue(valid_name(name), repr(name))
        for name in ("A", "A" * 11, "\U0001f600" * 5 + "A", "\udfffA", "A\tB"):
            self.assertFalse(valid_name(name), repr(name))

    def test_invalid_saved_owner_revision_or_membership_does_not_get_repaired(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Id=True),
            lambda p: p["User"].update(Cas=-1),
            lambda p: p["User"].update(Cas=True),
            lambda p: p["User"].update(Cas=MAX_REVISION + 1),
            lambda p: p["User"].update(Name=None),
            lambda p: p.update(GuildMember=[]),
            lambda p: p["GuildMember"].update(UserId=1),
            lambda p: p["GuildMember"].update(Cas=True),
            lambda p: p["GuildMember"].update(Name=None),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject({"Name": "Other"})

    def test_guild_revision_overflow_rejects_entire_rename(self):
        profile = self.store.account.profile()
        profile["GuildMember"]["Cas"] = MAX_REVISION
        self.save(profile)
        self.reject({"Name": "Other"})

    def test_receipt_failure_rolls_back_both_names_and_revisions(self):
        self.db.execute(
            "CREATE TEMP TRIGGER refuse_rename BEFORE INSERT ON account_name_requests BEGIN SELECT RAISE(ABORT,'synthetic refusal'); END"
        )
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call({"Name": "Other"})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_signin_is_required(self):
        self.session.signed_in = False
        self.reject({"Name": "Other"})

    def test_fresh_completed_account_can_rename_but_unfinished_prologue_cannot(self):
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db).account
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.change_name({"Name": "Other"}, "unfinished")
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
            self.assertEqual(
                account.change_name({"Name": "Other"}, "fresh")["User"]["Name"], "Other"
            )
