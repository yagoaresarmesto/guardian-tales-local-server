# SPDX-License-Identifier: Apache-2.0
"""An optional weapon copy has isolated definitions, receipts and targeted undo."""

import copy
import hashlib
import io
import json
import sqlite3
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from unittest.mock import patch

from guardian_tales.__main__ import main
from guardian_tales.admin_test_items import grant_test_pin
from guardian_tales.andras_trial_growth import LEADER
from guardian_tales.head_hunter import grant, history, remove
from guardian_tales.head_hunter_static import ACTION, CLASS, OPTION, SOURCE, TABLE, VARIANT
from guardian_tales.items import inventory_item
from guardian_tales.protocol import PacketError
from guardian_tales.raid_static import decode, records
from guardian_tales.snapshots import CLIENT
from guardian_tales.state_lock import StateLock
from tests import test_andras_trial as fixture
from tests.test_admin_test_items import source_body
from tests.test_snapshots import request


class HeadHunterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.AndrasTrialTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        f = self.fixture
        self.state, self.refs, self.db = f.state, f.refs, f.db
        self.source = self.refs / "static_data_get.bin"
        self.enterContext(
            patch(
                "guardian_tales.head_hunter_static.binary_name_hash",
                side_effect=lambda s: int.from_bytes(
                    hashlib.sha256(s.encode()).digest()[:8], "little"
                ),
            )
        )
        weapon = dict(
            Id=SOURCE,
            Name="cwp_demonslayer_epic",
            Type="weapon",
            WeaponType="staff",
            Rarity=4,
            OriginRarity=4,
            ExclusiveCharacterId=488,
            NameWithoutRarity="cwp_demonslayer",
            SuperBattleAction="CwpDemonSlayer",
            SpriteName={"default": "existing_staff"},
            IceDamage=174.3333333,
            StatGrowthRate=1.02,
            StaticOptions=[dict(OptionId=310488, Level=1), dict(OptionId=340488, Level=4)],
            EngraveRandomOptions=[dict(OptionId=104, Level=45)],
        )
        f.tables["items"].append(weapon)
        pin_tables = records(decode(source_body()))[1]
        f.tables["items"].extend(json.loads(pin_tables["items"][1]))
        f.tables["options"].extend(json.loads(pin_tables["options"][1]))
        f.tables["options"].append(
            dict(
                Id=310488,
                Name="demon_slayer_cwp_option",
                Class="BattleActionParameter",
                ConditionType="CharacterOriginType",
                CharacterOriginIds=[488],
                ReinforceCondition=4,
                AddModifierMultiplier=0.2,
            )
        )
        f.heroes[0]["CompatibleWeapons"] = {"default": ["staff"]}
        # Keep JSON and native lookup tables consistent in this synthetic pack.
        f.tables["heroes-bin"] = fixture.pack_rows(
            [(h["Id"], i + 1, json.dumps(h).encode()) for i, h in enumerate(f.heroes)]
        )
        role = next(r for r in f.tables["battleactions"] if r["Name"] == "RoleDemonSlayer")
        role.update(UseScript=True, CwpOptionId=310488)
        f.tables["battleactions-bin"] = fixture.pack_rows(
            [(i, i + 100, json.dumps(r).encode()) for i, r in enumerate(f.tables["battleactions"])]
        )
        f.tables["heroes2"] = []
        f.tables["battlestyles"] = {
            "BattleClasses": [],
            "BattleStyles": [
                dict(
                    Name="staff_demon_slayer",
                    Class="demon_slayer",
                    Weapon1="staff",
                    Weapon2="none",
                    BattleActions=["ManualDemonSlayer:First", "RoleDemonSlayer"],
                    ManualBattleActions=["ManualDemonSlayer:First"],
                    ClassBattleActions=[],
                    Ai="ExistingAndrasAI",
                    Visual={"existing": True},
                )
            ],
        }
        f.write_source()
        enhance = dict(
            client=CLIENT,
            free=True,
            level_total_exps=list(range(100, 22100, 100)),
            weapons={str(SOURCE): 4},
            hammer_exp={"999": 100},
            limit_break_coef=3,
            max_limit_breaks=5,
            myth_coef=20,
        )
        engraving = dict(
            client=CLIENT,
            free=True,
            min_experience=100,
            required_limit_breaks=5,
            engrave_coef=15,
            max_ceiling=5,
            weapons={str(SOURCE): dict(origin_rarity=4, options=[dict(OptionId=104, Level=45)])},
            hammers={"998": 4},
        )
        (self.refs / "weapon_enhance_debug_catalog.json").write_text(json.dumps(enhance))
        (self.refs / "weapon_engrave_mock_catalog.json").write_text(json.dumps(engraving))
        profile = self.profile()
        user = profile["User"]
        user["Unlocked"].setdefault("MaxLevel", {})["Weapon"] = 99
        user["ItemIdCounter"] += 1
        self.source_id = user["ItemIdCounter"]
        row = inventory_item(self.source_id, SOURCE)
        row.update(
            Experience=12900,
            LimitBreaks=5,
            EngraveCeiling=1,
            EngraveOptions=[dict(OptionId=104, Level=45, Locked=False, OptionSource=0)],
        )
        user["ItemWeapons"].append(row)
        user["Characters"][0]["Weapon1"] = self.source_id
        self.save(profile)

    def profile(self):
        return json.loads(
            self.db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
        )

    def save(self, profile):
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))

    def grant(self, operation_id="weapon-01", **kwargs):
        return grant(self.state, self.refs, operation_id, "Experimental weapon", **kwargs)

    def fetch(self, route="/static-data/get", body=None, sequence=1):
        packet = request(route, body or {})
        packet["sequence_id"] = sequence
        return self.fixture.session.handle(packet).body

    def tables(self):
        return records(decode(self.fetch()))[1]

    def test_grant_clones_one_owned_weapon_at_visible_150_with_backup_and_no_other_changes(self):
        before, source = self.profile(), self.source.read_bytes()
        value = self.grant()
        expected = copy.deepcopy(before)
        row = dict(
            before["User"]["ItemWeapons"][-1],
            Id=value["inventory_id"],
            ItemId=VARIANT,
            Experience=14900,
            Locked=True,
        )
        expected["User"]["ItemWeapons"].append(row)
        expected["User"]["ItemIdCounter"] += 1
        expected["User"]["Cas"] += 1
        self.assertEqual(self.profile(), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual((value["visible_level"], value["four_crystal_bonus_percent"]), (150, 25))
        with closing(sqlite3.connect(value["backup_path"])) as backup:
            self.assertEqual(
                json.loads(backup.execute("SELECT profile FROM local_account").fetchone()[0]),
                before,
            )
            self.assertEqual(backup.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
        path = self.state / "backups"
        self.assertEqual(len(list(path.glob("*.sqlite3.sha256"))), 1)

    def test_overlay_keeps_original_20_percent_action_style_and_all_stock_rows(self):
        before = records(decode(self.fetch()))[1]
        self.grant()
        after = self.tables()
        for name in ("items", "options", "heroes2", "battleactions"):
            original = json.loads(before[name][1])
            self.assertEqual(json.loads(after[name][1])[: len(original)], original)
        for name in before.keys() - {
            "items",
            "options",
            "heroes2",
            "battleactions",
            "battleactions-bin",
            "battlestyles",
            "__checksum__",
        }:
            self.assertEqual(after[name], before[name])
        items = {r["Id"]: r for r in json.loads(after["items"][1])}
        self.assertEqual(items[SOURCE]["Rarity"], 4)
        self.assertEqual((items[VARIANT]["Rarity"], items[VARIANT]["ExclusiveNumber"]), (5, 2))
        self.assertEqual(items[VARIANT]["StaticOptions"][0]["OptionId"], OPTION)
        options = {r["Id"]: r for r in json.loads(after["options"][1])}
        self.assertEqual(options[310488]["AddModifierMultiplier"], 0.2)
        self.assertEqual(options[OPTION]["AddModifierMultiplier"], 0.25)
        self.assertEqual(options[310488]["Name"], options[OPTION]["Name"])
        actions = {r["Name"]: r for r in json.loads(after["battleactions"][1])}
        self.assertEqual(actions["RoleDemonSlayer"]["CwpOptionId"], 310488)
        self.assertEqual(actions[ACTION]["CwpOptionId"], OPTION)
        styles = json.loads(after["battlestyles"][1])["BattleStyles"]
        self.assertEqual(styles[:-1], json.loads(before["battlestyles"][1])["BattleStyles"])
        self.assertEqual(styles[-1]["Class"], CLASS)
        self.assertIn(ACTION, styles[-1]["BattleActions"])
        overrides = json.loads(after["heroes2"][1])
        self.assertEqual(
            overrides[-1],
            dict(
                Id=490,
                Class=CLASS,
                ExclusiveNumber=2,
                Options=[dict(OptionId=320488), dict(OptionId=310488)],
            ),
        )
        old_binary = fixture.binary_rows(before["battleactions-bin"][1], require_id=False)
        new_binary = fixture.binary_rows(after["battleactions-bin"][1], require_id=False)
        self.assertEqual(new_binary[:-1], old_binary)
        self.assertEqual(json.loads(new_binary[-1][2]), actions[ACTION])
        check = json.loads(
            self.fetch("/static-data/check-update", {"Checksum": after["__checksum__"][1]})
        )
        self.assertTrue(check["UpToDate"])

    def test_equip_original_copy_and_clear_persist_without_switching_owned_hero_spec(self):
        value = self.grant()
        before = self.profile()
        for sequence, ident in enumerate((value["inventory_id"], self.source_id, None), 10):
            self.fetch(
                "/user/change-weapons",
                dict(CharacterId=self.fixture.target, Weapon1=ident, Weapon2=None),
                sequence,
            )
            current = self.profile()
            self.assertEqual(current["User"]["Characters"][0]["Weapon1"], ident)
            self.assertEqual(current["User"]["Characters"][0]["CharacterId"], 490)
            self.assertEqual(current["User"]["ItemWeapons"], before["User"]["ItemWeapons"])

    def test_retry_history_and_sold_copy_never_resurrect_or_erase_newer_progress(self):
        value = self.grant()
        current = self.profile()
        current["User"]["ItemWeapons"].pop()
        current["User"]["Assets"][0]["Amount"] += 9
        self.save(current)
        before = list(self.db.iterdump())
        self.assertFalse(self.grant()["present"])
        self.assertFalse(history(self.state)[0]["present"])
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.fetch(), self.fixture.original)
        removed = remove(self.state, "weapon-01")
        self.assertFalse(removed["present"])
        self.assertEqual(self.profile(), current)
        self.assertEqual(remove(self.state, "weapon-01")["result"], "already_removed")
        self.assertEqual(self.grant()["inventory_id"], value["inventory_id"])
        self.assertFalse(self.grant()["present"])

    def test_remove_detaches_only_copy_retains_later_progress_and_restores_parent_overlay(self):
        original = self.profile()
        value = self.grant()
        current = self.profile()
        current["User"]["Assets"][0]["Amount"] += 17
        current["User"]["Characters"][0]["Weapon1"] = value["inventory_id"]
        self.save(current)
        remove(self.state, "weapon-01")
        expected = copy.deepcopy(current)
        expected["User"]["ItemWeapons"].pop()
        expected["User"]["Characters"][0]["Weapon1"] = None
        expected["User"]["Cas"] += 1
        self.assertEqual(self.profile(), expected)
        self.assertEqual(expected["User"]["ItemWeapons"], original["User"]["ItemWeapons"])
        self.assertEqual(self.fetch(), self.fixture.original)
        self.assertEqual(remove(self.state, "weapon-01")["result"], "already_removed")

    def test_multiple_grants_share_one_definition_and_remove_independently(self):
        first, second = self.grant(), self.grant("weapon-02")
        self.assertNotEqual(first["inventory_id"], second["inventory_id"])
        self.assertEqual(
            len([r for r in json.loads(self.tables()["items"][1]) if r["Id"] == VARIANT]), 1
        )
        remove(self.state, "weapon-01")
        self.assertTrue(history(self.state)[0]["present"])
        self.assertIn(str(VARIANT), self.tables()["items"][1])
        remove(self.state, "weapon-02")
        self.assertEqual(self.fetch(), self.fixture.original)

    def test_andras_myth_growth_and_test_pin_overlays_compose_and_survive_weapon_removal(self):
        self.fixture.cli("enable")
        grant_test_pin(self.state, self.refs, "pin-01", "Synthetic companion")
        parent = self.fetch()
        self.grant()
        after = self.tables()
        hero = next(r for r in json.loads(after["heroes2"][1]) if r["Id"] == 20488)
        self.assertTrue(any(o["OptionId"] == LEADER for o in hero["Options"]))
        self.assertEqual(hero["Class"], CLASS)
        actions = {r["Name"]: r for r in json.loads(after["battleactions"][1])}
        self.assertEqual(
            actions[ACTION]["ModifierBase"], actions["RoleDemonSlayer"]["ModifierBase"]
        )
        remove(self.state, "weapon-01")
        self.assertEqual(self.fetch(), parent)

    def test_backend_lock_prevents_grant_and_remove_without_account_writes(self):
        self.grant()
        before = list(self.db.iterdump())
        with StateLock(self.state):
            for action in (
                lambda: self.grant("weapon-02"),
                lambda: remove(self.state, "weapon-01"),
            ):
                with self.assertRaises(RuntimeError):
                    action()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_invalid_source_state_catalog_and_input_make_no_account_writes(self):
        before = self.profile()
        for change in (
            dict(LimitBreaks=4),
            dict(EngraveOptions=[]),
            dict(JewelSlots=[123]),
            dict(EngraveCeiling=0),
        ):
            current = copy.deepcopy(before)
            current["User"]["ItemWeapons"][-1].update(change)
            self.save(current)
            dump = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.grant()
            self.assertEqual(list(self.db.iterdump()), dump)
        self.save(before)
        for change in (dict(source_item_id=True), dict(source_item_id=99999)):
            with self.assertRaises(ValueError):
                self.grant(**change)
        for key, value in (("myth_coef", 0), ("level_total_exps", [100])):
            path = self.refs / "weapon_enhance_debug_catalog.json"
            old = path.read_text()
            altered = json.loads(old)
            altered[key] = value
            path.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                self.grant()
            path.write_text(old)
        self.assertEqual(self.profile(), before)
        self.assertFalse((self.state / "backups").exists())

    def test_unlock_and_zero_gold_sale_accept_owned_copy_and_never_resurrect_it(self):
        value = self.grant()
        before = self.profile()
        ident = value["inventory_id"]
        self.fetch("/item/unlock", {"itemIndexes": [ident]}, 60)
        self.fetch("/item/sell", {"SellItems": {str(ident): 1}}, 61)
        after = self.profile()
        self.assertEqual(after["User"]["Assets"], before["User"]["Assets"])
        self.assertEqual(after["User"]["ItemWeapons"], before["User"]["ItemWeapons"][:-1])
        self.assertFalse(self.grant()["present"])

    def test_retirement_rejects_training_room_socketed_or_repurposed_copy_without_writes(self):
        value = self.grant()
        original = self.profile()
        for mode in ("training", "jewel", "different_spec"):
            current = copy.deepcopy(original)
            if mode == "training":
                current["User"]["TrainingSlots"]["trial"] = {"ItemId": value["inventory_id"]}
            elif mode == "jewel":
                current["User"]["ItemWeapons"][-1]["JewelSlots"] = [123]
            else:
                current["User"]["ItemWeapons"][-1]["ItemId"] = SOURCE
            self.save(current)
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                remove(self.state, "weapon-01")
            self.assertEqual(list(self.db.iterdump()), before)

    def test_ambiguous_owned_sources_require_explicit_id(self):
        current = self.profile()
        current["User"]["ItemIdCounter"] += 1
        second = dict(current["User"]["ItemWeapons"][-1], Id=current["User"]["ItemIdCounter"])
        current["User"]["ItemWeapons"].append(second)
        self.save(current)
        with self.assertRaises(ValueError):
            self.grant()
        self.assertEqual(self.grant(source_item_id=second["Id"])["source_item_id"], second["Id"])

    def test_conflicting_source_tables_reject_before_backup(self):
        before = list(self.db.iterdump())
        for name, row in (
            ("items", {"Id": VARIANT}),
            ("options", {"Id": OPTION}),
            ("heroes2", {"Id": 490}),
            ("battleactions", {"Name": ACTION}),
        ):
            self.fixture.tables[name].append(row)
            self.fixture.write_source()
            with self.assertRaises(ValueError):
                self.grant()
            self.fixture.tables[name].pop()
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertFalse((self.state / "backups").exists())

    def test_wrong_pack_or_owner_never_serve_or_equip_trial(self):
        self.grant()
        for field, value in (("source_sha256", "wrong"), ("owner_id", 99999)):
            old = self.db.execute(f"SELECT {field} FROM {TABLE}").fetchone()[0]
            with self.db:
                self.db.execute(f"UPDATE {TABLE} SET {field}=?", (value,))
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.fetch()
            with self.assertRaises(PacketError):
                self.fetch(
                    "/user/change-weapons",
                    dict(
                        CharacterId=self.fixture.target,
                        Weapon1=self.profile()["User"]["ItemWeapons"][-1]["Id"],
                        Weapon2=None,
                    ),
                )
            self.assertEqual(list(self.db.iterdump()), before)
            with self.db:
                self.db.execute(f"UPDATE {TABLE} SET {field}=?", (old,))

    def test_failed_receipt_insert_rolls_back_profile_and_counter(self):
        first = self.grant()
        with self.db:
            self.db.execute(
                f"CREATE TRIGGER fail_grant BEFORE INSERT ON {TABLE} BEGIN SELECT RAISE(ABORT,'synthetic'); END"
            )
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.Error):
            self.grant("weapon-02")
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertTrue(first["present"])

    def test_cli_list_grant_remove_and_validation_are_dispatchable(self):
        def cli(*args):
            with redirect_stdout(io.StringIO()) as output:
                main(
                    [
                        "head-hunter",
                        *args,
                        "--data-dir",
                        str(self.state),
                        "--reference-dir",
                        str(self.refs),
                    ]
                )
            return json.loads(output.getvalue())

        self.assertEqual(cli("list"), [])
        self.assertEqual(cli("grant", "--operation-id", "cli-01")["result"], "applied")
        self.assertEqual(cli("remove", "--operation-id", "cli-01")["result"], "removed")
        self.assertEqual(len(cli("list")), 1)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            cli("grant")
        self.assertEqual(error.exception.code, 2)
