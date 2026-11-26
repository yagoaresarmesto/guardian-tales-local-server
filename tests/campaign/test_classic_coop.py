# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.modes.classic_coop import CREATE, END, LEAVE, MARKER, STAGE_ID, START
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore
from guardian_tales.runtime.packet_reader import parse_packet
from guardian_tales.runtime.protocol import Packet, PacketError, encode_packet


class ClassicCoopTests(unittest.TestCase):
    def setUp(self):
        scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.marker = Path(scratch) / MARKER
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db, Path(scratch))
        self.session = BootstrapSession(self.store)
        self.create = {"StageId": STAGE_ID, "TestMode": True}
        self.start = {"CoopId": STAGE_ID}
        self.end = {"CoopId": STAGE_ID, "RaidResult": {}, "Result": 0}
        self.leave = {"StageId": STAGE_ID, "IsClearExit": False, "ExitName": None}
        self.leave_response = {
            "AddedItems": [],
            "StageState": 0,
            "StageProgress": self.store.account.stage_progress(STAGE_ID),
        }

    def call(self, route, body):
        packet = Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=18)
        response = self.session.handle(parse_packet(encode_packet(packet)))
        self.assertEqual((response.sequence_id, response.body_type), (18, 1))
        return json.loads(response.body)

    def test_practice_is_opt_in_and_requires_sign_in(self):
        with self.assertRaisesRegex(PacketError, "sign-in"):
            self.call(CREATE, self.create)
        self.session.signed_in = True
        with self.assertRaisesRegex(PacketError, "disabled"):
            self.call(CREATE, self.create)
        self.marker.touch()
        self.assertEqual(self.call(CREATE, self.create), self.start)

    def test_practice_can_repeat_without_account_changes(self):
        self.marker.touch()
        self.session.signed_in = True
        before = list(self.db.iterdump())
        for _ in range(2):
            self.assertEqual(self.call(CREATE, self.create), self.start)
            self.assertEqual(self.call(START, self.start), {})
            for _ in range(2):
                self.assertEqual(self.call(END, self.end), {"RewardItems": [], "AddedItems": []})
                self.assertEqual(self.call(LEAVE, self.leave), self.leave_response)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_other_stages_and_matches_are_rejected(self):
        self.marker.touch()
        self.session.signed_in = True
        for route, body in (
            (CREATE, {**self.create, "StageId": STAGE_ID + 1}),
            (CREATE, {**self.create, "TestMode": False}),
            (START, self.start),
            (END, self.end),
        ):
            with self.subTest(route=route, body=body), self.assertRaises(PacketError):
                self.call(route, body)
        self.call(CREATE, self.create)
        with self.assertRaises(PacketError):
            self.call(END, {**self.end, "CoopId": STAGE_ID + 1})

    def test_practice_exit_is_read_only_after_reconnecting(self):
        self.session.signed_in = True
        with self.assertRaisesRegex(PacketError, "disabled"):
            self.call(LEAVE, self.leave)
        self.marker.touch()
        before = list(self.db.iterdump())
        for cleared in (True, False):
            self.assertEqual(
                self.call(LEAVE, {**self.leave, "IsClearExit": cleared}), self.leave_response
            )
        self.assertEqual(list(self.db.iterdump()), before)

    def test_imported_practice_exit_leaves_other_campaign_exits_guarded(self):
        self.marker.touch()
        self.session.signed_in = True
        profile = self.store.account.profile()
        profile["UserProgress"]["StageStates"][str(STAGE_ID)] = 3
        with self.db:
            self.db.execute(
                "UPDATE local_account SET profile = ? WHERE id = 1", (json.dumps(profile),)
            )
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)", ("test", "test", "{}", "{}")
            )
        before = list(self.db.iterdump())
        self.assertEqual(self.call(LEAVE, self.leave), {**self.leave_response, "StageState": 3})
        with self.assertRaisesRegex(PacketError, "Imported-account"):
            self.call(LEAVE, {**self.leave, "StageId": STAGE_ID + 1})
        self.assertEqual(list(self.db.iterdump()), before)
