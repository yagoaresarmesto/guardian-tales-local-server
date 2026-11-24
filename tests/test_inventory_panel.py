# SPDX-License-Identifier: Apache-2.0
"""Exercise the local panel against a synthetic catalog and disposable working save."""

import base64
import json
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.andras_trial_static import pack_rows
from guardian_tales.basecamp import MASTERY_POINTS
from guardian_tales.inventory_panel import server
from guardian_tales.inventory_panel.equipment import english_inventory_names
from guardian_tales.inventory_panel.equipment_ribbons import (
    completed_weapon_books,
    equipment_ribbons,
)
from guardian_tales.inventory_panel.server import InventoryServer
from guardian_tales.raid_static import compress, digest
from guardian_tales.reference import ReferenceData
from guardian_tales.snapshots import CLIENT
from guardian_tales.state_lock import StateLock


def prepare_inventory(root):
    pool = dict(OptionId=7, Probability=1, MinLevel=1, MaxLevel=3)
    option = dict(OptionId=7, Level=1, Locked=False)
    catalog = {
        "items": [
            dict(Id=1, Name="test_ticket", Type="ticket", MaxCount=10),
            dict(Id=2, Name="test_card", Type="card"),
            dict(Id=6, Name="exp_hammer_1_rare", Type="enhancehammer", Level=19, Rarity=1),
            dict(Id=7, Name="limitbreak_hammer_legend", Type="limitbreakhammer", Rarity=3),
            dict(
                Id=8, Name="limitbreak_hammer_epic", Type="limitbreakhammer", Rarity=4, MaxCount=6
            ),
            dict(Id=9, Name="hammer_box", Type="gachaitem"),
            dict(Id=10, Name="test_shield", Type="weapon", WeaponType="shield", Rarity=4),
            dict(Id=70014, Name="spiritStone", Type="goods"),
            dict(
                Id=110007,
                Name="summon_ticket",
                Type="ticket",
                MaxCount=40,
                SpriteName={"default": "ic_drone_controller"},
            ),
            dict(
                Id=110015,
                Name="selectable_summon_ticket",
                Type="ticket",
                SpriteName={"default": "ic_drone_controller_2"},
            ),
            dict(
                Id=3,
                Name="test_ring",
                Type="weapon",
                WeaponType="accessory",
                Rarity=4,
                Options=[pool],
                MinOptions=1,
                MaxOptions=1,
            ),
            dict(
                Id=4,
                Name="test_relic",
                Type="relic",
                OriginRarity=4,
                BaseOptions=[[pool]],
                ChangeOptions=[[pool]],
            ),
            dict(
                Id=5,
                Name="test_sword",
                Type="weapon",
                WeaponType="onehandsword",
                Rarity=4,
                ExclusiveCharacterId=1,
                Options=[pool],
                MinOptions=1,
                MaxOptions=1,
                EngraveRandomOptions=[dict(OptionId=8, Level=n) for n in (15, 9, 3)],
                EngraveStaticOptions=[dict(OptionId=7, Level=1)],
            ),
        ],
        "heroes": [
            dict(Id=1, OriginId=1, Rank=2, PortraitAssetName="swordsman"),
            dict(Id=2, OriginId=1, Rank=6, PortraitAssetName="swordsman_myth"),
            dict(Id=3, OriginId=1, Rank=4, PortraitAssetName="swordsman"),
            dict(Id=4, OriginId=4, Rank=2, PortraitAssetName="archer"),
        ],
        "buffs": [],
        "options": [
            dict(
                Id=10,
                Name="test_warrior_atk",
                Class="TotalAttackScale",
                CoopClassType="Melee",
                AttackScaleAdd=0.001,
            ),
            dict(Id=7, Name="relic_base_hp_scale", Class="HpScale", HpScaleAdd=0.01),
            dict(Id=8, Name="test_atk", Class="TotalAttackScale", AttackScaleAdd=0.01),
        ],
        "guardianlevel": {
            "GuardianSkill": [dict(SkillId=101, SkillCategoryId=1, OptionId=[10])],
            "GuardianSkillLevel": [
                dict(SkillLevel=1, OptionLevel=1),
                dict(SkillLevel=11, OptionLevel=21),
            ],
        },
        "weaponenhance": {
            "Constants": dict(
                WeaponMaxLimitBreak=3,
                WeaponEngravingCeiling=3,
                WeaponEngravingLevelRequirement=2,
                WeaponLimitBreakCoef=3,
                WeaponEngraveCoef=15,
                WeaponMythCoef=20,
            ),
            "LevelExps": [dict(Level=i, TotalExps=50 * (i + 1)) for i in range(150)],
            "WeaponEngraveOptionProbability": [
                dict(CeilingCount=i, OptionWeights=weights)
                for i, weights in enumerate(([1, 1, 1], [1, 1, 1], [1, 0, 0]))
            ],
        },
        "__checksum__": {},
    }
    sword = next(item for item in catalog["items"] if item["Id"] == 5)
    catalog["items"].append(dict(sword, Id=50, Name="test_myth_sword", Rarity=5))
    records = []
    for key, value in catalog.items():
        content = json.dumps(value)
        records.extend((key, content, "1", digest(content.encode())))
    (root / "static_data_get.bin").write_bytes(compress(("\n".join(records) + "\n").encode()))
    profile = {
        "User": {
            "Id": 1,
            "Cas": 10,
            "Characters": [],
            "ItemWeapons": [
                dict(
                    Id=11,
                    ItemId=3,
                    Experience=0,
                    Locked=True,
                    Amount=1,
                    Options=[dict(option, OptionSource=0)],
                ),
                dict(
                    Id=15,
                    ItemId=5,
                    Experience=100,
                    LimitBreaks=1,
                    EngraveCeiling=0,
                    EngraveOptions=[],
                    Locked=True,
                    Amount=1,
                    Options=[dict(option, OptionSource=0)],
                ),
            ],
            "ItemMiscs": [
                dict(
                    Id=12,
                    ItemId=4,
                    Locked=False,
                    Amount=1,
                    RelicOptions=[dict(option, OptionSource=1), dict(option, OptionSource=2)],
                )
            ],
            "ItemStackables": [
                dict(Id=13, ItemId=1, Amount=5, Locked=False),
                dict(Id=14, ItemId=2, Amount=1, Locked=False),
                dict(Id=16, ItemId=6, Amount=11, Locked=False),
                dict(Id=17, ItemId=7, Amount=4, Locked=False),
                dict(Id=18, ItemId=8, Amount=2, Locked=True),
                dict(Id=19, ItemId=9, Amount=9, Locked=False),
                dict(Id=20, ItemId=8, Amount=1, Locked=False),
            ],
        }
    }
    database = root / "server.sqlite3"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "CREATE TABLE local_account (id INTEGER PRIMARY KEY, schema_version INTEGER, profile TEXT)"
        )
        db.execute("INSERT INTO local_account VALUES(1, 3, ?)", (json.dumps(profile),))
    return database


class InventoryStartupTests(unittest.TestCase):
    def test_native_english_cache_resolves_weapon_and_hero_and_prefers_exact_binding(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        refs = ReferenceData(root)
        specs = {42: {"Id": 42, "WeaponType": "basket", "NameWithoutRarity": "cwp_example"}}
        keys = {"cwp_example": 101, "name_example": 102}
        with patch(
            "guardian_tales.inventory_panel.equipment.binary_name_hash",
            side_effect=keys.__getitem__,
        ):
            for filename, title in (
                ("strings-bin-enUS", b"Example Basket"),
                ("andras-trial-strings-abc.bin", b"Updated Basket"),
            ):
                table = pack_rows([(1, 101, title), (2, 102, b"Basket Hero")])
                (root / filename).write_bytes(base64.b64decode(table))
                self.assertEqual(
                    english_inventory_names(refs, specs, "abc", {31: "name_example"}),
                    ({42: title.decode()}, {31: "Basket Hero"}),
                )

    def test_first_launch_installs_panel_art_and_next_launch_skips_pip(self):
        with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as config:
            requirements = tomllib.load(config)["project"]["optional-dependencies"]["panel-art"]
        with (
            patch.object(server, "display_readers_available", side_effect=[False, True, True]),
            patch.object(subprocess, "run") as install,
            redirect_stderr(StringIO()),
        ):
            server.ensure_display_readers()
            server.ensure_display_readers()
        (args,), kwargs = install.call_args
        install.assert_called_once()
        self.assertEqual(args[:3], [sys.executable, "-m", "pip"])
        self.assertEqual(args[args.index("--no-input") + 1 :], requirements)
        self.assertTrue(kwargs["check"])

    def test_failed_install_still_serves_panel_and_explains_retry(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(server, "display_readers_available", return_value=False),
            patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")),
            patch.object(server, "InventoryServer") as panel,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()) as errors,
        ):
            Path(directory, "server.sqlite3").touch()
            server.main(["--data-dir", directory])
        panel.return_value.serve_forever.assert_called_once()
        self.assertIn("placeholders", errors.getvalue())
        self.assertIn("retry", errors.getvalue())


class InventoryPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        database = prepare_inventory(self.root)
        self.server = self.enterContext(
            InventoryServer(0, database, ReferenceData(self.root), self.root)
        )
        thread = Thread(target=self.server.serve_forever, args=(0.02,))
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.shutdown)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def call(self, path, body=None, **headers):
        request = Request(
            self.origin + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Origin": self.origin, "Content-Type": "application/json", **headers},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response) if path.startswith("/api/") else response.read()

    def test_exclusive_hero_is_independent_of_weapon_copy_rarity(self):
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            profile = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            weapons = profile["User"]["ItemWeapons"]
            weapons.append(dict(weapons[1], Id=99, ItemId=50))
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        for path in ("/api/game/equipment", "/api/inventory"):
            with self.subTest(path=path):
                rows = {row["id"]: row for row in self.call(path)["rows"]}
                self.assertIsNone(rows[11]["exclusiveHero"])
                self.assertEqual((rows[15]["exclusiveHero"], rows[15]["stars"]), (1, 5))
                self.assertEqual((rows[99]["exclusiveHero"], rows[99]["stars"]), (1, 6))

    def test_hero_face_prefers_native_myth_and_falls_back_to_linked_hero(self):
        with patch("guardian_tales.inventory_panel.hero_portraits.PORTRAITS") as atlas:
            atlas.read.side_effect = lambda refs, *, frame: frame.encode()
            self.assertEqual(self.call("/hero-face/1.png"), b"swordsman_myth")
            self.assertEqual(self.call("/hero-face/3.png"), b"swordsman_myth")
            self.assertEqual(self.call("/hero-face/4.png"), b"archer")
            atlas.read.side_effect = [FileNotFoundError(), b"swordsman"]
            self.assertEqual(self.call("/hero-face/1.png"), b"swordsman")
            self.assertEqual(atlas.read.call_args.kwargs["frame"], "swordsman")
            with self.assertRaises(HTTPError) as missing:
                self.call("/hero-face/999.png")
            self.assertEqual(missing.exception.code, 404)
            missing.exception.close()

    def test_views_and_referenced_static_assets(self):
        import re

        for section in ("equipment", "relics", "consumables", "mastery", "account"):
            page = self.call("/" + section)
            self.assertIn(b'lang="en"', page)
            self.assertIn(b'href="/account"', page)
            self.assertIn(f'href="/{section}" aria-current="page"'.encode(), page)
            self.assertEqual(page.count(b'aria-current="page"'), 1)
            self.assertEqual(b'id="preview-link"' in page, section == "equipment")
            for asset in re.findall(rb'(?:href|src)="(/[^"]+\.(?:css|js))"', page):
                self.assertTrue(self.call(asset.decode()))
        equipment = self.call("/equipment")
        for alias in ("/", "/equipment/preview", "/items", "/necklaces"):
            self.assertEqual(self.call(alias), equipment)
        with self.assertRaises(HTTPError) as missing_art:
            self.call("/mastery-training.png")
        self.assertEqual(missing_art.exception.code, 404)
        self.assertTrue(self.call("/inventory-dom.js"))
        self.assertTrue(self.call("/equipment-options.js"))

    def test_controller_icons_prefer_item_art_and_fall_back_to_the_exact_ui_frame(self):
        module = "guardian_tales.inventory_panel.catalog"
        with (
            patch(module + ".ICONS") as items,
            patch(module + ".UI") as ui,
            patch(module + ".inventory_icon", side_effect=lambda png: png),
        ):
            items.read.side_effect = [b"regular icon", FileNotFoundError(), FileNotFoundError()]
            ui.read.side_effect = [b"selectable icon", FileNotFoundError()]
            self.assertEqual(self.call("/icon/110007.png"), b"regular icon")
            items.read.assert_called_once_with(
                self.server.catalog.refs, frame="ic_drone_controller"
            )
            ui.read.assert_not_called()
            self.assertEqual(self.call("/icon/110015.png"), b"selectable icon")
            ui.read.assert_called_once_with(self.server.catalog.refs, frame="ic_drone_controller_2")
            with self.assertRaises(HTTPError) as missing:
                self.call("/icon/110015.png")
            self.assertEqual(missing.exception.code, 404)

    def seed_wallet(self):
        (self.root / "stamina_purchase_catalog.json").write_text(
            json.dumps(
                dict(amount_per_charge=50, gem_prices=[100], max_storage=3000, daily_limit=1)
            )
        )
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            profile = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            profile["User"].update(
                Name="Player",
                HashTag="00001",
                ItemIdCounter=20,
                Assets=[
                    dict(Id=70001, Amount=5, Spent=-10),
                    dict(Id=70003, Amount=8, Spent=9),
                    dict(Id=70006, Amount=90, Spent=12, MaxAdj=27, NextCharge="saved timer"),
                    dict(Id=70032, Amount=2990, Spent=8),
                ],
            )
            profile["GuildMember"] = dict(UserId=1, Name="Player", HashTag="00001", Cas=4)
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            db.execute("CREATE TABLE prologue_selection (id INTEGER PRIMARY KEY)")
            db.execute("INSERT INTO prologue_selection VALUES (1)")
        return profile

    def test_account_identity_and_separate_wallet_caps_apply_once(self):
        original = self.seed_wallet()
        path = "/api/game/account"
        view = self.call(path)
        self.assertTrue(view["ready"])
        body = dict(
            version=view["version"],
            name="Knight",
            tag="#0ab01",
            add=dict(gold=99_999_995, freeGems=99_999_992, paidGems=100_000_000, coffee=10),
        )
        with StateLock(self.root):
            self.assertFalse(self.call(path)["writable"])
            with self.assertRaises(HTTPError) as locked:
                self.call(path, body)
            self.assertEqual(locked.exception.code, 423)
        result = self.call(path, body)
        self.assertEqual(result["tag"], "0AB01")
        self.assertEqual(
            {w["key"]: w["balance"] for w in result["wallet"]},
            dict(gold=100_000_000, freeGems=100_000_000, paidGems=100_000_000, coffee=3000),
        )
        with self.assertRaises(HTTPError) as repeated:
            self.call(path, body)
        self.assertEqual(repeated.exception.code, 409)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
        user = original["User"]
        user.update(Name="Knight", HashTag="0AB01", Cas=user["Cas"] + 1)
        for index, amount in [(0, 100_000_000), (1, 100_000_000), (3, 3000)]:
            user["Assets"][index]["Amount"] = amount
        user["Assets"].append(
            dict(Id=70002, Amount=100_000_000, Spent=0, MaxAdj=0, NextCharge=None)
        )
        original["GuildMember"].update(Name="Knight", HashTag="0AB01", Cas=5)
        self.assertEqual(saved, original)
        no_op = self.call(
            path, dict(version=result["version"], name="Knight", tag="#0ab01", add={})
        )
        self.assertEqual(no_op, result)

    def test_account_sets_summoning_totals_across_stacks_and_allocates_missing_tickets(self):
        profile = self.seed_wallet()
        user = profile["User"]
        user["ItemIdCounter"] = 22
        user["ItemStackables"].extend(
            [
                dict(Id=22, ItemId=110007, Amount=8, Locked=True),
                dict(Id=21, ItemId=110007, Amount=5, Locked=False),
            ]
        )
        user["Assets"].append(dict(Id=70014, Amount=300, Spent=17))
        path = "/api/game/account"
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        view = self.call(path)
        self.assertEqual([r["balance"] for r in view["summoning"]], [300, 13, 0])
        body = dict(
            version=view["version"],
            name=view["name"],
            tag=view["tag"],
            add={},
            set=dict(mileage=0, summonControllers=6, selectableControllers=10),
        )
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(path, body)
        self.assertEqual(locked.exception.code, 423)
        result = self.call(path, body)
        self.assertEqual([r["balance"] for r in result["summoning"]], [0, 6, 10])
        with self.assertRaises(HTTPError) as stale:
            self.call(path, body)
        self.assertEqual(stale.exception.code, 409)
        body["version"] = result["version"]
        self.assertEqual(self.call(path, body), result)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])[
                "User"
            ]
        self.assertEqual(saved["Assets"][-1], dict(Id=70014, Amount=0, Spent=17))
        self.assertEqual(saved["ItemStackables"][:-2], user["ItemStackables"][:-2])
        self.assertEqual(
            saved["ItemStackables"][-2], dict(Id=22, ItemId=110007, Amount=6, Locked=True)
        )
        ticket = saved["ItemStackables"][-1]
        self.assertEqual((ticket["Id"], ticket["ItemId"], ticket["Amount"]), (23, 110015, 10))
        self.assertEqual(saved["ItemIdCounter"], 23)
        body["set"] = dict(mileage=2_147_483_647, summonControllers=40, selectableControllers=0)
        self.call(path, body)
        self.assertEqual(
            [r["balance"] for r in self.call(path)["summoning"]], [2_147_483_647, 40, 0]
        )
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])[
                "User"
            ]
        self.assertEqual(
            saved["ItemStackables"],
            user["ItemStackables"][:-2] + [dict(Id=22, ItemId=110007, Amount=40, Locked=True)],
        )
        self.assertEqual(saved["ItemIdCounter"], 23)

    def test_account_rejects_invalid_edits_without_partial_writes(self):
        self.seed_wallet()
        path = "/api/game/account"
        view = self.call(path)
        body = dict(version=view["version"], name="Renamed", tag="00123", add={})
        for change in [
            dict(name="x"),
            dict(name="😀" * 6),
            dict(tag="1234"),
            dict(tag=" A001"),
            dict(tag="ßAAAA"),
            dict(add={"gold": 1, "coffee": 11}),
            dict(add={"freeGems": 99_999_993}),
            dict(add={"paidGems": 100_000_001}),
            dict(add={"gold": 99_999_996}),
            dict(add={"gold": -1}),
            dict(add={"coffee": True}),
            dict(add={"chargedCoffee": 1}),
            dict(set={"mileage": -1}),
            dict(set={"mileage": 2_147_483_648}),
            dict(add={"gold": 1}, set={"summonControllers": 10, "selectableControllers": False}),
            dict(set={"summonControllers": 41}),
            dict(set={"selectableControllers": 4.5}),
            dict(set={"gold": 10}),
            dict(add={"mileage": 1}),
            dict(set=[]),
        ]:
            with self.subTest(change=change), self.assertRaises(HTTPError) as invalid:
                self.call(path, body | change)
            self.assertEqual(invalid.exception.code, 400)
        self.assertEqual(self.call(path), view)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            db.execute("DELETE FROM prologue_selection")
        with self.assertRaises(HTTPError) as early:
            self.call(path, body)
        self.assertEqual(early.exception.code, 400)
        self.assertFalse(self.call(path)["ready"])

    def test_account_keeps_legacy_balances_and_checks_guild_owner(self):
        profile = self.seed_wallet()
        (self.root / "stamina_purchase_catalog.json").unlink()
        profile["User"]["Assets"][0]["Amount"] = 100_000_001
        profile["GuildMember"]["UserId"] = 2
        path = "/api/game/account"
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        state = self.call(path)
        body = dict(version=state["version"], name=state["name"], tag=state["tag"], add={})
        for change in (dict(tag="0A123", add={"freeGems": 1}), dict(add={"coffee": 1})):
            with self.assertRaises(HTTPError) as invalid:
                self.call(path, body | change)
            self.assertEqual(invalid.exception.code, 400)
            self.assertEqual(self.call(path), state)
        updated = self.call(path, body | {"add": {"freeGems": 1}})
        balances = {item["key"]: item for item in updated["wallet"]}
        self.assertEqual(balances["gold"]["balance"], 100_000_001)
        self.assertEqual(balances["freeGems"]["balance"], 9)
        self.assertIsNone(balances["coffee"]["limit"])

    def seed_mastery(self, balance=500):
        skills = {str(group * 100 + index): group for group in range(1, 5) for index in (1, 2)}
        catalog = dict(
            client=CLIENT, portal_specs=[9001], skills=skills, level_costs=list(range(2, 14))
        )
        (self.root / "guardian_mastery_catalog.json").write_text(json.dumps(catalog))
        village = dict(UserId=1, Buildings=[dict(SpecId=9001, Status=2)])
        reads = {"/lobby-village/enter": {"value": {"UserLobbyVillage": village}}}
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            db.execute("CREATE TABLE imported_account (id INTEGER PRIMARY KEY, startup_reads TEXT)")
            db.execute("INSERT INTO imported_account VALUES(1,?)", (json.dumps(reads),))
            profile = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            user = profile["User"]
            user.update(
                GuardianMasteryLevel=96,
                Options={
                    "GuardianMastery": {
                        "GuardianMasterySkill": dict.fromkeys(skills, 12),
                        "SkillNextResetTime": "2099-01-01T00:00:00+00:00",
                    }
                },
                Assets=[
                    dict(Id=MASTERY_POINTS, Amount=balance, Spent=719),
                    dict(Id=70003, Amount=0, Spent=20),
                ],
            )
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        return profile, dict.fromkeys(skills, 12)

    def test_mastery_card_uses_catalog_option_rank_and_next_level_cost(self):
        self.seed_mastery()
        state = self.call("/api/game/mastery")
        skill = next(skill for skill in state["skills"] if skill["id"] == "101")
        self.assertEqual((skill["className"], skill["name"]), ("Warrior", "ATK"))
        self.assertEqual(skill["bonuses"], {"0": 0, "1": 0.1, "11": 2.1})
        self.assertEqual(state["levelCosts"][11], 13)

    def test_mastery_full_reset_capped_refund_and_rebuild_from_zero(self):
        path = "/api/game/mastery"
        before, maximum = self.seed_mastery()
        state = self.call(path)
        self.assertEqual(
            (state["maxInvestment"], state["refundCeiling"], state["maxLevel"]), (720, 733, 12)
        )
        reset = dict(version=state["version"], levels=dict.fromkeys(maximum, 0))
        with StateLock(self.root):
            self.assertEqual(self.call(path + "/preview", reset)["excess"], 487)
            with self.assertRaises(HTTPError) as locked:
                self.call(path, reset)
            self.assertEqual(locked.exception.code, 423)
        self.assertEqual(self.call(path), state)
        result = self.call(path, reset)
        self.assertEqual((result["balance"], result["delta"], result["excess"]), (733, -720, 487))
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
        expected = before["User"]
        expected["Cas"] += 1
        expected["GuardianMasteryLevel"] = 0
        expected["Options"]["GuardianMastery"]["GuardianMasterySkill"] = {}
        expected["Assets"][0].update(Amount=733, Spent=-1)
        self.assertEqual(saved, before)
        with self.assertRaises(HTTPError) as stale:
            self.call(path, reset)
        self.assertEqual(stale.exception.code, 409)
        self.assertEqual(
            self.call(path, dict(version=result["version"], levels=maximum))["balance"], 13
        )

    def test_mastery_validates_final_distribution_and_settles_only_net_cost(self):
        path = "/api/game/mastery"
        _, maximum = self.seed_mastery(balance=1000)
        initial = self.call(path)

        def body(levels):
            return dict(version=initial["version"], levels=levels)

        for target in (
            dict(maximum, extra=0),
            {},
            dict(maximum, **{"101": True}),
            dict(maximum, **{"101": 13}),
            dict(dict.fromkeys(maximum, 0), **{"101": 11}),
        ):
            with self.subTest(target=target), self.assertRaises(HTTPError) as invalid:
                self.call(path, body(target))
            self.assertEqual(invalid.exception.code, 400)
        self.assertEqual(self.call(path), initial)
        self.assertFalse(self.call(path, body(maximum))["changed"])
        lowered = dict(maximum, **{"101": 11})
        result = self.call(path, body(lowered))
        self.assertEqual((result["balance"], result["excess"]), (1000, 13))
        swap = dict(maximum, **{"102": 11})
        move = self.call(path, dict(version=result["version"], levels=swap))
        self.assertEqual((move["balance"], move["delta"], move["excess"]), (1000, 0, 0))
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            profile = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            profile["User"]["Assets"][0]["Amount"] = 0
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        state = self.call(path)
        with self.assertRaises(HTTPError) as insufficient:
            self.call(path, dict(version=state["version"], levels=maximum))
        self.assertEqual(insufficient.exception.code, 400)
        self.assertEqual(self.call(path), state)

    def test_consumable_filter_limits_lock_and_stale_edits(self):
        path = "/api/game/consumables"
        (stack,) = self.call(path)["rows"]
        self.assertEqual(stack["id"], 13)
        edit = dict(id=stack["id"], version=stack["version"], amount=9)
        with StateLock(self.root):
            self.assertFalse(self.call("/api/game/status")["writable"])
            with self.assertRaises(HTTPError) as locked:
                self.call(path, edit)
            self.assertEqual(locked.exception.code, 423)
        for body, origin, status in (
            (edit, "http://example.invalid", 403),
            (dict(edit, amount=11), self.origin, 400),
        ):
            with self.assertRaises(HTTPError) as refused:
                self.call(path, body, Origin=origin)
            self.assertEqual(refused.exception.code, status)
        self.assertEqual(self.call(path)["rows"][0]["amount"], 5)
        self.assertEqual(self.call(path, edit)["amount"], 9)
        with self.assertRaises(HTTPError) as stale:
            self.call(path, dict(edit, amount=8))
        self.assertEqual(stale.exception.code, 409)
        self.assertEqual(self.call(path)["rows"][0]["amount"], 9)

    def test_enhance_edits_only_the_selected_owned_hammer_stack(self):
        path = "/api/game/equipment/hammers"
        equipment = self.call("/api/game/equipment")
        hammers = equipment["hammers"]
        self.assertEqual([h["id"] for h in hammers], [16, 17, 18, 20])
        self.assertEqual([h["rarityName"] for h in hammers], ["Rare", "Legend", "Epic", "Epic"])
        self.assertEqual((hammers[0]["name"], hammers[0]["level"]), ("Strengthening Hammer", 20))
        self.assertEqual(hammers[2]["name"], "Epic Limit Breaking Hammer")
        (ticket,) = self.call("/api/game/consumables")["rows"]
        edit = dict(id=18, version=hammers[2]["version"], amount=6)
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(path, edit)
        self.assertEqual(locked.exception.code, 423)
        for endpoint, request in (
            (path, dict(edit, amount=7)),
            (path, dict(edit, amount=0)),
            (path, dict(edit, amount=True)),
            (path, dict(id=ticket["id"], version=ticket["version"], amount=2)),
            ("/api/game/consumables", edit),
        ):
            with self.subTest(request=request), self.assertRaises(HTTPError) as invalid:
                self.call(endpoint, request)
            self.assertEqual(invalid.exception.code, 400)
        saved = self.call(path, edit)
        with self.assertRaises(HTTPError) as stale:
            self.call(path, dict(edit, amount=3))
        self.assertEqual(stale.exception.code, 409)
        after = self.call("/api/game/equipment")
        self.assertEqual(after["revision"], equipment["revision"] + 1)
        self.assertEqual(after["rows"], equipment["rows"])
        self.assertEqual(after["hammers"], [*hammers[:2], dict(hammers[2], **saved), hammers[3]])
        self.assertTrue(after["hammers"][2]["locked"])
        self.assertEqual(self.call("/api/game/consumables")["rows"], [ticket])

    def test_equipment_and_relic_respect_catalog_and_preserve_other_slots(self):
        path = "/api/game/equipment"
        state = self.call(path)
        item = state["rows"][0]
        body = dict(
            id=item["id"], version=item["version"], revision=state["revision"], options={"7": 4}
        )
        with self.assertRaises(HTTPError) as invalid:
            self.call(path, body)
        self.assertEqual(invalid.exception.code, 400)
        self.call(path, dict(body, options={"7": 3}, lockedValues={"7": 3}))
        (row,) = self.call(path)["rows"][0]["options"]
        self.assertEqual((row["Level"], row["Locked"]), (3, True))
        path = "/api/game/relics"
        state = self.call(path)
        (relic,) = state["copies"]
        change = dict(group="main", slot=0, option=7, level=3)
        body = dict(
            id=relic["id"], revision=state["revision"], version=relic["version"], changes=[change]
        )
        with self.assertRaises(HTTPError) as invalid:
            self.call(path, dict(body, changes=[dict(change, level=4)]))
        self.assertEqual(invalid.exception.code, 400)
        self.call(path, body)
        (relic,) = self.call(path)["copies"]
        self.assertEqual((relic["main"][0]["Level"], relic["bonus"][0]["Level"]), (3, 1))

    def weapon_edit(self, **changes):
        state = self.call("/api/game/equipment")
        item = state["rows"][1]
        return dict(id=item["id"], version=item["version"], revision=state["revision"], **changes)

    def test_accessory_limit_breaks_are_increase_only_without_engraving(self):
        path = "/api/game/equipment"
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            original = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
        for before, target in [(0, 1), (1, 3)]:
            state = self.call(path)
            ring = state["rows"][0]
            self.assertEqual(ring["breaks"], before)
            self.assertEqual(ring["progression"], dict(maxBreaks=3, engraving=None))
            body = dict(id=ring["id"], revision=state["revision"], version=ring["version"])
            for invalid in (
                dict(breaks=0),
                dict(breaks=4),
                dict(breaks=3, engraving=dict(count=1, level=9)),
            ):
                with self.assertRaises(HTTPError) as error:
                    self.call(path, dict(body, progression=invalid))
                self.assertEqual(error.exception.code, 400)
            self.call(path, dict(body, progression=dict(breaks=target)))
        state = self.call(path)
        ring = state["rows"][0]
        self.assertEqual(ring["breaks"], 3)
        self.assertIsNone(ring["progression"])
        with self.assertRaises(HTTPError) as capped:
            self.call(
                path,
                dict(
                    id=ring["id"],
                    revision=state["revision"],
                    version=ring["version"],
                    progression=dict(breaks=4),
                ),
            )
        self.assertEqual(capped.exception.code, 400)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
        original["User"]["ItemWeapons"][0]["LimitBreaks"] = 3
        original["User"]["Cas"] += 2
        self.assertEqual(saved, original)

    def test_free_max_level_matches_saved_cap_rarity_breaks_and_first_engraving(self):
        path = "/api/game/equipment"
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            original = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            user = original["User"]
            user["Unlocked"] = {"MaxLevel": {"Weapon": 99}}
            ring, sword = user["ItemWeapons"]
            ring["LimitBreaks"] = 3
            myth = dict(sword, Id=99, ItemId=50)
            shield = dict(ring, Id=100, ItemId=10, LimitBreaks=1, Options=None)
            user["ItemWeapons"].extend([myth, shield])
            db.execute("UPDATE local_account SET profile=?", (json.dumps(original),))

        for item, upgrades, level in [
            (ring, {}, 109),
            (shield, {}, 103),
            (shield, dict(breaks=3), 109),
            (sword, dict(breaks=3, engraving=dict(count=1, level=9)), 124),
            (myth, dict(breaks=3), 129),
            (myth, dict(engraving=dict(count=1, level=9)), 144),
            (myth, dict(engraving=dict(count=2, level=15)), None),
        ]:
            state = self.call(path)
            row = next(r for r in state["rows"] if r["id"] == item["Id"])
            changes = dict(upgrades)
            if item is shield:
                self.assertIsNone(row["progression"]["engraving"])
            if level:
                targets = row["progression"]["levels"]
                offered = (
                    targets["engraved"]
                    if "engraving" in upgrades
                    else targets["byBreaks"][str(upgrades.get("breaks", row["breaks"]))]
                )
                self.assertEqual(offered, level)
                changes["maxLevel"] = level
                item["Experience"] = (level - 1) * 50
            if "breaks" in upgrades:
                item["LimitBreaks"] = upgrades["breaks"]
            if "engraving" in upgrades:
                item.update(
                    EngraveCeiling=upgrades["engraving"]["count"],
                    EngraveOptions=[dict(OptionId=8, Level=upgrades["engraving"]["level"])],
                )
            body = dict(
                id=row["id"],
                revision=state["revision"],
                version=row["version"],
                progression=changes,
            )
            self.call(path, body)
            user["Cas"] += 1
            saved = next(r for r in self.call(path)["rows"] if r["id"] == item["Id"])
            self.assertEqual(saved["level"], level or 144)
            if item is shield and level == 109:
                self.assertIsNone(saved["progression"])
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            self.assertEqual(
                json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), original
            )

    def test_max_level_rejects_stale_story_cap_and_overcap_edits_atomically(self):
        path = "/api/game/equipment"
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            profile = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            profile["User"]["Unlocked"] = {"MaxLevel": {"Weapon": 49}}
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        edit = self.weapon_edit(progression=dict(maxLevel=53), options={"7": 2})
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(path, edit)
        self.assertEqual(locked.exception.code, 423)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            profile["User"]["Unlocked"]["MaxLevel"]["Weapon"] = 50
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        for level in (True, 53, 150, 100000):
            with self.subTest(level=level), self.assertRaises(HTTPError) as invalid:
                self.call(path, dict(edit, progression=dict(maxLevel=level)))
            self.assertEqual(invalid.exception.code, 400)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            self.assertEqual(
                json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), profile
            )
        self.call(path, dict(edit, progression=dict(maxLevel=54)))
        with self.assertRaises(HTTPError) as capped:
            self.call(path, self.weapon_edit(progression=dict(maxLevel=54)))
        self.assertEqual(capped.exception.code, 400)

    def test_upgrades_and_options_apply_together_with_native_tiers(self):
        path = "/api/game/equipment"
        state = self.call(path)
        stack = self.call("/api/game/consumables")["rows"][0]
        body = self.weapon_edit(
            progression=dict(breaks=3, engraving=dict(count=1, level=9)), options={"7": 2}
        )
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(path, body)
        self.assertEqual(locked.exception.code, 423)
        self.assertEqual(self.call(path, body)["revision"], state["revision"] + 1)
        with self.assertRaises(HTTPError) as stale:
            self.call(path, body)
        self.assertEqual(stale.exception.code, 409)
        item = self.call(path)["rows"][1]
        engraving = item["progression"]["engraving"]
        self.assertEqual(
            (item["breaks"], item["options"][0]["Level"], engraving["count"], engraving["level"]),
            (3, 2, 1, 9),
        )
        self.assertEqual(engraving["tiers"], {"2": [9, 15], "3": [15]})
        self.call(path, self.weapon_edit(progression=dict(engraving=dict(count=3, level=15))))
        self.assertEqual(self.call(path)["rows"][1]["progression"]["engraving"]["tiers"], {})
        self.assertEqual(self.call("/api/game/consumables")["rows"][0], stack)

    def test_invalid_upgrades_roll_back_entire_edit(self):
        path = "/api/game/equipment"
        original = self.call(path)
        for upgrade in (
            dict(breaks=0),
            dict(breaks=4),
            dict(breaks=True),
            dict(engraving=dict(count=1, level=9)),
            dict(breaks=3, engraving=dict(count=1, level=10)),
            dict(breaks=3, engraving=dict(count=3, level=9)),
            dict(breaks=3, engraving=dict(count=4, level=15)),
        ):
            with self.subTest(upgrade=upgrade), self.assertRaises(HTTPError) as invalid:
                self.call(path, self.weapon_edit(progression=upgrade, options={"7": 2}))
            self.assertEqual(invalid.exception.code, 400)
        self.assertEqual(self.call(path), original)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            profile = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            profile["User"]["ItemWeapons"][1]["Experience"] = 99
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        with self.assertRaises(HTTPError) as invalid:
            self.call(
                path, self.weapon_edit(progression=dict(breaks=3, engraving=dict(count=1, level=9)))
            )
        self.assertEqual(invalid.exception.code, 400)
        self.call(path, self.weapon_edit(progression=dict(breaks=3)))
        self.assertFalse(self.call(path)["rows"][1]["progression"]["engraving"]["enoughExperience"])

    def test_imported_engraving_retains_native_fields_and_stops_at_best_roll(self):
        path = "/api/game/equipment"
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            profile = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
            item = profile["User"]["ItemWeapons"][1]
            item.update(
                LimitBreaks=3,
                EngraveCeiling=1,
                EngraveOptions=[dict(OptionId=8, Level=3, OptionSource=0, Locked=False)],
            )
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.call(path, self.weapon_edit(progression=dict(engraving=dict(count=2, level=15))))
        self.assertEqual(self.call(path)["rows"][1]["ribbons"], ["engraved-max"])
        preview = self.call("/api/inventory")["rows"]
        self.assertEqual(
            next(row["ribbons"] for row in preview if row["id"] == 15), ["engraved-max"]
        )
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
        self.assertEqual(
            saved["User"]["ItemWeapons"][1]["EngraveOptions"],
            [dict(OptionId=8, Level=15, OptionSource=0, Locked=False)],
        )
        with self.assertRaises(HTTPError) as invalid:
            self.call(path, self.weapon_edit(progression=dict(engraving=dict(count=3, level=15))))
        self.assertEqual(invalid.exception.code, 400)


class EquipmentRibbonTests(unittest.TestCase):
    def test_book_requires_all_tracked_rarities_and_their_linked_sets(self):
        base = dict(Type="weapon", WeaponType="bow", OriginRarity=2)
        specs = {
            12: dict(base, Rarity=2, EvolveTo={"Default": 13}),
            13: dict(base, Rarity=3, SortingNumber=-1, EvolveTo={"Default": 14}),
            14: dict(base, Rarity=4),
        }
        definitions = {
            "ItemMastery": {"Bow": []},
            "Collection": [
                dict(Id=11, ItemId=[13]),
                dict(Id=12, ItemId=[14]),
                dict(Id=13, ItemId=[12], VersionFrom={"KakaoGlobal": "v9.99"}),
            ],
        }
        saved = {"ItemCollections": {"12": 0, "14": 2}, "CustomCollections": [11]}
        self.assertEqual(completed_weapon_books(specs, definitions, saved), set())
        saved["CustomCollections"].append(12)
        self.assertEqual(completed_weapon_books(specs, definitions, saved), {12, 13, 14})
        saved["ItemCollections"]["14"] = -1
        self.assertEqual(completed_weapon_books(specs, definitions, saved), set())

    def test_exclusive_marks_reflect_engraving_option_and_collaboration(self):
        spec = dict(
            Id=15,
            ExclusiveCharacterId=8,
            Rarity=4,
            EngraveRandomOptions=[dict(OptionId=2, Level=6), dict(OptionId=2, Level=3)],
        )
        saved = dict(EngraveCeiling=0, EngraveOptions=[])
        self.assertEqual(equipment_ribbons(saved, spec, {15}), ["book-complete", "exclusive"])
        self.assertEqual(equipment_ribbons(saved, dict(spec, ExclusiveCharacterId=0), set()), [])
        collab = dict(spec, CollaborationId=1, Rarity=5)
        self.assertEqual(equipment_ribbons(saved, collab, set()), ["exclusive-collab"])
        saved.update(EngraveCeiling=1, EngraveOptions=[dict(OptionId=2, Level=3)])
        self.assertEqual(equipment_ribbons(saved, spec, set()), ["engraved"])
        self.assertEqual(equipment_ribbons(saved, collab, set()), ["engraved-collab"])
        saved["EngraveOptions"][0]["Level"] = 6
        self.assertEqual(equipment_ribbons(saved, spec, set()), ["engraved-max"])
        self.assertEqual(equipment_ribbons(saved, collab, set()), ["engraved-max"])
        # Match the first template tier even on a nonstandard custom weapon.
        spec["EngraveRandomOptions"].append(dict(OptionId=2, Level=9))
        self.assertEqual(equipment_ribbons(saved, spec, set()), ["engraved-max"])
