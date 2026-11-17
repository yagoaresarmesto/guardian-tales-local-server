# SPDX-License-Identifier: Apache-2.0
"""Contents-book prerequisites preserve saved state and reject mode actions."""

import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.play_menu import PLAY_MENU_ROUTES
from guardian_tales.protocol import Packet, PacketError, encode_packet
from tests.test_snapshots import synthetic_snapshot


class PlayMenuTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = GuestStore(self.db)
        self.session = BootstrapSession(self.store)

    def tearDown(self):
        self.db.close()

    def call(self, route, value=None):
        request = parse_packet(
            encode_packet(
                Packet(0, json.dumps(value).encode(), body_type=1, api=route, sequence_id=18)
            )
        )
        response = self.session.handle(request)
        self.assertEqual(response.sequence_id, 18)
        self.assertEqual(response.body_type, 1)
        return read_json_body(parse_packet(encode_packet(response)))

    def login(self):
        self.call(
            "/auth/sign-in",
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": False},
        )

    def install_import(self):
        snapshot = synthetic_snapshot()
        snapshot["profile"]["UserProgress"]["RiftEvolveStoneRewards"] = {
            "4": {"Unique": 101, "Rares": [102, 103]}
        }
        snapshot["startup_reads"]["/preset/get-presets"]["value"]["CoopExpeditionSlots"] = {
            "1": {"CharacterId": 1, "WeaponId": 1}
        }
        with self.db:
            self.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1", (json.dumps(snapshot["profile"]),)
            )
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("synthetic", "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        return snapshot

    def test_fresh_prerequisites_are_reads_without_rewards_or_profile_changes(self):
        self.login()
        before = list(self.db.iterdump())
        profile = self.store.account.profile()
        for partial in (False, True):
            coop = self.call("/coop-expedition/enter", {"IsPartial": partial})
            self.assertIs(coop["IsPartial"], False)
            self.assertEqual(coop["UserCoopExpedition"]["StageStates"], {})
            self.assertEqual(coop["UserCoopExpedition"]["WeeklyClearRewardCount"], {})
            self.assertEqual(coop["UserCoopExpedition"]["Slots"], {})
        for body in (None, {}):
            rift = self.call("/rift/enter", body)
            self.assertEqual(rift, {"UserProgress": profile["UserProgress"]})
        self.assertEqual(list(self.db.iterdump()), before)

    def test_imported_reads_preserve_presets_and_return_current_rift_settings(self):
        snapshot = self.install_import()
        self.login()
        before = list(self.db.iterdump())
        expected_slots = snapshot["startup_reads"]["/preset/get-presets"]["value"][
            "CoopExpeditionSlots"
        ]
        for partial in (False, True):
            coop = self.call("/coop-expedition/enter", {"IsPartial": partial})
            self.assertEqual(coop["UserCoopExpedition"]["Slots"], expected_slots)
        self.assertEqual(
            self.call("/rift/enter")["UserProgress"], snapshot["profile"]["UserProgress"]
        )
        self.assertEqual(list(self.db.iterdump()), before)
        changed = self.store.account.profile()
        changed["UserProgress"]["RiftEvolveStoneRewards"]["4"]["Unique"] = 104
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(changed),))
        before = list(self.db.iterdump())
        self.assertEqual(self.call("/rift/enter")["UserProgress"], changed["UserProgress"])
        self.assertEqual(list(self.db.iterdump()), before)

    def test_authentication_and_exact_request_contracts_reject_without_writes(self):
        before = list(self.db.iterdump())
        for route, body in (
            ("/coop-expedition/enter", {"IsPartial": False}),
            ("/rift/enter", None),
        ):
            with self.assertRaises(PacketError):
                self.call(route, body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.install_import()
        self.login()
        before = list(self.db.iterdump())
        malformed = {
            "/coop-expedition/enter": (
                None,
                {},
                [],
                False,
                {"IsPartial": 0},
                {"IsPartial": "false"},
                {"IsPartial": True, "Claim": True},
                {"isPartial": False},
            ),
            "/rift/enter": ([], False, 0, {"Claim": True}, {"IsPartial": False}),
        }
        for route, bodies in malformed.items():
            for body in bodies:
                with self.subTest(route=route, body=body), self.assertRaises(PacketError):
                    self.call(route, body)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_preserved_slots_and_unsupported_actions_do_not_change_account(self):
        snapshot = self.install_import()
        snapshot["startup_reads"]["/preset/get-presets"]["value"]["CoopExpeditionSlots"] = []
        with self.db:
            self.db.execute(
                "UPDATE imported_account SET startup_reads=?",
                (json.dumps(snapshot["startup_reads"]),),
            )
        self.login()
        before = list(self.db.iterdump())
        for route, body in (
            ("/coop-expedition/enter", {"IsPartial": False}),
            ("/coop-expedition/create", {}),
            ("/rift/set-evolve-stone-reward", {}),
            ("/stage/start-stage", {}),
        ):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(route, body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(set(PLAY_MENU_ROUTES), {"/coop-expedition/enter", "/rift/enter"})
