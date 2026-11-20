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
    BATTLE_INFOS,
    BATTLE_RECORDS,
    DEFENSE_PARTY,
    END,
    ENTRY,
    OPPONENTS,
    PRACTICE_CONFIG,
    RANKING,
    RANKINGS,
    REFRESH,
    ROUTES,
    SAVE_ATTACK_FORMATION,
    SET_DEFENSE_FORMATION,
    SET_DEFENSE_PRESET,
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
        self.db = db
        self.addCleanup(db.close)
        self.session = BootstrapSession(GuestStore(db, refs))
        saved = synthetic_snapshot()
        user = saved["profile"]["User"]
        user["Options"].update(
            ItemCollection=[{"OptionId": 20001, "Level": 2}],
            HeroCollection=[{"OptionId": 20002, "Level": 3}],
            UserMigrationVersion=1,
        )
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

    def call(self, route, body, sequence_id=12):
        packet = Packet(
            0,
            b"" if body is None else json.dumps(body).encode(),
            body_type=int(body is not None),
            sequence_id=sequence_id,
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

    def test_public_colosseum_menus_return_empty_local_data_without_writes(self):
        changes = self.db.total_changes
        for route, key in ((RANKINGS, "Rankings"), (BATTLE_RECORDS, "BattleRecords")):
            for body in (None, {}):
                self.assertEqual(self.call(route, body), {key: []})
            with self.assertRaises(PacketError):
                self.call(route, {"SeasonId": 7})
        for season, tier, is_attack in ((7, 0, True), (6, 5, False), (7, -1, False)):
            query = {"SeasonId": season, "Tier": tier, "IsAttack": is_attack}
            self.assertEqual(self.call(BATTLE_INFOS, query), {"Infos": []})
        for body in (None, {"SeasonId": 7, "Tier": 5, "IsAttack": 0}, {"seasonId": 7}):
            with self.assertRaises(PacketError):
                self.call(BATTLE_INFOS, body)
        self.assertEqual(self.db.total_changes, changes)

    def test_lobby_reads_require_sign_in(self):
        self.session.signed_in = False
        for route in ROUTES:
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(route, None)

    def test_saved_defense_overrides_the_seed_and_refreshes_without_restarting(self):
        self.config.write_text('{"preset_id": 601}')
        self.db.execute("PRAGMA query_only=OFF")
        original = self.session.store.account.profile()
        seed = self.call(DEFENSE_PARTY, None)
        self.assertFalse(seed["Changed"])
        self.assertEqual(seed["UserColosseum"]["DefensePartyInfo"]["Preset"], self.preset)

        defense = dict(self.preset, Id=0, Name="Defense team", Order=0)
        member = dict(defense["Characters"][0], CharacterSpecOriginId=1)
        editor_preset = dict(
            defense,
            Characters=[member, None],
            Count=1,
            DPSWithCriticalTotal=120.0,
            ToughnessTotal=270.0,
            ExorcismTotal=8,
            IsEmpty=False,
        )
        del editor_preset["Order"]
        saved = self.call(SET_DEFENSE_PRESET, {"Preset": editor_preset}, sequence_id=20)
        self.assertEqual(saved["UserColosseum"]["DefensePartyInfo"]["Preset"], defense)
        first = {"Positions": [4, 0, 0, 0]}
        latest = {"Positions": [20, 0, 0, 0]}
        self.call(SET_DEFENSE_FORMATION, first, sequence_id=21)
        self.call(SET_DEFENSE_FORMATION, latest, sequence_id=22)
        # The old request must return current state after a newer save.
        response = self.call(SET_DEFENSE_FORMATION, first, sequence_id=21)
        self.assertEqual(
            response["UserColosseum"]["DefensePartyInfo"]["Formation"]["Positions"],
            latest["Positions"],
        )
        self.config.unlink()
        refreshed = self.call(REFRESH, None)
        for opponent in refreshed["Opponents"]:
            self.assertEqual(opponent["User"]["Name"], defense["Name"])
            self.assertEqual(opponent["Formation"]["Positions"], latest["Positions"])
        first_opponent = refreshed["Opponents"][0]["User"]
        self.assertEqual(
            self.call(
                START,
                {
                    "OpponentId": first_opponent["Id"],
                    "OpponentParty": [first_opponent["Characters"][0]["CharacterId"]],
                    "OpponentPositions": latest["Positions"],
                },
            ),
            {},
        )
        self.assertEqual(self.session.store.account.profile(), original)

    def test_defense_rejects_invalid_grid_cells_and_unowned_members_without_writes(self):
        self.db.execute("PRAGMA query_only=OFF")
        before = self.db.total_changes
        for route, body in (
            (SET_DEFENSE_FORMATION, {"Positions": [0, 0, 0, 0]}),
            (SET_DEFENSE_FORMATION, {"Positions": [1, 1, 0, 0]}),
            (SET_DEFENSE_FORMATION, {"Positions": [21, 0, 0, 0]}),
            (SET_DEFENSE_PRESET, {"Preset": {"Id": 0, "Order": 0, "Characters": [{"Id": 999}]}}),
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(route, body)
        self.assertEqual(self.db.total_changes, before)

    def test_apply_refreshes_opponent_cards_and_allows_a_start_before_the_refresh(self):
        self.config.write_text('{"preset_id": 601}')
        self.db.execute("PRAGMA query_only=OFF")
        profile = self.session.store.account.profile()
        defenders = profile["User"]["Characters"]
        defenders.append(dict(defenders[0], Id=2, CharacterId=3))
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        first = self.call(OPPONENTS, None)["Opponents"][0]
        old_start = {
            "OpponentId": first["User"]["Id"],
            "OpponentParty": [defenders[0]["CharacterId"]],
            "OpponentPositions": first["Formation"]["Positions"],
        }
        defense = dict(self.preset, Name="New defense", Characters=[{"Id": defenders[1]["Id"]}])
        positions = [20, 0, 0, 0]
        for sequence, route, body in (
            (20, SET_DEFENSE_PRESET, {"Preset": defense}),
            (21, SET_DEFENSE_FORMATION, {"Positions": positions}),
            (21, SET_DEFENSE_FORMATION, {"Positions": positions}),
        ):
            saved = self.call(route, body, sequence_id=sequence)["UserColosseum"]
            self.assertLessEqual(
                datetime.fromisoformat(saved["NextRefresh"]), datetime.now(timezone.utc)
            )

        self.db.execute("PRAGMA query_only=ON")
        self.assertEqual(self.call(START, old_start), {})
        with self.assertRaises(PacketError):
            self.call(START, dict(old_start, OpponentPositions=[1, 2, 3, 4]))
        # The lobby polls get-opponents when the cache expires, without a manual refresh.
        refreshed = self.call(OPPONENTS, None)
        self.assertGreater(
            datetime.fromisoformat(refreshed["UserColosseum"]["NextRefresh"]),
            datetime.now(timezone.utc),
        )
        for opponent in refreshed["Opponents"]:
            self.assertEqual(opponent["User"]["Name"], defense["Name"])
            self.assertEqual(opponent["Formation"]["Positions"], positions)
        self.assertEqual(
            self.call(
                START,
                dict(
                    old_start,
                    OpponentParty=[defenders[1]["CharacterId"]],
                    OpponentPositions=positions,
                ),
            ),
            {},
        )
        with self.assertRaises(PacketError):
            self.call(START, old_start)

    def test_attack_positions_are_independent_even_when_both_sides_use_the_same_team(self):
        self.config.write_text('{"preset_id": 601}')
        self.db.execute("PRAGMA query_only=OFF")
        defense = [20, 0, 0, 0]
        attack = [1, 0, 0, 0]
        self.call(SET_DEFENSE_FORMATION, {"Positions": defense}, sequence_id=21)
        body = {"PresetId": 601, "Positions": attack}
        saved = self.call(SAVE_ATTACK_FORMATION, body, sequence_id=22)
        response = self.call(REFRESH, None)
        lobby = response["UserColosseum"]
        self.assertEqual(saved["UserColosseum"]["NextRefresh"], lobby["NextRefresh"])
        self.assertEqual(lobby["Formations"], {"601": {"Id": 601, "Positions": attack}})
        self.assertEqual(lobby["DefensePartyInfo"]["Formation"]["Positions"], defense)
        for opponent in response["Opponents"]:
            self.assertEqual(opponent["Formation"]["Positions"], defense)
        before = self.db.total_changes
        self.call(SAVE_ATTACK_FORMATION, body, sequence_id=22)
        with self.assertRaises(PacketError):
            self.call(SAVE_ATTACK_FORMATION, dict(body, PresetId=701), sequence_id=23)
        self.assertEqual(self.db.total_changes, before)

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
        expected_options = dict(owner["Options"])
        expected_options.pop("UserMigrationVersion")
        for entry in opponents:
            self.assertEqual(entry["User"]["Options"], expected_options)
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
