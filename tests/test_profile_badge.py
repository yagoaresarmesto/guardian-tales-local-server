# SPDX-License-Identifier: Apache-2.0
"""Client-managed badges accept only owned items and never rewrite account state."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.portrait_frame import frame_specs
from guardian_tales.profile_badge import ROUTE
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.raid_static import compress, digest
from guardian_tales.snapshots import ACCOUNT_READS, IMPORTED_MUTATIONS
from guardian_tales.village import MAX_REVISION
from tests.test_snapshots import synthetic_snapshot


class ProfileBadgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.definitions = [
            {"Id": spec, "Type": kind}
            for spec, kind in (
                (230001, "profilebadge"),
                (230004, "profilebadge"),
                (0x7FFFFFFF, "profilebadge"),
                (220001, "portraitframe"),
                (70023, "costume"),
                (230099, "profilebadge"),
            )
        ]
        self.catalog(self.definitions)
        self.store = GuestStore(self.db, self.root)
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["ItemMiscs"] = [
            {"Id": i, "ItemId": spec, "Amount": amount, "SyntheticPreserved": [i]}
            for i, spec, amount in (
                (17, 230001, 1),
                (29, 230004, 1),
                (19, 220001, 1),
                (23, 70023, 1),
                (31, 230099, 0),
                (0x7FFFFFFE, 0x7FFFFFFF, 1),
            )
        ]
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

    def catalog(self, items, name="items"):
        content = json.dumps(items, separators=(",", ":"))
        raw = f"{name}\n{content}\n1\n{digest(content.encode())}\n".encode()
        (self.root / "static_data_get.bin").write_bytes(compress(raw))

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.login(self.session, reconnect)

    def login(self, session, reconnect=False):
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            route="/auth/sign-in",
            sequence=1,
            session=session,
        )

    def call(self, body, route=ROUTE, sequence=901, session=None):
        packet = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        reply = (session or self.session).handle(packet)
        self.assertEqual(reply.sequence_id, sequence)
        return read_json_body(parse_packet(encode_packet(reply)))

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def reject_without_writes(self, body):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_all_owned_badges_and_removal_acknowledge_with_sqlite_writes_disabled(self):
        self.assertIn(ROUTE, ACCOUNT_READS)
        self.assertNotIn(ROUTE, IMPORTED_MUTATIONS)
        source = self.source.read_bytes()
        before, changes = list(self.db.iterdump()), self.db.total_changes
        profile = self.store.account.profile()
        self.db.execute("PRAGMA query_only=ON")
        for badge in (17, 29, 0x7FFFFFFE, None, 17, None):
            self.assertEqual(self.call({"BadgeId": badge}), {})
            self.assertEqual(self.store.account.profile(), profile)
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.db.total_changes, changes)
            self.assertEqual(self.source.read_bytes(), source)

    def test_malformed_design_unowned_wrong_type_and_empty_stack_ids_reject(self):
        self.db.execute("PRAGMA query_only=ON")
        for body in (
            None,
            [],
            {},
            True,
            {"BadgeId": True},
            {"BadgeId": 17.0},
            {"BadgeId": "17"},
            {"BadgeId": []},
            {"BadgeId": 0},
            {"BadgeId": -1},
            {"BadgeId": 0x80000000},
            {"BadgeId": 230001},
            {"BadgeId": 19},
            {"BadgeId": 23},
            {"BadgeId": 31},
            {"BadgeId": 999},
            {"BadgeId": 17, "UserId": 9400},
            {"badgeId": 17},
        ):
            with self.subTest(body=body):
                self.reject_without_writes(body)

    def test_invalid_saved_inventory_and_owner_do_not_receive_silent_repairs(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Id=True),
            lambda p: p["User"].update(ItemMiscs=None),
            lambda p: p["User"]["ItemMiscs"].append(copy.deepcopy(p["User"]["ItemMiscs"][0])),
            lambda p: p["User"]["ItemMiscs"][0].update(Id=True),
            lambda p: p["User"]["ItemMiscs"][0].update(ItemId="230001"),
            lambda p: p["User"]["ItemMiscs"][0].update(Amount=-1),
            lambda p: p["User"]["ItemMiscs"][0].pop("Amount"),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject_without_writes({"BadgeId": 17})

    def test_catalog_changes_apply_and_frame_and_badge_caches_stay_distinct(self):
        body = (self.root / "static_data_get.bin").read_bytes()
        self.assertEqual(frame_specs(body), frozenset({220001}))
        self.assertEqual(self.call({"BadgeId": 17}), {})
        profile = self.store.account.profile()
        profile["User"]["ItemMiscs"].append({"Id": 101, "ItemId": 123456789, "Amount": 1})
        self.save(profile)
        self.reject_without_writes({"BadgeId": 101})
        self.catalog(self.definitions + [{"Id": 123456789, "Type": "profilebadge"}])
        self.assertEqual(self.call({"BadgeId": 101}), {})
        self.catalog(self.definitions + [{"Id": 123456789, "Type": "portraitframe"}])
        self.reject_without_writes({"BadgeId": 101})

    def test_missing_corrupt_or_ambiguous_external_definitions_reject_without_writes(self):
        path = self.root / "static_data_get.bin"
        path.unlink()
        self.reject_without_writes({"BadgeId": 17})
        path.write_bytes(b"invalid")
        self.reject_without_writes({"BadgeId": 17})
        self.catalog([], name="other")
        self.reject_without_writes({"BadgeId": 17})
        for items in (
            {},
            [],
            [None],
            [{"Id": True, "Type": "profilebadge"}],
            self.definitions + [self.definitions[0]],
        ):
            self.catalog(items)
            self.reject_without_writes({"BadgeId": 17})

    def test_reopening_and_old_acknowledgements_preserve_all_later_profile_edits(self):
        self.call({"BadgeId": 17})
        self.call({"BadgeId": 29}, sequence=902)
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["Experience"] += 37
        profile["User"]["FrameId"] = 220001
        self.save(profile)
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session(reconnect=True)
        self.db.execute("PRAGMA query_only=ON")
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"BadgeId": 17}), {})
        self.assertEqual(self.call(None, route="/auth/fetch-account"), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_badge_selection_spends_nothing_and_needs_no_available_user_revision(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        self.save(profile)
        before = list(self.db.iterdump())
        self.assertEqual(self.call({"BadgeId": 17}), {})
        self.assertEqual(self.call({"BadgeId": None}), {})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_authentication_and_fresh_prologue_are_required(self):
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call({"BadgeId": 17}, session=BootstrapSession(self.store))
        self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            store = GuestStore(db, self.root)
            session = BootstrapSession(store)
            self.login(session)
            before = list(db.iterdump())
            with self.assertRaises(PacketError):
                self.call({"BadgeId": None}, session=session)
            self.assertEqual(list(db.iterdump()), before)

    def test_completed_fresh_account_uses_owned_badges_and_can_clear_empty_inventory(self):
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
            session = BootstrapSession(store)
            self.login(session)
            self.assertEqual(self.call({"BadgeId": None}, session=session), {})
            profile = store.account.profile()
            profile["User"]["ItemMiscs"].append({"Id": 17, "ItemId": 230001, "Amount": 1})
            with db:
                db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            db.execute("PRAGMA query_only=ON")
            before, changes = list(db.iterdump()), db.total_changes
            self.assertEqual(self.call({"BadgeId": 17}, session=session), {})
            self.assertEqual(list(db.iterdump()), before)
            self.assertEqual(db.total_changes, changes)
