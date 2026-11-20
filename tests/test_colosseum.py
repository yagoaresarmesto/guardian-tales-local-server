# SPDX-License-Identifier: Apache-2.0
"""Check native Colosseum cache hints through the authenticated packet dispatcher."""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.colosseum import (
    END,
    ENTRY,
    OPPONENTS,
    PRACTICE_CONFIG,
    RANKING,
    REFRESH,
    ROUTES,
    START,
)
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.raid_static import compress, digest
from tests.test_snapshots import synthetic_snapshot


class ColosseumEntryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        refs = Path(directory.name)
        self.config = refs / PRACTICE_CONFIG
        table = b'{"Seasons":[{"SeasonId":7,"MapId":{"KakaoGlobal":31}}]}'
        (refs / "static_data_get.bin").write_bytes(
            compress(b"colosseum\n" + table + b"\n1\n" + digest(table).encode() + b"\n")
        )
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        self.session = BootstrapSession(GuestStore(db, refs))
        saved = synthetic_snapshot()
        user = saved["profile"]["User"]
        saved["profile"]["UserRecord"]["ColosseumRank"] = 7
        user["SelectedPresetId"]["ColosseumAttack"] = 601
        self.preset = {
            "Id": 601,
            "Name": "Practice",
            "Characters": [
                {"Id": user["Characters"][0]["Id"], "Weapon1": user["ItemWeapons"][0]["Id"]}
            ],
        }
        saved["startup_reads"]["/preset/get-presets"]["value"]["UserPartyPreset2"] = {
            "Presets": [self.preset]
        }
        with db:
            db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("0" * 64, "synthetic", json.dumps(saved["startup_reads"]), "{}"),
            )
            db.execute(
                "UPDATE local_account SET profile=? WHERE id=1", (json.dumps(saved["profile"]),)
            )
        self.call("/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": True})
        db.execute("PRAGMA query_only=ON")

    def call(self, route, body):
        packet = Packet(
            0,
            b"" if body is None else json.dumps(body).encode(),
            body_type=int(body is not None),
            sequence_id=12,
            api=route,
        )
        response = self.session.handle(parse_packet(encode_packet(packet)))
        return read_json_body(parse_packet(encode_packet(response)))

    def test_full_partial_and_legacy_entry_return_the_saved_team(self):
        for body in ({"IsPartial": False}, {"IsPartial": True}, None, {}):
            with self.subTest(body=body):
                response = self.call(ENTRY, body)
                lobby = response["UserColosseum"]
                self.assertEqual(response["DefenseBattleRecords"], [])
                self.assertFalse(response["NewSeason"])
                self.assertEqual(response["SeasonUntil"], lobby["NextReset"])
                self.assertGreater(
                    datetime.fromisoformat(lobby["NextRefresh"]), datetime.now(timezone.utc)
                )
                self.assertEqual(lobby["DefensePartyInfo"]["Preset"], self.preset)
                self.assertEqual(lobby["SeasonId"], 7)
                self.assertEqual(lobby["Ticket"]["Type"], 3)

    def test_malformed_cache_hints_are_rejected(self):
        for body in ({"isPartial": False}, {"IsPartial": 1}, {"IsPartial": True, "extra": 1}, []):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(ENTRY, body)

    def test_lobby_loads_opponent_list_and_personal_rank_without_writes(self):
        lobby = self.call(ENTRY, {"IsPartial": False})["UserColosseum"]
        for body in (None, {}):
            response = self.call(OPPONENTS, body)
            self.assertEqual(response["Opponents"], [])
            self.assertEqual(
                response["UserColosseum"]["DefensePartyInfo"], lobby["DefensePartyInfo"]
            )
            self.assertGreater(
                datetime.fromisoformat(response["UserColosseum"]["NextRefresh"]),
                datetime.now(timezone.utc),
            )
            self.assertEqual(self.call(RANKING, body), {"Ranking": 7})
        for route in (OPPONENTS, REFRESH, RANKING):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(route, {"UserId": 3})

    def test_parameterless_refresh_can_be_repeated_without_spending(self):
        entry = self.call(ENTRY, {"IsPartial": False})["UserColosseum"]
        # The synthetic imported save is query-only during dispatch, including retries.
        for _ in range(2):
            response = self.call(REFRESH, None)
            self.assertEqual(response["Opponents"], [])
            self.assertEqual(response["UserColosseum"], entry)

    def test_lobby_reads_require_sign_in(self):
        self.session.signed_in = False
        for route in ROUTES:
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(route, None)

    def test_practice_opponent_uses_the_saved_preset_and_resolves_its_equipment(self):
        self.config.write_text('{"preset_id": 601}')
        owner = self.session.store.account.profile()["User"]
        opponents = self.call(OPPONENTS, None)["Opponents"]
        self.assertEqual(len(opponents), 3)
        opponent_ids = [opponent["User"]["Id"] for opponent in opponents]
        self.assertEqual(len(set(opponent_ids)), 3)
        expected_opponent = opponents[0]
        user = expected_opponent["User"]
        self.assertNotEqual(user["Id"], owner["Id"])
        self.assertEqual(user["Name"], "Practice")
        self.assertEqual(user["Party"]["Characters"], [self.preset["Characters"][0]["Id"]])
        self.assertEqual(len(user["ItemWeapons"]), 1)
        self.assertEqual(user["Characters"][0]["Weapon1"], user["ItemWeapons"][0]["Id"])
        self.assertIsNone(user["Characters"][0]["Weapon2"])
        self.assertEqual(self.call(REFRESH, None)["Opponents"], opponents)
        lobby = self.call(ENTRY, None)["UserColosseum"]
        self.assertEqual(lobby["OpponentIds"], opponent_ids)
        self.assertEqual(lobby["Challenges"], [0, 0, 0])

        start = {
            "OpponentId": user["Id"],
            "OpponentParty": [user["Characters"][0]["CharacterId"]],
            "OpponentPositions": expected_opponent["Formation"]["Positions"],
        }
        result = {
            "OpponentId": user["Id"],
            "Result": 1,
            "Damages": [[0]],
            "OpponentLevels": [1],
        }
        for _ in range(2):
            self.assertEqual(self.call(START, start), {})
            self.assertEqual(self.call(END, result), {"AddedTrophy": 0, "AddedItems": []})
        with self.assertRaises(PacketError):
            self.call(START, dict(start, OpponentParty=[999]))
        with self.assertRaises(PacketError):
            self.call(END, dict(result, OpponentId=owner["Id"]))
