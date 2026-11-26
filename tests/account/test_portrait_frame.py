# SPDX-License-Identifier: Apache-2.0
"""Frame inventory IDs resolve to owned designs without losing newer progress."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.accounts.portrait_frame import ROUTE
from guardian_tales.modes.guild.raid_static import compress, digest
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet
from guardian_tales.settlement.village import MAX_REVISION
from tests.account.test_snapshots import synthetic_snapshot


class PortraitFrameTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.path = self.root / "server.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.definitions = [
            {"Id": spec, "Type": kind}
            for spec, kind in (
                (220004, "portraitframe"),
                (220001, "portraitframe"),
                (0x7FFFFFFF, "portraitframe"),
                (70023, "costume"),
                (220099, "portraitframe"),
            )
        ]
        self.catalog(self.definitions)
        self.store = GuestStore(self.db, self.root)
        snapshot = synthetic_snapshot()
        user = snapshot["profile"]["User"]
        user["FrameId"] = 220004
        user["ItemMiscs"] = [
            {"Id": i, "ItemId": spec, "Amount": amount, "SyntheticPreserved": [i]}
            for i, spec, amount in (
                (7, 220004, 1),
                (19, 220001, 1),
                (23, 70023, 1),
                (31, 220099, 0),
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
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            route="/auth/sign-in",
            sequence=1,
        )

    def call(self, body, route=ROUTE, sequence=861):
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
        return {"User": {k: profile["User"][k] for k in ("Id", "Cas", "FrameId")}}

    def reject_without_writes(self, body, sequence=861):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_owned_inventory_ids_resolve_to_designs_and_null_removes_only_the_frame(self):
        source = self.source.read_bytes()
        other = [
            row for row in self.db.iterdump() if not row.startswith('INSERT INTO "local_account"')
        ]
        for sequence, (inventory, design) in enumerate(
            ((19, 220001), (0x7FFFFFFE, 0x7FFFFFFF), (7, 220004), (None, None)), 861
        ):
            expected = copy.deepcopy(self.store.account.profile())
            expected["User"].update(FrameId=design, Cas=expected["User"]["Cas"] + 1)
            result = self.call({"FrameId": inventory}, sequence=sequence)
            self.assertEqual(result, self.response(expected))
            self.assertLess(len(json.dumps(result).encode()), 256)
            self.assertEqual(self.store.account.profile(), expected)
            card = self.call({"UserId": 9400}, route="/user/get-user-profile-card")
            self.assertEqual(card["UserProfileCard"]["User"], expected["User"])
            self.assertEqual(
                [
                    row
                    for row in self.db.iterdump()
                    if not row.startswith('INSERT INTO "local_account"')
                    and not row.startswith('INSERT INTO "portrait_frame_requests"')
                ],
                other,
            )
            self.assertEqual(self.source.read_bytes(), source)

    def test_malformed_unowned_wrong_kind_empty_stack_and_design_ids_are_rejected(self):
        for body in (
            None,
            [],
            {},
            True,
            {"FrameId": True},
            {"FrameId": 19.0},
            {"FrameId": "19"},
            {"FrameId": []},
            {"FrameId": 0},
            {"FrameId": -1},
            {"FrameId": 0x80000000},
            {"FrameId": 220001},
            {"FrameId": 23},
            {"FrameId": 31},
            {"FrameId": 999},
            {"FrameId": 19, "UserId": 9400},
            {"frameId": 19},
        ):
            with self.subTest(body=body):
                self.reject_without_writes(body)
        for identity in (None, "", "x" * 201, True):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.select_portrait_frame({"FrameId": 19}, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_restart_and_delayed_retry_preserve_current_frame_and_later_inventory_edits(self):
        self.call({"FrameId": 19})
        self.call({"FrameId": None}, sequence=862)
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["Experience"] += 37
        profile["User"]["ItemMiscs"] = [i for i in profile["User"]["ItemMiscs"] if i["Id"] != 19]
        self.save(profile)
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.open_session(reconnect=True)
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"FrameId": 19}), self.response(profile))
        self.assertEqual(self.call(None, route="/auth/fetch-account"), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_request_conflict_is_rejected_and_fresh_signin_rotates_the_identity(self):
        self.call({"FrameId": 19})
        self.reject_without_writes({"FrameId": None})
        self.open_session(reconnect=False)
        self.assertIsNone(self.call({"FrameId": None})["User"]["FrameId"])

    def test_unchanged_design_and_null_do_not_increment_a_maximum_revision(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        profile["User"]["ItemMiscs"].append({"Id": 43, "ItemId": 220004, "Amount": 1})
        self.save(profile)
        changes = self.db.total_changes
        self.assertEqual(self.call({"FrameId": 43}), self.response(profile))
        self.assertEqual(self.db.total_changes, changes + 1)
        self.assertEqual(self.call({"FrameId": 43}), self.response(profile))
        self.assertEqual(self.db.total_changes, changes + 1)
        self.reject_without_writes({"FrameId": None}, sequence=862)
        profile["User"]["FrameId"] = None
        self.save(profile)
        self.assertEqual(self.call({"FrameId": None}, sequence=863), self.response(profile))

    def test_invalid_saved_inventory_owner_revision_and_frame_are_not_repaired(self):
        original = self.store.account.profile()
        for mutate in (
            lambda p: p["User"].update(Id=True),
            lambda p: p["User"].update(Cas=True),
            lambda p: p["User"].update(Cas=-1),
            lambda p: p["User"].update(Cas=MAX_REVISION + 1),
            lambda p: p["User"].update(ItemMiscs=None),
            lambda p: p["User"]["ItemMiscs"].append(copy.deepcopy(p["User"]["ItemMiscs"][0])),
            lambda p: p["User"]["ItemMiscs"][0].update(Id=True),
            lambda p: p["User"]["ItemMiscs"][0].update(ItemId="220004"),
            lambda p: p["User"]["ItemMiscs"][0].update(Amount=-1),
            lambda p: p["User"].update(FrameId=True),
            lambda p: p["User"].update(FrameId=7),
            lambda p: p["User"].update(FrameId=220099),
            lambda p: p["User"].pop("FrameId"),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            self.save(profile)
            self.reject_without_writes({"FrameId": 19})

    def test_default_and_null_saved_frames_can_select_any_owned_frame(self):
        for sequence, current in enumerate((None, 0), 871):
            profile = self.store.account.profile()
            profile["User"]["FrameId"] = current
            self.save(profile)
            self.assertEqual(
                self.call({"FrameId": 19}, sequence=sequence)["User"]["FrameId"], 220001
            )

    def test_catalog_is_dynamic_and_refreshes_when_external_content_changes(self):
        profile = self.store.account.profile()
        profile["User"]["ItemMiscs"].append({"Id": 101, "ItemId": 123456789, "Amount": 1})
        self.save(profile)
        self.reject_without_writes({"FrameId": 101})
        self.catalog(self.definitions + [{"Id": 123456789, "Type": "portraitframe"}])
        self.assertEqual(self.call({"FrameId": 101})["User"]["FrameId"], 123456789)
        self.catalog(self.definitions + [{"Id": 123456789, "Type": "costume"}])
        self.reject_without_writes({"FrameId": 19}, sequence=862)

    def test_missing_corrupt_ambiguous_and_wrong_shape_definitions_fail_without_writes(self):
        path = self.root / "static_data_get.bin"
        path.unlink()
        self.reject_without_writes({"FrameId": 19})
        path.write_bytes(b"invalid")
        self.reject_without_writes({"FrameId": 19})
        self.catalog([], name="other")
        self.reject_without_writes({"FrameId": 19})
        for items in (
            {},
            [],
            [None],
            [{"Id": True, "Type": "portraitframe"}],
            [{"Id": 220004}],
            self.definitions + [self.definitions[0]],
        ):
            self.catalog(items)
            self.reject_without_writes({"FrameId": 19})

    def test_profile_and_receipt_failures_roll_back_together(self):
        for table, action in (("local_account", "UPDATE"), ("portrait_frame_requests", "INSERT")):
            self.db.execute(
                f"CREATE TRIGGER reject_frame BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            before = list(self.db.iterdump())
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.store.account.select_portrait_frame({"FrameId": 19}, "rollback")
            self.assertEqual(list(self.db.iterdump()), before)
            self.db.execute("DROP TRIGGER reject_frame")
            self.db.commit()

    def test_existing_import_adds_receipts_without_reimporting_or_rewriting_profile(self):
        original = self.store.account.profile()
        reads = self.db.execute("SELECT * FROM imported_account").fetchall()
        self.db.execute("DROP TABLE portrait_frame_requests")
        self.db.commit()
        self.open_session(reconnect=True)
        self.assertEqual(self.store.account.profile(), original)
        self.assertEqual(self.db.execute("SELECT * FROM imported_account").fetchall(), reads)
        self.assertEqual(self.call({"FrameId": 19})["User"]["FrameId"], 220001)

    def test_authentication_and_completed_fresh_prologue_are_required(self):
        packet = parse_packet(
            encode_packet(Packet(0, b'{"FrameId":19}', body_type=1, api=ROUTE, sequence_id=861))
        )
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            BootstrapSession(self.store).handle(packet)
        self.assertEqual(list(self.db.iterdump()), before)
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.root).account
            original = account.profile()
            with self.assertRaises(ValueError):
                account.select_portrait_frame({"FrameId": None}, "unfinished")
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
            profile["User"]["ItemMiscs"].append({"Id": 19, "ItemId": 220001, "Amount": 1})
            with db:
                db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            self.assertEqual(
                account.select_portrait_frame({"FrameId": 19}, "fresh")["User"]["FrameId"], 220001
            )
