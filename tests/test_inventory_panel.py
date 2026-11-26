# SPDX-License-Identifier: Apache-2.0
"""Exercise the local panel against a synthetic catalog and disposable working save."""

import base64
import gzip
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from io import StringIO
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.andras_trial_static import pack_rows
from guardian_tales.awakening_catalog import Node, Tree
from guardian_tales.basecamp import MASTERY_POINTS
from guardian_tales.characters import new_character
from guardian_tales.inventory_panel import server
from guardian_tales.inventory_panel.equipment import english_inventory_names
from guardian_tales.inventory_panel.equipment_ribbons import (
    completed_weapon_books,
    equipment_ribbons,
)
from guardian_tales.inventory_panel.server import InventoryServer
from guardian_tales.panel_common.art_cache import cached_art
from guardian_tales.raid_static import compress, digest
from guardian_tales.reference import ReferenceData
from guardian_tales.service_control import register
from guardian_tales.snapshots import CLIENT, preserved_read
from guardian_tales.state_lock import StateLock
from guardian_tales.web_panel.server import WebPanel


def prepare_inventory(root):
    pool = dict(OptionId=7, Probability=1, MinLevel=1, MaxLevel=3)
    option = dict(OptionId=7, Level=1, Locked=False)
    catalog = {
        "items": [
            dict(Id=1, Name="test_ticket", Type="ticket", MaxCount=10),
            dict(Id=300, Name="test_jewel", Type="jewel"),
            dict(Id=2, Name="test_card", Type="card"),
            dict(Id=6, Name="exp_hammer_1_rare", Type="enhancehammer", Level=19, Rarity=1),
            dict(Id=7, Name="limitbreak_hammer_legend", Type="limitbreakhammer", Rarity=3),
            dict(
                Id=8, Name="limitbreak_hammer_epic", Type="limitbreakhammer", Rarity=4, MaxCount=6
            ),
            dict(Id=9, Name="hammer_box", Type="gachaitem"),
            dict(
                Id=10,
                Name="test_shield",
                Type="weapon",
                WeaponType="shield",
                Rarity=4,
                OriginRarity=4,
                Limited=False,
                SortingNumber=400,
                MinOptions=0,
                MaxOptions=0,
            ),
            dict(Id=70014, Name="spiritStone", Type="goods"),
            dict(Id=70004, Name="experience", Type="goods"),
            dict(Id=70028, Name="jewel_powder", Type="goods"),
            dict(Id=70034, Name="dream_mythstone", Type="goods", MaxCount=800),
            dict(Id=71001, Name="purple_coin_1", Type="goods"),
            dict(Id=71002, Name="purple_coin_2", Type="goods"),
            dict(Id=76005, Name="coop_expedition_coin_2", Type="goods"),
            dict(Id=77004, Name="ic_rogue_chess_coin_01_4", Type="goods"),
            dict(Id=80001, Name="evolve_stone_archer", Type="evolve_stone", StoneType="HeroEvolve"),
            dict(Id=80002, Name="evolve_stone_knight", Type="evolve_stone", StoneType="HeroEvolve"),
            dict(Id=81000, Name="evolve_stone_rare", Type="evolve_stone", StoneType="HeroEvolve"),
            dict(Id=85001, Name="myth_stone_archer", Type="evolve_stone", StoneType="HeroMyth"),
            dict(Id=85002, Name="myth_stone_knight", Type="evolve_stone", StoneType="HeroMyth"),
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
                OriginRarity=4,
                Summonable=True,
                Limited=False,
                Rarity=4,
                Options=[pool],
                MinOptions=1,
                MaxOptions=1,
            ),
            dict(
                Id=4,
                Name="test_relic",
                NameWithoutRarity="relic_scripture",
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
                OriginRarity=4,
                Summonable=True,
                Limited=False,
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
            dict(
                Id=1,
                OriginId=1,
                Rank=2,
                PortraitAssetName="swordsman",
                Playable=True,
                EvolvingStoneId=81000,
            ),
            dict(Id=2, OriginId=1, Rank=6, PortraitAssetName="swordsman_myth"),
            dict(
                Id=3,
                OriginId=1,
                Rank=4,
                PortraitAssetName="swordsman",
                Playable=True,
                EvolvingStoneId=81000,
            ),
            dict(
                Id=4,
                OriginId=4,
                Rank=2,
                PortraitAssetName="archer",
                Playable=True,
                EvolvingStoneId=80001,
            ),
            dict(
                Id=5,
                OriginId=5,
                Rank=2,
                PortraitAssetName="healer",
                Playable=True,
                EvolvingStoneId=81000,
            ),
        ],
        "buffs": [],
        "constants": {"DefaultInventoryLimit": 8, "DefaultRelicInventoryLimit": 3},
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
    catalog["items"].extend(
        [
            dict(sword, Id=51, Name="internal_weapon", Summonable=False, SortingNumber=-1),
            dict(sword, Id=52, Name="limited_weapon", Limited=True),
            dict(sword, Id=53, Name="npc_weapon", WeaponType="custom"),
            dict(sword, Id=54, Name="future_weapon", VersionFrom={"KakaoGlobal": "v999.0"}),
            dict(sword, Id=55, Name="invalid_weapon", MinOptions=3),
            dict(sword, Id=56, Name="eu_myth_sword", Rarity=5, Summonable=False),
        ]
    )
    collab_sword = dict(
        sword,
        Id=57,
        Name="collab_sword_epic",
        NameWithoutRarity="collab_sword",
        Limited=True,
        CollaborationId=6,
        Summonable=False,
        SortingNumber=101,
    )
    catalog["items"].extend(
        [
            dict(collab_sword, EvolveTo={"KakaoGlobal": 58}),
            dict(collab_sword, Id=58, Name="collab_sword_myth", Rarity=5),
            dict(collab_sword, Id=59, Name="collab_internal", SortingNumber=-1),
        ]
    )
    sword["EvolveTo"] = {"Default": 50, "KakaoGlobal": 56}
    relic = next(item for item in catalog["items"] if item["Id"] == 4)
    catalog["items"].extend(
        [
            dict(
                relic, Id=61, Name="scripture_normal", OriginRarity=0, BaseOptions=[[pool], [], []]
            ),
            dict(relic, Id=62, Name="internal_relic", NameWithoutRarity="internal"),
            dict(relic, Id=63, Name="future_relic", VersionFrom={"KakaoGlobal": "v999.0"}),
        ]
    )
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
            "guardian_tales.panel_common.labels.binary_name_hash",
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
            panel.return_value.server_port = 17661
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

    def test_dashboard_port_has_one_listener(self):
        with (
            self.assertRaises(OSError),
            WebPanel(ReferenceData(self.root), self.server.server_port),
        ):
            self.fail("A second dashboard bound the active inventory port")
        self.assertEqual(self.call("/api/backend")["instance"], self.server.instance)

    def test_artwork_on_reused_connection_after_gzipped_listing(self):
        brand = self.root / "brand.png"
        brand.write_bytes(b"first image")
        connection = self.enterContext(
            closing(HTTPConnection("127.0.0.1", self.server.server_port, timeout=5))
        )

        def get(path, headers=None):
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response, response.read()

        listing, body = get("/api/game/equipment", {"Accept-Encoding": "gzip"})
        self.assertIn("rows", json.loads(gzip.decompress(body)))
        self.assertEqual(listing.getheader("Cache-Control"), "no-store")
        socket = connection.sock
        self.assertIsNotNone(socket)

        image, body = get("/brand.png")
        self.assertEqual(body, b"first image")
        self.assertIsNone(image.getheader("Content-Encoding"))
        self.assertEqual(image.getheader("Cache-Control"), "private, max-age=900")
        etag = image.getheader("ETag")
        validator = {"If-None-Match": '"other", W/' + etag}
        fresh, body = get("/brand.png", validator)
        self.assertEqual((fresh.status, body, fresh.getheader("ETag")), (304, b"", etag))

        brand.write_bytes(b"new image")
        changed, body = get("/brand.png", validator)
        self.assertEqual((changed.status, body), (200, b"new image"))
        self.assertNotEqual(etag, changed.getheader("ETag"))
        state, _ = get("/api/game/equipment", {"If-None-Match": "*"})
        self.assertEqual((state.status, state.getheader("Cache-Control")), (200, "no-store"))
        missing, _ = get("/hero-face/999.png")
        self.assertEqual((missing.status, missing.getheader("Cache-Control")), (404, "no-store"))
        self.assertIs(socket, connection.sock)

    def test_rendered_art_cache_survives_reopen_and_rebuilds_stale_or_damaged_entries(self):
        source = self.root / "art.bundle"
        directory = self.root / "cache"
        with patch.dict(os.environ, LOCALAPPDATA=str(directory)):

            def render(stamp, data):
                return cached_art(source, "sprite", stamp, lambda: data)

            self.assertEqual(render(1, b"original"), b"original")
            self.assertEqual(render(1, b"unexpected"), b"original")
            self.assertEqual(render(2, b"updated"), b"updated")
            (entry,) = [path for path in directory.rglob("*") if path.is_file()]
            entry.write_bytes(entry.read_bytes()[:-1])
            self.assertEqual(render(2, b"repaired"), b"repaired")

        source.touch()
        with patch.dict(os.environ, LOCALAPPDATA=str(source)):
            self.assertEqual(render(3, b"uncached"), b"uncached")

    def test_open_reuses_the_running_inventory_service_for_this_save(self):
        with (
            register("inventory", self.server.database, self.server.server_port, lambda: None),
            patch.object(server, "InventoryServer") as create,
            patch.object(server, "ensure_display_readers") as prepare,
            patch.object(server.webbrowser, "open") as launch,
            redirect_stdout(StringIO()) as output,
        ):
            server.main(
                ["--data-dir", str(self.root), "--port", str(self.server.server_port), "--open"]
            )
        create.assert_not_called()
        prepare.assert_not_called()
        launch.assert_called_once_with(self.origin + "/")
        self.assertIn("already running", output.getvalue())

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

        for section in ("equipment", "relics", "heroes", "consumables", "mastery", "account"):
            page = self.call("/" + section)
            self.assertIn(b'lang="en"', page)
            self.assertIn(b'href="/account"', page)
            self.assertIn(b'href="/heroes"', page)
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
        self.assertTrue(self.call("/equipment-add.js"))
        self.assertTrue(self.call("/catalog-picker.js"))

    def test_hero_stars_follow_current_form_and_family(self):
        editor = self.server.inventory.heroes
        for category, rank, collaboration, stars, style in (
            ("Normal", 0, False, 1, "bronze"),
            ("Normal", 4, False, 5, "bronze"),
            ("Story", 1, False, 2, "silver"),
            ("Story", 4, False, 5, "silver"),
            ("Unique", 2, False, 3, "gold"),
            ("Unique", 3, False, 4, "gold"),
            ("Unique", 4, False, 5, "gold"),
            ("Story", 5, False, 5, "promote_silver"),
            ("Story", 6, False, 6, "promote_silver"),
            ("Unique", 6, False, 6, "myth_red"),
            ("Unique", 4, True, 5, "collab"),
            ("Unique", 6, True, 6, "collab"),
        ):
            with self.subTest(category=category, rank=rank, collaboration=collaboration):
                editor.specs = {
                    10: {"SummonCategory": category, "CollaborationId": int(collaboration)},
                    20: {"OriginId": 10, "Rank": rank},
                }
                hero = editor.summary(new_character(1, 20))
                self.assertEqual((hero["stars"], hero["starStyle"]), (stars, style))

    def seed_hero_upgrades(self):
        api = "/api/game/heroes"
        self.assertEqual(self.call(api)["heroes"], [])
        editor = self.server.inventory.heroes
        tree = Tree(
            (
                Node(0, 0, False, frozenset({1}), 10, ((70, 2),)),
                Node(0, 0, False, frozenset({0}), 10, ((70, 2),)),
            ),
            (),
            (),
        )
        editor.specs = {
            i: dict(
                Id=i,
                Name=f"archer_{i}",
                Rank=rank,
                Playable=True,
                OriginId=31,
                SummonCategory="Unique",
            )
            for i, rank in ((31, 3), (32, 4), (33, 6))
        }
        editor.specs[33]["SpineAssetName"] = {"default": "archer#archer_myth_model"}
        rules = {
            "hero_blessing.rules": ({32: 2, 33: 2}, (10, 20), 88, 39),
            "hero_evolution.rules": ({31: (3, 32, 81, 1)}, {3: {0: (40, True)}}, 90),
            "hero_limit_break.rules": ({32: (100,), 33: (100,)}, 91),
            "hero_myth.rules": ({32: (33, 93, 400)}, 1, 94, 1),
            "awakening_catalog.catalog": (
                {i: (tree, s["Rank"]) for i, s in editor.specs.items()},
                0.3,
            ),
        }
        rules["hero_awakening.catalog"] = rules["awakening_catalog.catalog"]
        for name, values in rules.items():
            self.enterContext(patch("guardian_tales." + name, return_value=values))
        policy = dict(
            client=CLIENT,
            free_experience=True,
            experience_by_level=[0, 37, 111, 222, 370, 555],
            caps=[{"opened_stage_id": 0, "max_level": 1}],
            limit_break_coefficient=1,
            blessing_coefficient=1,
            myth_coefficient=1,
            max_limit_breaks=1,
            max_bless_level=2,
            character_ids=[31, 32, 33],
            myth_ids=[33],
        )
        (self.root / "imported_training_catalog.json").write_text(json.dumps(policy))
        other = new_character(2, 31)
        with closing(sqlite3.connect(editor.database)) as db, db:
            profile = editor.profile(db)
            profile["User"].update(
                Characters=[new_character(1, 31), other], Assets=[], ItemStackables=[]
            )
            profile["UserProgress"] = {
                "StageStates": {"100010001": 7},
                "QuestProgresses": [{"Id": 39, "Grade": 0}],
            }
            profile["UserRecord"] = {"Cas": 2, "AddCharacterExperienceAmount": 0}
            db.execute("CREATE TABLE imported_account (id INTEGER PRIMARY KEY)")
            db.execute("INSERT INTO imported_account VALUES (1)")
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        return editor, other

    def test_owned_hero_upgrades_are_free_versioned_and_limited_to_the_current_form(self):
        api = "/api/game/heroes"
        editor, other = self.seed_hero_upgrades()
        roster = self.call(api)["heroes"]
        self.assertEqual([h["id"] for h in roster], [1, 2])
        self.assertTrue(all(h["upgradable"] for h in roster))
        detail = self.call(api + "/1")
        original = dict(id=1, action="evolve", value=1, version=detail["version"])
        with StateLock(self.root), self.assertRaises(HTTPError) as in_use:
            self.call(api, original)
        self.assertEqual(in_use.exception.code, 423)
        in_use.exception.close()
        for invalid in (dict(id=999), dict(action="myth"), dict(action="level", value=6)):
            with self.assertRaises(HTTPError) as rejected:
                self.call(api, original | invalid)
            self.assertEqual(rejected.exception.code, 400)
            rejected.exception.close()
        for action, value in (
            ("evolve", 1),
            ("break", 1),
            ("bless", 2),
            ("myth", 1),
            ("level", 6),
            ("awaken", 1),
            ("awaken", -1),
        ):
            detail = self.call(
                api, dict(id=1, action=action, value=value, version=detail["version"])
            )
        self.assertEqual(detail["actions"], {})
        self.assertEqual(detail["hero"]["sprite"], "/heroes/sprites/archer_33.png")
        self.assertEqual(
            detail["stats"],
            {"Level": "6 / 6", "Blessing": "2 / 2", "Limit breaks": "1 / 1", "Awakening": "2 / 2"},
        )
        with self.assertRaises(HTTPError) as stale:
            self.call(api, original)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        with editor.reader() as db:
            user = editor.profile(db)["User"]
        self.assertEqual((user["Assets"], user["ItemStackables"]), ([], []))
        self.assertEqual(user["Characters"][1], other)
        self.assertEqual(user["Characters"][0]["AwakeningTreeGold"], 0)

    def test_panel_hero_reset_matches_preview_preserves_inventory_and_rejects_stale_requests(self):
        api = "/api/game/heroes"
        editor, other = self.seed_hero_upgrades()
        with closing(sqlite3.connect(editor.database)) as db, db:
            profile = editor.profile(db)
            user = profile["User"]
            user["Characters"][0].update(Weapon1=151, Costume=201)
            user["ItemStackables"] = [dict(Id=10, ItemId=110003, Amount=2)]
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        initial = self.call(api + "/1")
        self.assertIn("reason", initial["reset"])
        myth = self.call(api, dict(id=1, action="max", version=initial["version"]))
        self.assertEqual(myth["hero"]["form"], "Myth")
        self.assertEqual(myth["actions"], {})
        target = myth["reset"]["target"]
        self.assertEqual(target, initial["hero"])
        body = dict(id=1, action="reset", version=myth["version"])
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(api, body)
        self.assertEqual(locked.exception.code, 423)
        locked.exception.close()
        with editor.reader() as db:
            before = editor.profile(db)
        result = self.call(api, body)
        self.assertEqual(result["hero"], target)
        self.assertEqual(result["reset"], initial["reset"])
        self.assertEqual(self.call(api + "/1"), result)
        with self.assertRaises(HTTPError) as stale:
            self.call(api, body)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        with self.assertRaises(HTTPError) as repeated:
            self.call(api, body | {"version": result["version"]})
        self.assertEqual(repeated.exception.code, 400)
        repeated.exception.close()
        before["User"]["Characters"] = [user["Characters"][0], other]
        before["User"]["Cas"] += 1
        with editor.reader() as db:
            self.assertEqual(editor.profile(db), before)

    def test_panel_hero_reset_respects_story_evolution_and_training_room(self):
        api = "/api/game/heroes"
        editor, _ = self.seed_hero_upgrades()
        for spec in editor.specs.values():
            spec["SummonCategory"] = "Story"
        with closing(sqlite3.connect(editor.database)) as db, db:
            profile = editor.profile(db)
            profile["User"]["Characters"][0].update(CharacterId=33, Experience=37)
            profile["User"]["Characters"][1]["Experience"] = 37
            profile["User"]["TrainingSlots"] = {"1": {"CharacterId": 2, "IsLevel": True}}
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        first = self.call(api + "/1")
        second = self.call(api + "/2")
        self.assertIn("Training Room", second["reset"]["reason"])
        with self.assertRaises(HTTPError) as blocked:
            self.call(api, dict(id=2, action="reset", version=second["version"]))
        self.assertEqual(blocked.exception.code, 400)
        blocked.exception.close()
        result = self.call(api, dict(id=1, action="reset", version=first["version"]))
        self.assertEqual(result["hero"], first["reset"]["target"])
        self.assertEqual((result["hero"]["spec"], result["hero"]["stars"]), (32, 5))

    def test_max_hero_is_atomic_and_stops_at_the_selected_heros_available_form(self):
        api = "/api/game/heroes"
        editor, other = self.seed_hero_upgrades()
        body = dict(id=1, action="max", version=self.call(api + "/1")["version"])
        with editor.reader() as db:
            original = editor.profile(db)
        with patch("guardian_tales.hero_awakening.awaken", side_effect=ValueError("invalid tree")):
            with self.assertRaises(HTTPError) as aborted:
                self.call(api, body)
            self.assertEqual(aborted.exception.code, 400)
            aborted.exception.close()
        with editor.reader() as db:
            self.assertEqual(editor.profile(db), original)
            self.assertIsNone(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='hero_myth_requests'"
                ).fetchone()
            )

        myth = self.call(api, body)
        self.assertEqual(myth["hero"]["form"], "Myth")
        self.assertEqual(myth["stats"]["Level"], "6 / 6")
        self.assertEqual(myth["stats"]["Awakening"], "2 / 2")
        self.assertEqual(myth["actions"], {})
        self.assertEqual(self.call(api, body | {"version": myth["version"]}), myth)
        with self.assertRaises(HTTPError) as stale:
            self.call(api, body)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        with editor.reader() as db:
            user = editor.profile(db)["User"]
        self.assertEqual(user["Characters"][1], other)
        self.assertEqual((user["Assets"], user["ItemStackables"]), ([], []))
        with patch("guardian_tales.hero_myth.rules", return_value=({}, 1, 94, 1)):
            ordinary = self.call(api, body | {"id": 2, "version": myth["version"]})
        self.assertEqual(ordinary["hero"]["spec"], 32)
        self.assertEqual(ordinary["stats"]["Level"], "5 / 5")
        self.assertEqual(ordinary["stats"]["Awakening"], "2 / 2")
        self.assertEqual(ordinary["actions"], {})

    def test_max_hero_follows_regional_ascent_before_myth_and_respects_training_locks(self):
        api = "/api/game/heroes"
        editor, _ = self.seed_hero_upgrades()
        editor.ascent_rank, editor.ascent_categories = 5, {"Story"}
        editor.specs[32].update(
            OriginId=31, SummonCategory="Story", AscendTo={"KakaoGlobal": 34, "Default": 99}
        )
        editor.specs[34] = dict(
            Id=34, OriginId=31, Name="archer_ascent", SummonCategory="Story", Rank=5, Playable=True
        )
        with patch("guardian_tales.hero_myth.rules", return_value=({34: (33, 93, 400)}, 1, 94, 1)):
            completed = self.call(
                api, dict(id=1, action="max", version=self.call(api + "/1")["version"])
            )
        self.assertEqual(completed["hero"]["form"], "Myth")
        self.assertEqual(completed["actions"], {})
        with closing(sqlite3.connect(editor.database)) as db, db:
            profile = editor.profile(db)
            profile["User"]["TrainingSlots"] = {"1": {"CharacterId": 2, "IsAwakening": True}}
            db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        restricted = self.call(api, dict(id=2, action="max", version=completed["version"]))
        self.assertTrue(restricted["trainingRoom"])
        self.assertEqual(restricted["hero"]["spec"], 32)
        self.assertEqual(restricted["stats"]["Awakening"], "0 / 2")
        self.assertEqual(restricted["stats"]["Level"], "5 / 5")
        self.assertEqual(restricted["actions"], {})

    def test_add_relic_uses_native_star_slots_and_separate_capacity(self):
        original = self.seed_wallet()["User"]
        api = "/api/game/relics"
        catalog = self.call(api + "/catalog")
        self.assertEqual({i["spec"]: i["stars"] for i in catalog["items"]}, {4: 5, 61: 1})
        body = dict(spec=61, version=catalog["version"])
        for spec in (3, 62, 63, True):
            with self.subTest(spec=spec), self.assertRaises(HTTPError) as rejected:
                self.call(api + "/add", dict(body, spec=spec))
            self.assertEqual(rejected.exception.code, 400)
            rejected.exception.close()
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(api + "/add", body)
        self.assertEqual(locked.exception.code, 423)
        locked.exception.close()
        self.assertEqual(self.call(api + "/add", body), {"id": 21, "spec": 61})
        with self.assertRaises(HTTPError) as stale:
            self.call(api + "/add", body)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        version = self.call(api + "/catalog")["version"]
        self.assertEqual(self.call(api + "/add", dict(spec=4, version=version))["id"], 22)
        listing = self.call(api)
        new = {r["id"]: r for r in listing["copies"]}[21]
        self.assertEqual(
            (new["spec"], new["locked"], new["equipped"], new["jewels"]), (61, False, False, 0)
        )
        for source, group in [(1, "main"), (2, "bonus")]:
            (row,) = new[group]
            self.assertEqual(
                (row["OptionSource"], row["OptionId"], row["Locked"]), (source, 7, False)
            )
            self.assertIn(row["Level"], range(1, 4))
        catalog = self.call(api + "/catalog")
        self.assertFalse(catalog["spaceAvailable"])
        with self.assertRaises(HTTPError) as full:
            self.call(api + "/add", dict(body, version=catalog["version"]))
        self.assertEqual(full.exception.code, 400)
        full.exception.close()
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            user = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])["User"]
        self.assertEqual(user["ItemMiscs"][:-2], original["ItemMiscs"])
        self.assertEqual((user["ItemIdCounter"], user["Cas"]), (22, original["Cas"] + 2))
        for field in ("ItemWeapons", "ItemStackables", "Assets", "Characters"):
            self.assertEqual(user[field], original[field])

    def test_add_standard_equipment_and_reject_replayed_or_unlisted_grants(self):
        original = self.seed_wallet()["User"]
        catalog = self.call("/api/game/equipment/catalog")
        self.assertEqual({i["spec"] for i in catalog["items"]}, {3, 5, 10, 56, 57, 58})
        path = "/api/game/equipment/add"
        payload = dict(spec=3, version=catalog["version"])
        for spec in (1, 50, 51, 52, 53, 54, 55, 59, True):
            with self.subTest(spec=spec), self.assertRaises(HTTPError) as invalid:
                self.call(path, dict(payload, spec=spec))
            self.assertEqual(invalid.exception.code, 400)
            invalid.exception.close()
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(path, payload)
        self.assertEqual(locked.exception.code, 423)
        locked.exception.close()
        self.assertEqual(self.call(path, payload), {"id": 21, "spec": 3})
        with self.assertRaises(HTTPError) as stale:
            self.call(path, payload)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()
        version = self.call("/api/game/equipment/catalog")["version"]
        self.assertEqual(self.call(path, dict(spec=10, version=version))["id"], 22)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            user = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])["User"]
        self.assertEqual(user["ItemWeapons"][:-2], original["ItemWeapons"])
        self.assertEqual(user["ItemMiscs"], original["ItemMiscs"])
        self.assertEqual(user["ItemStackables"], original["ItemStackables"])
        self.assertEqual(user["Assets"], original["Assets"])
        self.assertEqual((user["ItemIdCounter"], user["Cas"]), (22, original["Cas"] + 2))
        ring, shield = user["ItemWeapons"][-2:]
        self.assertEqual((ring["Experience"], ring["LimitBreaks"], ring["Locked"]), (0, 0, False))
        (option,) = ring["Options"]
        self.assertIn(option["Level"], (1, 2, 3))
        self.assertEqual(
            (option["OptionId"], option["Locked"], option["OptionSource"]), (7, False, 0)
        )
        self.assertIsNone(shield["Options"])
        catalog = self.call("/api/game/equipment/catalog")
        self.assertFalse(catalog["spaceAvailable"])
        with self.assertRaises(HTTPError) as full:
            self.call(path, dict(spec=5, version=catalog["version"]))
        self.assertEqual(full.exception.code, 400)
        full.exception.close()

    def test_delete_exact_equipped_copy_preserves_duplicates_and_clears_only_its_roll(self):
        original = self.seed_wallet()
        db = self.enterContext(closing(sqlite3.connect(self.root / "server.sqlite3")))
        user = original["User"]
        user.update(TrainingSlots={}, Characters=[{"Weapon1": 11, "Relic": 12}], ItemIdCounter=25)
        user["ItemWeapons"][0]["Locked"] = False
        user["ItemWeapons"].append(dict(user["ItemWeapons"][0], Id=24))
        user["ItemMiscs"].append(dict(user["ItemMiscs"][0], Id=25))
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(original),))
            db.execute("CREATE TABLE imported_account (id INTEGER PRIMARY KEY, startup_reads TEXT)")
            db.execute("CREATE TABLE relic_option_proposals (item_id INTEGER PRIMARY KEY)")
            db.executemany("INSERT INTO relic_option_proposals VALUES(?)", [(12,), (25,)])
        for section, ident, spec, bucket, field in (
            ("equipment", 11, 3, "ItemWeapons", "Weapon1"),
            ("relics", 12, 4, "ItemMiscs", "Relic"),
        ):
            with self.subTest(section=section):
                api = "/api/game/" + section
                payload = dict(id=ident, spec=spec, version=self.call(api)["inventoryVersion"])
                with StateLock(self.root), self.assertRaises(HTTPError) as locked:
                    self.call(api + "/delete", payload)
                self.assertEqual(locked.exception.code, 423)
                locked.exception.close()
                user["Cas"] += 1
                self.assertEqual(
                    self.call(api + "/delete", payload), {"id": ident, "revision": user["Cas"]}
                )
                with self.assertRaises(HTTPError) as replay:
                    self.call(api + "/delete", payload)
                self.assertEqual(replay.exception.code, 409)
                replay.exception.close()
                user[bucket] = [row for row in user[bucket] if row["Id"] != ident]
                user["Characters"][0][field] = None
                self.assertEqual(
                    json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]),
                    original,
                )
        self.assertEqual(
            db.execute("SELECT item_id FROM relic_option_proposals").fetchall(), [(25,)]
        )

    def test_lock_and_unlock_preserve_equipped_copies_option_locks_jewels_and_duplicate_items(self):
        profile = self.seed_wallet()
        db = self.enterContext(closing(sqlite3.connect(self.root / "server.sqlite3")))
        user = profile["User"]
        weapon = user["ItemWeapons"][0]
        relic = user["ItemMiscs"][0]
        weapon["Options"][0]["Locked"] = True
        relic.update(Locked=True, JewelSlots=[300])
        relic["RelicOptions"][0]["Locked"] = True
        user.update(Characters=[{"Weapon1": 11, "Relic": 12}], ItemIdCounter=27)
        user["ItemWeapons"].extend((dict(weapon, Id=24), dict(weapon, Id=26, Locked=False)))
        user["ItemMiscs"].extend((dict(relic, Id=25), dict(relic, Id=27, Locked=False)))
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        for section, row in (("equipment", weapon), ("relics", relic)):
            api = "/api/game/" + section
            for action, protected in (("unlock", False), ("lock", True)):
                with self.subTest(section=section, action=action):
                    path = api + "/" + action
                    payload = dict(
                        id=row["Id"], spec=row["ItemId"], version=self.call(api)["inventoryVersion"]
                    )
                    with StateLock(self.root), self.assertRaises(HTTPError) as busy:
                        self.call(path, payload)
                    self.assertEqual(busy.exception.code, 423)
                    busy.exception.close()
                    result = self.call(path, payload)
                    user["Cas"] += 1
                    row["Locked"] = protected
                    self.assertIs(result["locked"], protected)
                    self.assertEqual(result["revision"], user["Cas"])
                    self.assertEqual(result["inventoryVersion"], self.call(api)["inventoryVersion"])
                    with self.assertRaises(HTTPError) as stale:
                        self.call(path, payload)
                    self.assertEqual(stale.exception.code, 409)
                    stale.exception.close()
                    self.assertEqual(
                        self.call(path, dict(payload, version=result["inventoryVersion"])), result
                    )
                    self.assertEqual(
                        json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]),
                        profile,
                    )

    def test_bulk_actions_validate_every_copy_and_commit_each_selection_once(self):
        profile = self.seed_wallet()
        db = self.enterContext(closing(sqlite3.connect(self.root / "server.sqlite3")))
        user = profile["User"]
        user.update(TrainingSlots={}, Characters=[{"Weapon1": 11, "Relic": 12}], ItemIdCounter=27)
        for bucket, duplicate, sibling in (("ItemWeapons", 24, 26), ("ItemMiscs", 25, 27)):
            first = user[bucket][0]
            first["Locked"] = False
            user[bucket].extend((dict(first, Id=duplicate, Locked=True), dict(first, Id=sibling)))
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            db.execute("CREATE TABLE imported_account (id INTEGER PRIMARY KEY, startup_reads TEXT)")

        def saved():
            return json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])

        for tab, bucket, field, duplicate in (
            ("equipment", "ItemWeapons", "Weapon1", 24),
            ("relics", "ItemMiscs", "Relic", 25),
        ):
            with self.subTest(tab=tab):
                api = "/api/game/" + tab
                first = user[bucket][0]
                selected = [first, next(r for r in user[bucket] if r["Id"] == duplicate)]
                copies = [dict(id=r["Id"], spec=r["ItemId"]) for r in selected]
                payload = dict(copies=copies, version=self.call(api)["inventoryVersion"])

                def reject(action, body, status):
                    with self.assertRaises(HTTPError) as error:
                        self.call(api + "/" + action, body)
                    self.assertEqual(error.exception.code, status)
                    error.exception.close()
                    self.assertEqual(saved(), profile)

                reject("delete", payload, 400)  # Last selected copy is locked.
                reject("lock", dict(payload, copies=[copies[0], copies[0]]), 400)
                reject("lock", dict(payload, copies=[copies[0], dict(copies[1], spec=999)]), 400)
                with StateLock(self.root):
                    reject("unlock", payload, 423)
                for action, locked in (("lock", True), ("unlock", False)):
                    old_token = payload["version"]
                    result = self.call(api + "/" + action, payload)
                    user["Cas"] += 1
                    for row in selected:
                        row["Locked"] = locked
                    self.assertEqual(result["ids"], [r["Id"] for r in selected])
                    self.assertIs(result["locked"], locked)
                    self.assertEqual(result["revision"], user["Cas"])
                    self.assertEqual(saved(), profile)
                    payload["version"] = result["inventoryVersion"]
                    reject("delete", dict(payload, version=old_token), 409)

                result = self.call(api + "/delete", payload)
                user["Cas"] += 1
                user[bucket] = [r for r in user[bucket] if r not in selected]
                user["Characters"][0][field] = None
                self.assertEqual(result["revision"], user["Cas"])
                self.assertEqual(result["inventoryVersion"], self.call(api)["inventoryVersion"])
                self.assertEqual(saved(), profile)
                reject("delete", payload, 409)

    def test_force_delete_equipment_releases_only_matching_slots_in_live_presets(self):
        profile = self.seed_wallet()
        user = profile["User"]
        db = self.enterContext(closing(sqlite3.connect(self.root / "server.sqlite3")))
        user.update(
            Characters=[dict(Id=11, Weapon1=11, Relic=12, EquipCostumes={"1": 15, "2": 12})],
            TrainingSlots={"2": {"Id": 2, "ItemId": 15, "IsLevel": True}},
            ItemIdCounter=22,
        )
        unchanged = {"Cas": 8, "Presets": [{"Id": 15, "Characters": [{"Id": 11, "Relic": 12}]}]}
        hero = {"Id": 11, "Weapon1": 11, "Weapon2": 15, "Relic": 12}
        party = {"Cas": 3, "Presets": [{"Id": 15, "Characters": [hero]}]}
        multi = {"Cas": 4, "Presets": [{"Id": 11, "Parties": [{"Characters": [hero]}]}]}
        coop = {"0": {"Id": 15, "Dealer": hero}}
        captured = {
            "UserPartyPreset2": unchanged,
            "UserCharacterListPreset": unchanged,
            "UserMultiPartyPreset": multi,
            "CoopExpeditionSlots": coop,
        }
        raw = json.dumps({"/preset/get-presets": {"value": captured}})
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            db.execute("CREATE TABLE imported_account (id INTEGER PRIMARY KEY, startup_reads TEXT)")
            db.execute("INSERT INTO imported_account VALUES(1,?)", (raw,))
            db.execute("CREATE TABLE party_preset_state (id INTEGER PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO party_preset_state VALUES(1,?)", (json.dumps(party),))
        api = "/api/game/equipment"
        body = dict(
            copies=[dict(id=11, spec=3), dict(id=15, spec=5)],
            version=self.call(api)["inventoryVersion"],
        )
        with StateLock(self.root), self.assertRaises(HTTPError) as busy:
            self.call(api + "/force-delete", body)
        self.assertEqual(busy.exception.code, 423)
        busy.exception.close()
        # Fail after overlay writes and verify they roll back with the profile.
        user["TrainingSlots"] = []
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        with self.assertRaises(HTTPError) as invalid:
            self.call(api + "/force-delete", body)
        self.assertEqual(invalid.exception.code, 400)
        invalid.exception.close()
        self.assertEqual(
            preserved_read(db, "/preset/get-presets"), dict(captured, UserPartyPreset2=party)
        )
        self.assertEqual(
            json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), profile
        )
        user["TrainingSlots"] = {"2": {"Id": 2, "ItemId": 15, "IsLevel": True}}
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        result = self.call(api + "/force-delete", body)
        self.assertEqual(result["revision"], user["Cas"] + 1)
        self.assertEqual(result["ids"], [11, 15])
        user["Cas"] += 1
        user["ItemWeapons"] = []
        user["Characters"][0].update(Weapon1=None, EquipCostumes={"2": 12})
        user["TrainingSlots"]["2"]["ItemId"] = 0
        self.assertEqual(
            json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), profile
        )
        hero.update(Weapon1=None, Weapon2=None)
        party["Cas"] += 1
        multi["Cas"] += 1
        self.assertEqual(
            preserved_read(db, "/preset/get-presets"), dict(captured, UserPartyPreset2=party)
        )
        self.assertEqual(
            db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], raw
        )
        with self.assertRaises(HTTPError) as stale:
            self.call(api + "/force-delete", body)
        self.assertEqual(stale.exception.code, 409)
        stale.exception.close()

    def test_force_delete_relics_recovers_all_jewels_once_and_rejects_invalid_sockets(self):
        profile = self.seed_wallet()
        user = profile["User"]
        source = user["ItemMiscs"][0]
        source.update(Locked=True, JewelSlots=[300, None])
        duplicate = dict(source, Id=24, JewelSlots=[9999])
        sibling = dict(source, Id=25)
        user["ItemMiscs"].extend([duplicate, sibling])
        user.update(TrainingSlots={}, Characters=[{"Relic": 12}], ItemIdCounter=25)
        db = self.enterContext(closing(sqlite3.connect(self.root / "server.sqlite3")))
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            db.execute("CREATE TABLE imported_account (id INTEGER PRIMARY KEY, startup_reads TEXT)")
        api = "/api/game/relics"
        version = self.call(api)["inventoryVersion"]
        batch = dict(copies=[dict(id=12, spec=4), dict(id=24, spec=4)], version=version)
        for body in (batch, dict(batch, copies=[dict(id=12, spec=4), dict(id=11, spec=3)])):
            with self.assertRaises(HTTPError) as invalid:
                self.call(api + "/force-delete", body)
            self.assertEqual(invalid.exception.code, 400)
            invalid.exception.close()
            self.assertEqual(
                json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), profile
            )
        duplicate["JewelSlots"] = [300, 0]
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.call(api + "/force-delete", batch)
        saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])["User"]
        self.assertEqual(saved["ItemMiscs"], [sibling])
        self.assertEqual(saved["ItemStackables"][:-1], user["ItemStackables"])
        recovered = saved["ItemStackables"][-1]
        self.assertEqual((recovered["Id"], recovered["ItemId"], recovered["Amount"]), (26, 300, 2))
        self.assertEqual(saved["Characters"], [{"Relic": None}])
        self.assertEqual(saved["Cas"], user["Cas"] + 1)
        self.call(
            api + "/force-delete", dict(id=25, spec=4, version=self.call(api)["inventoryVersion"])
        )
        saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])["User"]
        self.assertEqual((saved["ItemIdCounter"], saved["ItemStackables"][-1]["Amount"]), (26, 3))

    def test_batch_larger_than_a_page_fits_in_one_protection_request(self):
        profile = self.seed_wallet()
        user = profile["User"]
        rows = [dict(user["ItemWeapons"][0], Id=i, Locked=False) for i in range(100, 300)]
        user["ItemWeapons"].extend(rows)
        user["ItemIdCounter"] = 299
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        api = "/api/game/equipment"
        result = self.call(
            api + "/lock",
            dict(
                copies=[dict(id=row["Id"], spec=row["ItemId"]) for row in rows],
                version=self.call(api)["inventoryVersion"],
            ),
        )
        self.assertEqual(result["ids"], [row["Id"] for row in rows])
        self.assertEqual(result["revision"], user["Cas"] + 1)
        self.assertTrue(all(row["locked"] for row in self.call(api)["rows"] if row["id"] >= 100))

    def test_panel_unlock_checks_inventory_spec_and_unambiguous_owned_id(self):
        profile = self.seed_wallet()
        db = self.enterContext(closing(sqlite3.connect(self.root / "server.sqlite3")))
        version = self.call("/api/game/equipment")["inventoryVersion"]
        user = profile["User"]
        user["ItemMiscs"].append(dict(Id=21, ItemId=2, Amount=1, Locked=True))
        user["ItemIdCounter"] = 21
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))

        def reject(section, ident, spec):
            with self.assertRaises(HTTPError) as error:
                self.call(
                    "/api/game/" + section + "/unlock", dict(id=ident, spec=spec, version=version)
                )
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
            self.assertEqual(
                json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), profile
            )

        reject("equipment", 12, 4)
        reject("equipment", 11, 5)
        reject("relics", 11, 3)
        reject("relics", 21, 2)
        user["ItemMiscs"][-1]["Id"] = 11
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        reject("equipment", 11, 3)

    def test_panel_delete_rejects_protected_wrong_section_stack_and_stale_selection(self):
        profile = self.seed_wallet()
        user = profile["User"]
        db = self.enterContext(closing(sqlite3.connect(self.root / "server.sqlite3")))
        user["TrainingSlots"] = {"2": {"ItemId": 15}}
        user["ItemWeapons"][1]["Locked"] = False
        user["ItemMiscs"][0]["JewelSlots"] = [300]
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            db.execute("CREATE TABLE imported_account (id INTEGER PRIMARY KEY, startup_reads TEXT)")
        version = self.call("/api/game/equipment")["inventoryVersion"]

        def reject(section, ident, spec, status=400, token=version):
            with self.assertRaises(HTTPError) as error:
                self.call(
                    "/api/game/" + section + "/delete", dict(id=ident, spec=spec, version=token)
                )
            self.assertEqual(error.exception.code, status)
            error.exception.close()
            self.assertEqual(
                json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), profile
            )

        reject("equipment", 11, 3)  # Locked.
        reject("equipment", 15, 5)  # Training Room.
        reject("relics", 12, 4)  # Socketed jewel.
        reject("relics", 12, 4, 409, "99:10")  # Same revision, different owner.
        reject("equipment", 12, 4)
        reject("relics", 11, 3)
        reject("equipment", 13, 1)
        user["ItemMiscs"][0]["JewelSlots"] = [None]
        user["ItemMiscs"].append(dict(Id=23, ItemId=2, Amount=1, Locked=False))
        with db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            presets = {"/preset/get-presets": {"value": {"Presets": [{"Relic": 12}]}}}
            db.execute("INSERT INTO imported_account VALUES(1,?)", (json.dumps(presets),))
        reject("relics", 12, 4)  # Saved preset.
        reject("relics", 23, 2)  # Other miscellaneous inventory.

    def test_catalog_adds_limited_collaboration_weapons_and_their_linked_myth_forms(self):
        self.seed_wallet()
        api = "/api/game/equipment"
        catalog = self.call(api + "/catalog")
        collabs = [item for item in catalog["items"] if item["collaborationId"]]
        self.assertEqual(
            {(i["spec"], i["stars"], i["collaborationId"]) for i in collabs},
            {(57, 5, 6), (58, 6, 6)},
        )
        version = catalog["version"]
        for item in collabs:
            self.assertEqual(item["ribbons"], ["exclusive-collab"])
            saved = self.call(api + "/add", dict(spec=item["spec"], version=version))
            inventory = self.call(api)
            row = next(row for row in inventory["rows"] if row["id"] == saved["id"])
            self.assertEqual(
                (row["spec"], row["stars"], row["level"]), (item["spec"], item["stars"], 1)
            )
            self.assertIn("exclusive-collab", row["ribbons"])
            version = inventory["inventoryVersion"]

    def test_catalog_grants_the_selected_native_star_variant(self):
        self.seed_wallet()
        catalog = self.call("/api/game/equipment/catalog")
        variants = {item["spec"]: item for item in catalog["items"]}
        self.assertEqual((variants[5]["stars"], variants[56]["stars"]), (5, 6))
        self.assertEqual(variants[56]["grade"], variants[5]["grade"])
        self.assertEqual(variants[56]["exclusiveHero"], 1)
        saved = self.call("/api/game/equipment/add", {"spec": 56, "version": catalog["version"]})
        copies = {item["id"]: item for item in self.call("/api/game/equipment")["rows"]}
        self.assertEqual((copies[saved["id"]]["spec"], copies[saved["id"]]["stars"]), (56, 6))
        self.assertEqual((copies[15]["spec"], copies[15]["stars"]), (5, 5))

    def test_either_dashboard_serves_both_sections_on_the_same_save(self):
        game_panel = WebPanel(
            ReferenceData(self.root), 0, database=self.root / "server.sqlite3", art_dir=self.root
        )
        game_panel.start()
        self.addCleanup(game_panel.stop)
        with StateLock(self.root):
            for panel, landing in ((self.server, "/equipment"), (game_panel, "/raid")):
                with self.subTest(landing=landing):
                    self.origin = f"http://127.0.0.1:{panel.server_port}"
                    self.assertEqual(self.call("/"), self.call(landing))
                    for page in ("/raid", "/tetis", "/equipment", "/mastery"):
                        html = self.call(page)
                        self.assertIn(b'aria-label="Dashboard sections"', html)
                        self.assertIn(b'id="service-controls"', html)
                    equipment = self.call("/api/game/equipment")
                    self.assertEqual({row["id"] for row in equipment["rows"]}, {11, 15})
                    self.assertFalse(equipment["writable"])
                    self.assertFalse(self.call("/api/game/status")["writable"])

    def test_closing_equipment_preview_discards_the_copy_and_keeps_dashboard_open(self):
        self.seed_wallet()
        preview = self.call("/api/inventory")
        ring = next(row for row in preview["rows"] if row["id"] == 11)
        self.call("/api/lock", dict(id=11, locked=False, revision=preview["revision"]))
        self.assertTrue(ring["locked"])
        self.assertFalse(
            next(row for row in self.call("/api/inventory")["rows"] if row["id"] == 11)["locked"]
        )
        self.assertEqual(self.call("/api/preview/close", {}), {"closed": True})
        self.assertEqual(self.call("/api/inventory")["rows"], preview["rows"])
        self.assertTrue(self.call("/raid"))

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
                self.server.inventory.catalog.refs, frame="ic_drone_controller"
            )
            ui.read.assert_not_called()
            self.assertEqual(self.call("/icon/110015.png"), b"selectable icon")
            ui.read.assert_called_once_with(
                self.server.inventory.catalog.refs, frame="ic_drone_controller_2"
            )
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
        self.assertEqual([r["limit"] for r in view["summoning"]], [100_000, 40, 100_000])
        body = dict(
            version=view["version"],
            name=view["name"],
            tag=view["tag"],
            add={},
            set=dict(mileage=0, summonControllers=6, selectableControllers=100_000),
        )
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(path, body)
        self.assertEqual(locked.exception.code, 423)
        result = self.call(path, body)
        self.assertEqual([r["balance"] for r in result["summoning"]], [0, 6, 100_000])
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
        self.assertEqual((ticket["Id"], ticket["ItemId"], ticket["Amount"]), (23, 110015, 100_000))
        self.assertEqual(saved["ItemIdCounter"], 23)
        body["set"] = dict(mileage=100_000, summonControllers=40, selectableControllers=0)
        self.call(path, body)
        self.assertEqual([r["balance"] for r in self.call(path)["summoning"]], [100_000, 40, 0])
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
            dict(set={"mileage": 100_001}),
            dict(set={"selectableControllers": 100_001}),
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

    def test_account_material_edits_preserve_other_worlds_stones_progress_and_legacy_balances(self):
        profile = self.seed_wallet()
        user = profile["User"]
        user["Assets"].extend(
            [
                dict(Id=70004, Amount=1_500_000_000, Spent=25),
                dict(Id=71001, Amount=50, Spent=12),
            ]
        )
        user["ItemStackables"].extend(
            [
                dict(Id=21, ItemId=85001, Amount=30, Locked=True),
                dict(Id=22, ItemId=85001, Amount=80, Locked=False),
            ]
        )
        user["ItemIdCounter"] = 22
        profile["PurpleCoins"] = {"10001": "collected"}
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        path = "/api/game/account"
        view = self.call(path)
        materials = {i["id"]: i for i in view["materials"]}
        self.assertEqual(materials[71002]["choice"], "World 2")
        self.assertEqual(materials[85001]["choice"], "Archer")
        self.assertEqual(materials[70004]["balance"], 1_500_000_000)
        self.assertEqual(materials[85001]["balance"], 110)
        for ident in (70004, 70028):
            self.assertEqual(materials[ident]["limit"], 1_000_000_000)
        self.assertEqual(materials[70034]["limit"], 800)
        self.assertNotIn(70014, materials)
        body = dict(version=view["version"], name=view["name"], tag=view["tag"], add={})
        totals = {
            "material-71002": 100_000,
            "material-85001": 50,
            "material-85002": 33,
            "material-70034": 45,
            "material-76005": 24,
            "material-77004": 14,
        }
        for invalid in (
            {"material-70034": 801},
            {"material-70004": 1_000_000_001},
            {"material-70028": 1_000_000_001},
            {"material-85002": 100_001},
            {"material-70004": -1},
            {"material-70034": True},
            {"material-70014": 1},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(HTTPError) as rejected:
                self.call(path, body | {"set": totals | invalid})
            self.assertEqual(rejected.exception.code, 400)
        with StateLock(self.root), self.assertRaises(HTTPError) as locked:
            self.call(path, body | {"set": totals})
        self.assertEqual(locked.exception.code, 423)
        self.assertEqual(self.call(path), view)
        result = self.call(path, body | {"set": totals})
        with self.assertRaises(HTTPError) as stale:
            self.call(path, body | {"set": totals})
        self.assertEqual(stale.exception.code, 409)
        balances = {i["key"]: i["balance"] for i in self.call(path)["materials"]}
        self.assertEqual({key: balances[key] for key in totals}, totals)
        self.assertEqual(balances["material-70004"], 1_500_000_000)
        self.assertEqual(balances["material-71001"], 50)
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
        self.assertEqual(saved["PurpleCoins"], profile["PurpleCoins"])
        self.assertEqual(saved["User"]["Assets"][: len(user["Assets"])], user["Assets"])
        self.assertEqual(saved["User"]["ItemStackables"][-2]["Id"], 22)
        self.assertEqual(saved["User"]["ItemStackables"][-1]["Id"], 23)
        totals = {
            "material-85001": 0,
            "material-70004": 1_000_000_000,
            "material-70028": 1_000_000_000,
        }
        self.call(path, body | {"version": result["version"], "set": totals})
        balances = {i["key"]: i["balance"] for i in self.call(path)["materials"]}
        self.assertEqual({key: balances[key] for key in totals}, totals)

    def test_account_edits_personal_and_shared_evolution_stones_independently(self):
        profile = self.seed_wallet()
        legacy = dict(Id=22, ItemId=80002, Amount=17, Locked=False)
        profile["User"]["ItemStackables"].append(legacy)
        profile["User"]["ItemIdCounter"] = legacy["Id"]
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db, db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        path = "/api/game/account"
        view = self.call(path)
        stones = {
            row["id"]: row for row in view["materials"] if row["group"] == "Hero Evolution Stones"
        }
        self.assertEqual(set(stones), {80001, 81000})
        self.assertEqual(stones[80001]["choice"], "Archer")
        self.assertFalse(stones[80001]["catalogOnly"])
        self.assertEqual(stones[81000]["choice"], "Rare Evolution Stone")
        self.assertEqual(stones[81000]["limit"], 100_000)
        request = dict(name=view["name"], tag=view["tag"], version=view["version"], add={})
        totals = {"material-80001": 100_000, "material-81000": 35, "material-85001": 9}
        for edit in ({"material-80001": 100_001}, {"material-80002": 25}):
            with self.subTest(edit=edit), self.assertRaises(HTTPError) as invalid:
                self.call(path, request | {"set": totals | edit})
            self.assertEqual(invalid.exception.code, 400)
        saved = self.call(path, request | {"set": totals})
        self.call(path, request | {"version": saved["version"], "set": {"material-80001": 0}})
        balances = {row["key"]: row["balance"] for row in self.call(path)["materials"]}
        self.assertEqual({key: balances[key] for key in totals}, totals | {"material-80001": 0})
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            user = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])["User"]
        self.assertEqual(
            [row for row in user["ItemStackables"] if row["ItemId"] == 80002], [legacy]
        )

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
