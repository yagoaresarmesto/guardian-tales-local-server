# SPDX-License-Identifier: Apache-2.0
"""Exercise the local panel against a synthetic catalog and disposable working save."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardian_tales.basecamp import MASTERY_POINTS
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
            dict(
                Id=3,
                Name="test_ring",
                Type="weapon",
                WeaponType="accessory",
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
                WeaponMaxLimitBreak=3, WeaponEngravingCeiling=3, WeaponEngravingLevelRequirement=2
            ),
            "LevelExps": [dict(Level=1, TotalExps=100)],
            "WeaponEngraveOptionProbability": [
                dict(CeilingCount=i, OptionWeights=weights)
                for i, weights in enumerate(([1, 1, 1], [1, 1, 1], [1, 0, 0]))
            ],
        },
        "__checksum__": {},
    }
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
                    Id=11, ItemId=3, Locked=True, Amount=1, Options=[dict(option, OptionSource=0)]
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

    def test_views_and_referenced_static_assets(self):
        import re

        for section in ("equipment", "relics", "consumables", "mastery"):
            page = self.call("/" + section)
            self.assertIn(b'lang="en"', page)
            for asset in re.findall(rb'(?:href|src)="(/[^"]+\.(?:css|js))"', page):
                self.assertTrue(self.call(asset.decode()))
        with self.assertRaises(HTTPError) as missing_art:
            self.call("/mastery-training.png")
        self.assertEqual(missing_art.exception.code, 404)
        self.assertTrue(self.call("/inventory-dom.js"))
        self.assertTrue(self.call("/equipment-options.js"))

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

    def test_upgrades_and_options_apply_together_with_native_tiers(self):
        path = "/api/game/equipment"
        state = self.call(path)
        self.assertIsNone(state["rows"][0]["progression"])
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
        with closing(sqlite3.connect(self.root / "server.sqlite3")) as db:
            saved = json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0])
        self.assertEqual(
            saved["User"]["ItemWeapons"][1]["EngraveOptions"],
            [dict(OptionId=8, Level=15, OptionSource=0, Locked=False)],
        )
        with self.assertRaises(HTTPError) as invalid:
            self.call(path, self.weapon_edit(progression=dict(engraving=dict(count=3, level=15))))
        self.assertEqual(invalid.exception.code, 400)
