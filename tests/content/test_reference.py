# SPDX-License-Identifier: Apache-2.0
"""External bootstrap inputs are optional until the matching API is requested."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet
from guardian_tales.reference import ReferenceData, compressed_empty_list


class ReferenceTests(unittest.TestCase):
    def test_empty_account_templates_do_not_require_captured_bootstrap_bodies(self):
        with tempfile.TemporaryDirectory() as directory:
            references = ReferenceData(directory)
            self.assertEqual(references.json("new_guest_profile.json")["User"]["Characters"], [])
            with self.assertRaisesRegex(ValueError, "Missing reference file"):
                references.read_bytes("resource_urls.bin")
            with self.assertRaises(ValueError):
                references.read_bytes("../outside.json")

    def test_missing_seed_is_rejected_and_external_body_is_used_without_account_mutation(self):
        with tempfile.TemporaryDirectory() as directory, sqlite3.connect(":memory:") as db:
            store = GuestStore(db, directory)
            session = BootstrapSession(store)
            before = store.account.profile()
            request = parse_packet(
                encode_packet(Packet(0, api="/static-data/in-app-product-ids", sequence_id=1))
            )
            with self.assertRaisesRegex(PacketError, "Missing reference file"):
                session.handle(request)
            (Path(directory) / "product_ids.bin").write_bytes(compressed_empty_list())
            response = session.handle(request)
            self.assertEqual(response.body_type, 2)
            self.assertEqual(read_json_body(parse_packet(encode_packet(response))), [])
            self.assertEqual(store.account.profile(), before)
