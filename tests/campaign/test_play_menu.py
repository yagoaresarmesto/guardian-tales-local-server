# SPDX-License-Identifier: Apache-2.0
"""Contents-book prerequisites preserve saved state and reject mode actions."""

import json
import sqlite3
import unittest

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.play_menu import PLAY_MENU_ROUTES
from guardian_tales.protocol import Packet, PacketError, encode_packet
from tests.account.test_snapshots import synthetic_snapshot


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
            ("/tower-infinity/enter", None),
            ("/tower-infinity/get-rankings", None),
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
            "/tower-infinity/enter": ([], False, 0, {"Floor": 1}, {"Claim": True}),
            "/tower-infinity/get-rankings": ([], False, 0, {"Page": 1}, {"UserId": 9400}),
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
            ("/tower-infinity/save-formation", {}),
            ("/tower-infinity/start-stage", {}),
            ("/tower-infinity/end-stage", {}),
            ("/tower-infinity/get-my-ranking", {}),
        ):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(route, body)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(
            set(PLAY_MENU_ROUTES),
            {
                "/coop-expedition/enter",
                "/rift/enter",
                "/tower-infinity/enter",
                "/tower-infinity/get-rankings",
            },
        )

    def test_tower_rankings_are_empty_reads_for_fresh_and_imported_accounts(self):
        for imported in (False, True):
            with self.subTest(imported=imported):
                if imported:
                    self.install_import()
                self.login()
                before = list(self.db.iterdump())
                for body in (None, {}, None):
                    self.assertEqual(
                        self.call("/tower-infinity/get-rankings", body), {"Rankings": []}
                    )
                self.assertEqual(list(self.db.iterdump()), before)

    def test_tower_entry_returns_legacy_formation_without_migration_or_writes(self):
        self.login()
        before = list(self.db.iterdump())
        tower = self.store.account.profile()["UserProgress"]["TowerInfinity"]
        for body in (None, {}):
            response = self.call("/tower-infinity/enter", body)
            self.assertEqual(response, {"TowerInfinity": tower})
            self.assertNotIn("Formations", response["TowerInfinity"])
            self.assertNotIn("SelectedParty", response["TowerInfinity"])
        self.assertEqual(list(self.db.iterdump()), before)

    def test_imported_tower_entry_preserves_signed_floor_formation_and_current_state(self):
        self.install_import()
        profile = self.store.account.profile()
        profile["UserProgress"]["TowerInfinity"] = {
            "Floor": -27,
            "Formation": {"Id": 2, "Positions": [0, 1, 0, 0]},
        }
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.login()
        for floor in (-27, 28):
            profile["UserProgress"]["TowerInfinity"]["Floor"] = floor
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            before = list(self.db.iterdump())
            for body in (None, {}):
                self.assertEqual(
                    self.call("/tower-infinity/enter", body),
                    {"TowerInfinity": profile["UserProgress"]["TowerInfinity"]},
                )
            self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_saved_tower_progress_is_rejected_without_repair_or_rewards(self):
        self.install_import()
        self.login()
        for invalid in (
            None,
            [],
            {},
            {"Floor": True},
            {"Floor": "1"},
            {"Floor": -(2**31)},
            {"Floor": 2**31},
        ):
            with self.subTest(progress=invalid):
                profile = self.store.account.profile()
                profile["UserProgress"]["TowerInfinity"] = invalid
                with self.db:
                    self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
                before = list(self.db.iterdump())
                with self.assertRaises(PacketError):
                    self.call("/tower-infinity/enter")
                self.assertEqual(list(self.db.iterdump()), before)
