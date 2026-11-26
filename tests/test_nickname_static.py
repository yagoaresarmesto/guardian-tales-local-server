# SPDX-License-Identifier: Apache-2.0
"""The free nickname policy composes with mode overlays and refreshes client caches."""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales.account_costs_static import prepare
from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.raid_static import compress, decode, digest, records
from tests.test_snapshots import request


def static_body(cost=1200, checksum="original", revision=31, include_checksum=True):
    tables = {
        "constants": json.dumps(
            {"ChangeNickCost": cost, "ChangeGuildNameCost": 2000, "PlayCoopCoinReward": 0}
        ),
        "seasondate": '{"EventPeriod":[]}',
        "unchanged-bin": "YWJj",
    }
    if include_checksum:
        tables["__checksum__"] = checksum
    return compress(
        "".join(
            f"{name}\n{value}\n{revision}\n{digest(b'abc' if name.endswith('-bin') else value.encode())}\n"
            for name, value in tables.items()
        ).encode()
    )


class NicknameStaticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.source = self.root / "static_data_get.bin"
        self.original = static_body()
        self.source.write_bytes(self.original)
        (self.root / "static_data_check.bin").write_bytes(b'{"UpToDate":true}')
        self.db = sqlite3.connect(":memory:")
        self.session = BootstrapSession(GuestStore(self.db, self.root))
        self.session.signed_in = True

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def test_only_nickname_cost_and_record_checksums_change(self):
        body, checksum = prepare(self.original)
        before, after = records(decode(self.original))[1], records(decode(body))[1]
        for key in before.keys() - {"constants", "__checksum__"}:
            self.assertEqual(before[key], after[key])
        expected = json.loads(before["constants"][1])
        expected["ChangeNickCost"] = 0
        self.assertEqual(json.loads(after["constants"][1]), expected)
        self.assertEqual(after["constants"][2], 32)
        self.assertEqual(after["__checksum__"][1], checksum)
        self.assertNotEqual(checksum, "original")
        self.assertEqual(prepare(self.original), (body, checksum))
        self.assertEqual(prepare(body), (body, checksum))
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_bootstrap_get_and_check_share_stable_checksum_without_account_writes(self):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.db.execute("PRAGMA query_only=ON")
        body = self.session.handle(request("/static-data/get", {"ClientVersions": {}})).body
        checksum = records(decode(body))[1]["__checksum__"][1]
        for value in (None, {}, {"Checksum": "original"}, {"Checksum": checksum}):
            reply = self.session.handle(request("/static-data/check-update", value))
            self.assertEqual(
                json.loads(reply.body),
                {
                    "UpToDate": value == {"Checksum": checksum},
                    "Checksum": checksum,
                    "QuitGameWhenStaticDataUpdateNeeded": False,
                },
            )
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_composes_after_each_effective_mode_parent_without_losing_parent_content(self):
        parent_names = ("guild_war", "punchking", "raid")
        for index, mode in enumerate(parent_names):
            parent = static_body(checksum=mode, revision=100 + index)
            patches = [
                patch(
                    "guardian_tales.bootstrap." + key + "_bootstrap_override",
                    return_value=parent if key == mode else None,
                )
                for key in parent_names
            ]
            with patches[0], patches[1], patches[2]:
                body = self.session.handle(request("/static-data/get", {})).body
                actual = records(decode(body))[1]
                self.assertEqual(json.loads(actual["constants"][1])["ChangeNickCost"], 0)
                expected = records(decode(parent))[1]
                self.assertEqual(actual["seasondate"], expected["seasondate"])
                self.assertEqual(actual["unchanged-bin"], expected["unchanged-bin"])
                self.assertEqual(json.loads(actual["constants"][1])["PlayCoopCoinReward"], 0)
                reply = self.session.handle(
                    request("/static-data/check-update", {"Checksum": actual["__checksum__"][1]})
                )
                self.assertTrue(json.loads(reply.body)["UpToDate"])

    def test_parent_refresh_changes_checksum_and_retains_its_new_revision(self):
        first = prepare(self.original)
        second = prepare(static_body(checksum="new-parent", revision=211))
        self.assertNotEqual(first[1], second[1])
        self.assertEqual(records(decode(second[0]))[1]["constants"][2], 212)

    def test_zero_cost_is_already_prepared(self):
        body = static_body(cost=0)
        self.assertEqual(prepare(body), (body, "original"))

    def test_invalid_cost_missing_checksum_and_revision_overflow_reject(self):
        for cost in (None, True, -1, 1.5, "1200", 0x80000000):
            with self.subTest(cost=cost), self.assertRaises(ValueError):
                prepare(static_body(cost=cost))
        for body in (static_body(include_checksum=False), static_body(revision=0x7FFFFFFF)):
            with self.assertRaises(ValueError):
                prepare(body)

    def test_synthetic_tables_without_the_constant_retain_existing_parent_behavior(self):
        for body in (
            compress(b"[]"),
            compress(b"constants\n{}\n1\n" + digest(b"{}").encode() + b"\n"),
            compress(b"other\n{}\n1\n" + digest(b"{}").encode() + b"\n"),
        ):
            self.assertIsNone(prepare(body))
            self.source.write_bytes(body)
            self.assertEqual(self.session.handle(request("/static-data/get", {})).body, body)
            self.assertEqual(
                self.session.handle(request("/static-data/check-update", {})).body,
                b'{"UpToDate":true}',
            )
