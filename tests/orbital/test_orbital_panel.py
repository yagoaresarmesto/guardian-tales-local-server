# SPDX-License-Identifier: Apache-2.0
"""Orbital Lift progress edits through the unified dashboard on a disposable save."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.orbital_levels import SELECTION
from guardian_tales.raid_static import compress, decode, digest, records
from guardian_tales.reference import ReferenceData
from guardian_tales.snapshots import CLIENT
from guardian_tales.state_lock import StateLock
from guardian_tales.village import MAX_REVISION
from guardian_tales.web_panel.server import WebPanel
from tests.account.test_snapshots import request as packet_request
from tests.inventory.test_inventory_panel import prepare_inventory


class OrbitalPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = self.enterContext(closing(sqlite3.connect(prepare_inventory(self.root))))
        self.original = self.profile()
        self.original["UserProgress"] = {
            "Cas": 17,
            "TowerInfinity": {"Floor": -1340, "Formation": {"Positions": [1, 4, 7, 15]}},
        }
        self.store_original()
        (self.root / "orbital_entry_catalog.json").write_text(
            json.dumps({"client": CLIENT, "floors": [1, 1341, 1400, 1500, 1501]})
        )
        panel = WebPanel(ReferenceData(self.root), 0, database=self.root / "server.sqlite3")
        panel.start()
        self.addCleanup(panel.stop)
        self.origin = f"http://127.0.0.1:{panel.server_port}"

    def profile(self):
        return json.loads(self.db.execute("SELECT profile FROM local_account").fetchone()[0])

    def store_original(self):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.original),))

    def api(self, body=None, suffix=""):
        request = Request(
            self.origin + "/api/orbital-lift" + suffix,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Origin": self.origin, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_global_enemy_levels_reach_bootstrap_and_restore_each_floor(self):
        floors = [
            {
                "Floor": floor,
                "StandardLevel": min(199, 49 + floor // 10),
                "Monsters": [] if floor % 50 == 1 else [{"Options": [{"Level": 3}]}],
            }
            for floor in range(1, 1502)
        ]
        tables = {
            "infinitytowerfloors": floors,
            "infinitytowermonsters": [{"MonsterId": 2, "SpecId": 42}],
            "exps2": {"LevelExps": [{"Level": i} for i in range(220)]},
            "__checksum__": "stock",
        }
        texts = {name: json.dumps(data) for name, data in tables.items()}
        source = compress(
            "".join(f"{k}\n{v}\n7\n{digest(v.encode())}\n" for k, v in texts.items()).encode()
        )
        path = self.root / "static_data_get.bin"
        path.write_bytes(source)
        conn = self.enterContext(closing(sqlite3.connect(":memory:")))
        session = BootstrapSession(GuestStore(conn, self.root))

        def level_api(body=None):
            return self.api(body, "/enemy-level")

        def game(route, body):
            return session.handle(packet_request("/static-data/" + route, body)).body

        self.assertEqual(level_api(), {"level": None, "maxLevel": 200, "revision": 0})
        self.assertEqual(game("get", {}), source)
        for bad in (False, 0, -1, 201, 220, 1.5, "200"):
            with self.subTest(bad=bad), self.assertRaises(HTTPError) as rejected:
                level_api({"level": bad, "revision": 0})
            self.assertEqual(rejected.exception.code, 400)
            rejected.exception.close()
        self.assertFalse((self.root / SELECTION).exists())
        last_checksum = texts["__checksum__"]
        for revision, level in enumerate((200, 1, None)):
            body = {"revision": revision, "level": level}
            # Only progress editing takes the backend's save lock.
            with StateLock(self.root):
                level_api(body)
            self.assertEqual(
                level_api(), {"level": level, "maxLevel": 200, "revision": revision + 1}
            )
            with self.assertRaises(HTTPError) as stale:
                level_api(body)
            self.assertEqual(stale.exception.code, 409)
            stale.exception.close()
            level_api(dict(body, revision=revision + 1))
            self.assertEqual(level_api()["revision"], revision + 1)
            _, served = records(decode(game("get", {})))
            check = json.loads(game("check-update", {"Checksum": last_checksum}))
            self.assertFalse(check["UpToDate"])
            last_checksum = served["__checksum__"][1]
            self.assertEqual(check["Checksum"], last_checksum)
            self.assertTrue(
                json.loads(game("check-update", {"Checksum": last_checksum}))["UpToDate"]
            )
            for name in ("exps2", "infinitytowermonsters"):
                self.assertEqual(served[name][1:], (texts[name], 7))
            self.assertEqual(served["infinitytowerfloors"][2], 8 + revision)
            expected = [
                (
                    dict(row, StandardLevel=level - 1)
                    if level is not None and row["Floor"] <= 1500
                    else row
                )
                for row in floors
            ]
            self.assertEqual(json.loads(served["infinitytowerfloors"][1]), expected)
        self.assertEqual(served["infinitytowerfloors"][1], texts["infinitytowerfloors"])
        self.assertEqual(path.read_bytes(), source)
        self.assertEqual(self.profile(), self.original)

    def test_custom_boards_persist_and_restore_independently_over_global_levels(self):
        stock = [
            {"Position": 4, "MonsterId": 10, "Options": [{"OptionId": 15, "Level": 2}]},
            {"Position": 3, "MonsterId": 11},
        ]
        floors = [
            {
                "Floor": f,
                "FloorType": "RecordRoom" if f == 51 else "Normal",
                "Rewards": [{"ItemId": 70003, "Amount": 500}] if f == 51 else [],
                "StandardLevel": 199 if f == 1501 else 49,
                "Monsters": [] if f == 51 else stock,
            }
            for f in range(1, 1502)
        ]
        tables = {
            "infinitytowerfloors": floors,
            "exps2": {"LevelExps": list(range(220))},
            "infinitytowermonsters": [
                {"MonsterId": 10, "SpecId": 10, "Class": "boss", "AvailableEliteOption": [15, 18]},
                {"MonsterId": 11, "SpecId": 11},
                {"MonsterId": 12, "SpecId": 12},
            ],
            "monsters": [{"Id": i, "Name": f"it_foe_{i}"} for i in (10, 11, 12)],
            "options": [{"Id": 15, "Name": "elite_mortar"}, {"Id": 18, "Name": "elite_stat_up"}],
            "__checksum__": "stock",
        }
        texts = {name: json.dumps(data) for name, data in tables.items()}
        source = compress(
            "".join(f"{k}\n{v}\n7\n{digest(v.encode())}\n" for k, v in texts.items()).encode()
        )
        path = self.root / "static_data_get.bin"
        path.write_bytes(source)
        conn = self.enterContext(closing(sqlite3.connect(":memory:")))
        game = BootstrapSession(GuestStore(conn, self.root))

        def served():
            body = game.handle(packet_request("/static-data/get", {})).body
            fields = records(decode(body))[1]
            reply = game.handle(
                packet_request("/static-data/check-update", {"Checksum": fields["__checksum__"][1]})
            )
            self.assertTrue(json.loads(reply.body)["UpToDate"])
            return json.loads(fields["infinitytowerfloors"][1])

        def choose(floor, revision, board):
            return self.api({"floor": floor, "revision": revision, "board": board}, "/boards")

        view = self.api(suffix="/boards")
        previews = self.api(suffix="/map")
        self.assertEqual(len(previews["floors"]), 1500)
        kind, level, rewards = previews["floors"][50]
        self.assertEqual(
            (kind, level, previews["rewardSets"][rewards]), ("RecordRoom", 50, [[70003, 500]])
        )
        self.assertEqual(self.profile(), self.original)
        self.assertEqual(view["floor"]["type"], "Normal")
        self.assertEqual({e["id"] for e in view["enemies"]}, {10, 11})
        self.assertEqual([e["id"] for e in view["enemies"] if e["boss"]], [10])
        self.assertEqual(view["floor"]["originalElites"], {"4": 15})
        self.assertEqual({e["id"]: e["elites"] for e in view["enemies"]}, {10: [15, 18], 11: []})
        # Preserve settings from installations that predate custom boards.
        (self.root / SELECTION).write_text(json.dumps({"revision": 1, "level": 100}))
        self.assertEqual(self.api(suffix="/boards")["modifiedFloors"], [])
        for invalid_floor in (0, 1501):
            with self.assertRaises(HTTPError) as invalid:
                choose(invalid_floor, 1, None)
            self.assertEqual(invalid.exception.code, 400)
            invalid.exception.close()
        units = [{"position": 20, "enemy": 10, "origin": 4}, {"position": 4, "enemy": 10}]
        for bad in (
            [],
            [units[0], units[0]],
            [{"position": 21, "enemy": 10}],
            [{"position": 1, "enemy": 12}],
            [{"position": 1, "enemy": 10, "origin": 3}],
            [{"position": True, "enemy": 10}],
            [{"position": 1, "enemy": 10, "Options": []}],
            [{"position": 1, "enemy": 11, "elite": 18}],
            [{"position": 1, "enemy": 10, "elite": 19}],
            [{"position": 1, "enemy": 10, "elite": True}],
            [{"position": 1, "enemy": 10, "elite": [15, 18]}],
        ):
            with self.subTest(bad=bad), self.assertRaises(HTTPError) as rejected:
                choose(1, 1, {"units": bad, "level": None})
            self.assertEqual(rejected.exception.code, 400)
            rejected.exception.close()
        with self.assertRaises(HTTPError) as stale:
            choose(1500, 0, {"units": units, "level": 200})
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        choose(1500, 1, {"units": units, "level": 200})
        choose(51, 2, {"units": [units[1]], "level": None})
        choose(1, 3, {"units": view["floor"]["units"], "level": 1})
        self.assertEqual(self.api(suffix="/boards/52")["modifiedFloors"], [1, 51, 1500])
        self.assertEqual(self.api(suffix="/boards/1")["custom"], {"units": None, "level": 1})
        active = served()
        self.assertEqual(
            active[1499]["Monsters"],
            [dict(stock[0], Position=20), {"Position": 4, "MonsterId": 10}],
        )
        self.assertEqual(
            [active[i]["StandardLevel"] for i in (0, 1, 50, 1499, 1500)], [0, 99, 99, 199, 199]
        )
        self.assertEqual(active[50]["FloorType"], "Normal")
        self.assertEqual(active[1500], floors[1500])
        self.api({"revision": 4, "level": 80}, "/enemy-level")
        choose(51, 5, None)
        self.assertEqual(self.api(suffix="/boards/51")["modifiedFloors"], [1, 1500])
        active = served()
        self.assertEqual(active[50], dict(floors[50], StandardLevel=79))
        self.assertEqual(active[1499]["StandardLevel"], 199)
        choose(1500, 6, None)
        choose(1, 7, None)
        self.assertIsNone(self.api(suffix="/boards/1500")["custom"])
        self.api({"revision": 8, "level": None}, "/enemy-level")
        self.assertEqual(served(), floors)
        edited = [dict(units[0], elite=None), dict(units[1], elite=18)]
        choose(1, 9, {"units": edited, "level": None})
        self.assertEqual(self.api(suffix="/boards/1")["custom"]["units"], edited)
        self.assertEqual(
            served()[0]["Monsters"],
            [
                {"Position": 20, "MonsterId": 10},
                {"Position": 4, "MonsterId": 10, "Options": [{"OptionId": 18, "Level": 1}]},
            ],
        )
        edited[0].update(position=1, elite=18)
        choose(1, 10, {"units": edited, "level": None})
        self.assertEqual(
            served()[0]["Monsters"][0],
            {"Position": 1, "MonsterId": 10, "Options": [{"OptionId": 18, "Level": 1}]},
        )
        choose(1, 11, None)
        self.assertEqual(self.api(suffix="/boards")["modifiedFloors"], [])
        self.assertEqual(served(), floors)
        self.assertEqual(path.read_bytes(), source)
        self.assertEqual(self.profile(), self.original)

    def test_choose_next_floor_preserves_save_and_survives_reopening(self):
        state = self.api()
        self.assertEqual((state["clearedFloor"], state["nextFloor"]), (1340, 1341))
        self.assertEqual(state["floors"], [1, 1341, 1400, 1500])
        self.api(dict(version=state["version"], nextFloor=1341))
        self.assertEqual(self.profile(), self.original)
        for target in (1500, 1, 1341):
            state = self.api()
            self.api(dict(version=state["version"], nextFloor=target))
            self.assertEqual(self.api()["nextFloor"], target)
            self.original["UserProgress"]["TowerInfinity"]["Floor"] = target - 1
            self.original["UserProgress"]["Cas"] += 1
            self.assertEqual(self.profile(), self.original)

    def test_invalid_locked_stale_or_exhausted_updates_preserve_progress(self):
        state = self.api()
        body = dict(version=state["version"], nextFloor=1500)
        for value in (0, -1, 1501, 1499, True, "1400", 1.5):
            with self.subTest(value=value), self.assertRaises(HTTPError) as error:
                self.api(dict(body, nextFloor=value))
            self.assertEqual(error.exception.code, 400)
        with StateLock(self.root):
            self.assertFalse(self.api()["writable"])
            with self.assertRaises(HTTPError) as error:
                self.api(body)
            self.assertEqual(error.exception.code, 423)
        self.assertEqual(self.profile(), self.original)
        self.original["UserProgress"]["TowerInfinity"]["Floor"] = 1500
        self.original["UserProgress"]["Cas"] = MAX_REVISION
        self.store_original()
        state = self.api()
        self.assertEqual(state["nextFloor"], 1501)
        with self.assertRaises(HTTPError) as stale:
            self.api(body)
        self.assertEqual(stale.exception.code, 409)
        with self.assertRaises(HTTPError) as exhausted:
            self.api(dict(body, version=state["version"]))
        self.assertEqual(exhausted.exception.code, 400)
        self.assertEqual(self.profile(), self.original)
