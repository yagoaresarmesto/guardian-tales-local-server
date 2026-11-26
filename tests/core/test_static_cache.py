# SPDX-License-Identifier: Apache-2.0
"""Persisted static overlays preserve native get/check responses across restarts."""

import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from guardian_tales.accounts import account_costs_static
from guardian_tales.content import static_cache
from guardian_tales.content.static_cache import StaticCache, prepare_static
from guardian_tales.modes.expedition import expedition
from guardian_tales.modes.guild.raid_static import compress, decode, digest, records
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore
from tests.account.test_snapshots import request


class StaticCacheTests(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP")))
        self.root = Path(temp)
        self.cache = self.root / "cache"
        self.calls = 0

        def transform(source, generation=1, *, old=False):
            self.calls += 1
            data = source + json.dumps([generation, old]).encode()
            return compress(data), digest(data)

        self.transform = transform

    def prepare(self, *args, **kwargs):
        return StaticCache(self.cache).prepare(self.transform, *args, **kwargs)

    def test_restart_reuses_exact_input_and_rebuilds_for_each_changed_dependency(self):
        previous = None
        for count, (source, generation, old) in enumerate(
            [(b"base", 1, False), (b"base", 2, False), (b"base", 2, True), (b"next", 2, True)], 1
        ):
            with self.subTest(source=source, generation=generation, old=old):
                result = self.prepare(source, generation, old=old)
                self.assertNotEqual(result, previous)
                self.assertEqual(self.prepare(source, generation, old=old), result)
                self.assertEqual(self.calls, count)
                previous = result

    def test_truncated_or_corrupt_entries_are_rebuilt_and_then_reused(self):
        expected = self.prepare(b"base")
        entry = next(self.cache.rglob("*.bin"))
        original = entry.read_bytes()
        altered_checksum = digest(b"wrong checksum").encode()
        for corrupt in (
            b"",
            original[:-1],
            bytes([original[0] ^ 1]) + original[1:],
            original.replace(expected[1].encode(), altered_checksum),
            original[:-1] + bytes([original[-1] ^ 1]),
        ):
            with self.subTest(size=len(corrupt)):
                entry.write_bytes(corrupt)
                calls = self.calls
                self.assertEqual(self.prepare(b"base"), expected)
                self.assertEqual(self.prepare(b"base"), expected)
                self.assertEqual(self.calls, calls + 1)

    def test_relabeling_an_old_body_with_a_new_key_forces_a_rebuild(self):
        previous = self.prepare(b"old")
        entry = next(self.cache.rglob("*.bin"))
        old_bytes = entry.read_bytes()
        latest = self.prepare(b"new")
        new_bytes = entry.read_bytes()
        self.assertNotEqual(previous, latest)
        # The first SHA-256 digest identifies this input. The next authenticates
        # it together with the native checksum and the prepared catalog bytes.
        entry.write_bytes(new_bytes[:32] + old_bytes[32:])
        self.assertEqual(self.prepare(b"new"), latest)
        self.assertEqual(self.calls, 3)

    def test_opaque_native_checksum_survives_an_optional_cache(self):
        def passthrough(source):
            return source, "local-レガシー"

        for _ in range(2):
            self.assertEqual(
                StaticCache(self.cache).prepare(passthrough, b"original body"),
                (b"original body", "local-レガシー"),
            )

    def test_builder_revision_invalidates_disk_entry(self):
        package = self.root / "package"
        mode = package / "modes" / "guild"
        mode.mkdir(parents=True)
        builder = mode / "rules.py"
        builder.write_text("LIMIT = 1\n")
        self.enterContext(patch.object(static_cache, "PACKAGE_ROOT", package))
        self.addCleanup(static_cache._implementation.cache_clear)

        def restart():
            static_cache._implementation.cache_clear()
            return self.prepare(b"base")

        initial = restart()
        (mode / "panel.css").write_text("body {}")
        self.assertEqual(restart(), initial)
        self.assertEqual(self.calls, 1)
        builder.write_text("LIMIT = 2\n")
        self.assertEqual(restart(), initial)
        self.assertEqual(self.calls, 2)
        builder.rename(mode.parent / builder.name)
        self.assertEqual(restart(), initial)
        self.assertEqual(restart(), initial)
        self.assertEqual(self.calls, 3)

    def test_unavailable_cache_is_optional_and_render_errors_propagate(self):
        self.cache.write_bytes(b"occupied")
        baseline = prepare_static(SimpleNamespace(), self.transform, b"base")
        self.assertEqual(
            prepare_static(SimpleNamespace(static_cache=None), self.transform, b"base"), baseline
        )
        self.assertEqual(self.prepare(b"base"), baseline)
        self.assertEqual(self.cache.read_bytes(), b"occupied")

        def missing(source):
            if source == b"invalid":
                raise ValueError("Invalid catalog")
            return None

        working = StaticCache(self.root / "other-cache")
        self.assertIsNone(working.prepare(missing, b"empty"))
        with self.assertRaisesRegex(ValueError, "Invalid catalog"):
            working.prepare(missing, b"invalid")

    def test_parallel_revisions_never_exchange_outputs(self):
        inputs = [b"one", b"two"] * 8
        expected = {source: self.transform(source) for source in inputs[:2]}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self.prepare, inputs))
        self.assertEqual(results, [expected[source] for source in inputs])
        for source in expected:
            self.assertEqual(self.prepare(source), expected[source])

    def test_game_get_and_check_reuse_overlays_and_follow_changed_selection(self):
        values = {
            "constants": json.dumps({"ChangeNickCost": 1200}),
            "unlockfeature": json.dumps(
                [{"Id": i, "VersionFrom": {"KakaoGlobal": "v9.99"}} for i in expedition.FEATURE_IDS]
            ),
            "__checksum__": "base",
        }
        data = "".join(f"{k}\n{v}\n1\n{digest(v.encode())}\n" for k, v in values.items())
        original = compress(data.encode())
        (self.root / "static_data_get.bin").write_bytes(original)
        enabled = self.root / expedition.TRIAL
        enabled.touch()

        def restart():
            account_costs_static.prepare.cache_clear()
            expedition.prepare.cache_clear()
            db = self.enterContext(closing(sqlite3.connect(":memory:")))
            session = BootstrapSession(GuestStore(db, self.root))
            session.store.references.static_cache = StaticCache(self.cache)
            return session

        def get(session):
            return session.handle(request("/static-data/get", {})).body

        def check(session, checksum):
            reply = session.handle(request("/static-data/check-update", {"Checksum": checksum}))
            return json.loads(reply.body)

        first = get(restart())
        expected = expedition.prepare(account_costs_static.prepare(original)[0])
        self.assertEqual(first, expected[0])
        second = restart()
        with (
            patch.object(
                account_costs_static, "compress", side_effect=AssertionError("cache miss")
            ),
            patch.object(expedition, "compress", side_effect=AssertionError("cache miss")),
        ):
            self.assertEqual(second.handle(request("/static-data/get", {})).body, first)
            self.assertTrue(check(second, expected[1])["UpToDate"])
            enabled.unlink()
            changed = check(second, expected[1])
            self.assertFalse(changed["UpToDate"])
            self.assertNotEqual(changed["Checksum"], expected[1])
            self.assertEqual(
                records(decode(get(second)))[1]["__checksum__"][1], changed["Checksum"]
            )
