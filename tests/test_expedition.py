# SPDX-License-Identifier: Apache-2.0
"""The local Expedition trial restores access and reads the imported save."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.expedition import (
    BEAT,
    CLEAR,
    END,
    ENTRY,
    FARM_ENTRY,
    RANKINGS,
    START,
    TODAY_SCORE,
    TRIAL,
)
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from tests.test_snapshots import request, synthetic_snapshot


class ExpeditionTests(unittest.TestCase):
    def setUp(self):
        reference = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(reference)
        self.db = self.enterContext(closing(sqlite3.connect(":memory:")))
        self.session = BootstrapSession(GuestStore(self.db, self.root))

    def test_opt_in_feature_table_preserves_other_regions_conditions_and_mode_overlay(self):
        features = [
            {
                "Id": ident,
                "Type": "QuestClear",
                "Value": {"Default": 38},
                "VersionFrom": {"KakaoGlobal": "v9.99", "KakaoKorea": "v9.99"},
            }
            for ident in (10, 31, 110)
        ]
        tables = {
            "unlockfeature": json.dumps(features),
            "guildraid2": '{"Seasons":[{"Id":42}]}',
            "__checksum__": "old",
        }
        source = compress(
            "".join(
                f"{name}\n{value}\n3\n{digest(value.encode())}\n" for name, value in tables.items()
            ).encode()
        )
        source_path = self.root / "static_data_get.bin"
        source_path.write_bytes(source)
        get = request("/static-data/get", {})
        self.assertEqual(self.session.handle(get).body, source)

        (self.root / TRIAL).touch()
        _, updated = records(decode(self.session.handle(get).body))
        expected = json.loads(tables["unlockfeature"])
        for row in expected[1:]:
            row["VersionFrom"]["KakaoGlobal"] = "v3.57"
        self.assertEqual(json.loads(updated["unlockfeature"][1]), expected)
        self.assertEqual(updated["unlockfeature"][2], 4)
        self.assertEqual(updated["guildraid2"][1:], (tables["guildraid2"], 3))
        checksum = updated["__checksum__"][1]
        for value in ("old", checksum):
            reply = self.session.handle(request("/static-data/check-update", {"Checksum": value}))
            self.assertEqual(json.loads(reply.body)["UpToDate"], value == checksum)
            self.assertEqual(json.loads(reply.body)["Checksum"], checksum)
        self.assertEqual(source_path.read_bytes(), source)

    def install_save(self):
        snapshot = synthetic_snapshot()
        profile = snapshot["profile"]
        saved = {
            "UserId": profile["User"]["Id"],
            "Collectibles": [2001],
            "SpecialCollectiblesPlay": "",
            "AreaProgresses": [{"Id": 1, "Grade": 101}],
            "StageStates": [
                {"Id": 250011001, "StageState": 7, "MaxScore": 123, "NumCleared": 1},
                {"Id": 250011002, "StageState": 1, "MaxScore": 0, "NumCleared": 0},
            ],
        }
        profile["UserExpedition"] = saved
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("synthetic", "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        self.db.execute("PRAGMA query_only=ON")
        return saved

    def test_entry_returns_current_saved_progress_and_no_daily_score_writes(self):
        saved = self.install_save()
        entry = {"RegionId": 1, "IsPartial": False}
        with self.assertRaises(PacketError):
            self.session.handle(request(ENTRY, entry))
        self.session.signed_in = True
        with self.assertRaises(PacketError):
            self.session.handle(request(ENTRY, entry))
        (self.root / TRIAL).touch()
        for is_partial in (False, True):
            reply = self.session.handle(request(ENTRY, dict(entry, IsPartial=is_partial)))
            self.assertEqual(
                json.loads(reply.body),
                {"UserExpedition": saved, "IsFirstEnter": False, "IsPartial": False},
            )
        reply = self.session.handle(request(TODAY_SCORE, {"RegionId": 1}))
        self.assertEqual(json.loads(reply.body), {"TodayMaxScore": []})
        for is_partial in (False, True):
            reply = self.session.handle(request(FARM_ENTRY, {"IsPartial": is_partial}))
            farm = json.loads(reply.body)
            self.assertFalse(farm["IsPartial"])
            self.assertEqual(farm["UserHeavenHoldFarm"]["UserId"], saved["UserId"])
            self.assertEqual(farm["UserHeavenHoldFarm"]["Buildings"], [])
        with self.assertRaises(PacketError):
            self.session.handle(request(FARM_ENTRY, {"IsPartial": 1}))
        for bad in ({"RegionId": True}, {"RegionId": 1}, dict(entry, RegionId=2)):
            with self.assertRaises(PacketError):
                self.session.handle(request(ENTRY, bad))

    def test_unlocked_stage_can_run_and_score_without_spending_or_advancing_save(self):
        self.install_save()
        self.session.signed_in = True
        (self.root / TRIAL).touch()
        stage = {"StageId": 250011001}
        stages = [{"Id": ident, "Time": 100, "PartyCount": 3} for ident in (250011001, 250011002)]
        tables = {
            "expedition": {"Districts": [{"StageIds": [250011001, 250011002]}]},
            "expeditionbattle": {
                "Constants": {
                    "RemainingTimeBonus": 5,
                    "RemainingPartyBonus": 0.03,
                    "PartySwitchingBonus": 0.03,
                }
            },
            "stages": stages,
        }
        data = compress(
            "".join(
                f"{name}\n{text}\n1\n{digest(text.encode())}\n"
                for name, text in ((name, json.dumps(table)) for name, table in tables.items())
            ).encode()
        )
        (self.root / "static_data_get.bin").write_bytes(data)
        clear = dict(
            stage,
            PlayTime=80 * 10_000_000,
            KillScore=120000,
            Survivors=8,
            PartySwitchingCount=4,
            Kills=15,
            SupportSkillUsed=False,
        )
        for route, payload, expected in (
            (START, stage, {}),
            (
                BEAT,
                dict(stage, MonsterHandleNames=["enemy_a"]),
                {"AddedCollectibles": [], "AddedSpecialCollectibles": []},
            ),
            (
                CLEAR,
                clear,
                {
                    "RegionId": 1,
                    "KillScore": 120000,
                    "TimeScore": 100000,
                    "SurvivorsScore": 52800,
                    "PartySwitchingScore": 26400,
                    "TodayMaxScore": [],
                    "NewRecord": False,
                    "Rankings": [],
                    "AddedCollectibles": [],
                    "AddedItems": [],
                },
            ),
            (END, stage, {}),
            (RANKINGS, stage, {"Rankings": []}),
        ):
            with self.subTest(route=route):
                self.assertEqual(
                    json.loads(self.session.handle(request(route, payload)).body), expected
                )
        for route, payload in (
            (START, {"StageId": 250011002}),
            (START, {"StageId": 100010001}),
            (CLEAR, dict(clear, PlayTime=True)),
            (BEAT, dict(stage, MonsterHandleNames=[3])),
        ):
            with self.subTest(route=route, payload=payload), self.assertRaises(PacketError):
                self.session.handle(request(route, payload))

    def test_switching_to_a_captured_expedition_preset_preserves_its_parties(self):
        self.install_save()
        self.session.signed_in = True
        self.db.execute("PRAGMA query_only=OFF")
        profile = self.session.store.account.profile()
        roster = [{"Id": profile["User"]["Characters"][0]["Id"]}]
        reads = json.loads(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        )
        presets = reads["/preset/get-presets"]["value"]
        presets["UserMultiPartyPreset"] = {
            "Presets": [
                {
                    "Id": 900,
                    "Parties": [{"Characters": roster}, {"Characters": []}, {"Characters": []}],
                }
            ]
        }
        with self.db:
            self.db.execute("UPDATE imported_account SET startup_reads=?", (json.dumps(reads),))
        select = request("/preset/set-selected-preset", {"PresetId": 900})
        with self.assertRaises(PacketError):
            self.session.handle(select)
        (self.root / TRIAL).touch()
        updated = json.loads(self.session.handle(select).body)["User"]
        self.assertEqual(
            updated["SelectedPresetId"], dict(profile["User"]["SelectedPresetId"], Expedition=900)
        )
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0],
            json.dumps(reads),
        )
