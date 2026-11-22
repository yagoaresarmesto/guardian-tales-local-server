# SPDX-License-Identifier: Apache-2.0
"""The experimental Andras view never replaces the stored hero or game assets."""

import base64
import copy
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from guardian_tales.__main__ import main
from guardian_tales.andras_trial import SELECTION, load, project_response
from guardian_tales.andras_trial_static import (
    SOURCE,
    STONE,
    VARIANT,
    binary_rows,
    pack_rows,
    prepare,
)
from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.protocol import Packet, PacketError
from guardian_tales.raid_static import compress, decode, digest, records
from guardian_tales.snapshots import CLIENT
from tests.test_snapshots import request, synthetic_snapshot


class AndrasTrialTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = self.root / "state"
        self.state.mkdir()
        self.refs = self.root / "reference"
        self.refs.mkdir()
        self.db = self.enterContext(closing(sqlite3.connect(self.state / "server.sqlite3")))
        self.store = GuestStore(self.db, self.refs)
        self.session = BootstrapSession(self.store)
        self.session.signed_in = True
        snapshot = synthetic_snapshot()
        profile = snapshot["profile"]
        profile["User"]["Characters"][0]["CharacterId"] = SOURCE
        self.owner = profile["User"]["Id"]
        self.target = profile["User"]["Characters"][0]["Id"]
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
            self.db.execute(
                "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                ("synthetic", "synthetic", json.dumps(snapshot["startup_reads"]), "{}"),
            )
        source = {
            "Id": SOURCE,
            "Name": "demon_slayer_5",
            "OriginId": 488,
            "Rank": 4,
            "Class": "demon_slayer",
            "MythStoneId": 0,
            "Hp": 1100,
            "Atk": 1.521,
            "Def": 23.52,
            "Options": [{"OptionId": 320488}],
            "SpineAssetName": {"default": "existing_andras"},
            "PortraitAssetName": "existing_portrait",
            "EvolveTo": 0,
        }
        self.heroes = [source, {"Id": 200, "Name": "other_hero", "Rank": 4, "OriginId": 200}]
        self.tables = {
            "heroes": self.heroes,
            "heroes-bin": pack_rows(
                [(row["Id"], i + 1, json.dumps(row).encode()) for i, row in enumerate(self.heroes)]
            ),
            "items": [
                {
                    "Id": 85001,
                    "Name": "myth_stone_stock",
                    "Type": "evolve_stone",
                    "StoneType": "HeroMyth",
                    "SpriteName": {"default": "existing_stone_icon"},
                }
            ],
            "charactertreeconfig": [{"OriginId": 488, "TreeLayoutName": "original_tree"}],
            "__checksum__": "source",
        }
        self.add_growth_fixture()
        self.write_source()
        # Tests do not require the optional xxhash package; the real pack is
        # checked separately with native xxh3 hashes, never this synthetic hash.
        self.enterContext(
            patch(
                "guardian_tales.andras_trial_static.binary_name_hash",
                side_effect=lambda name: int.from_bytes(
                    hashlib.sha256(name.encode()).digest()[:8], "little"
                ),
            )
        )

    def add_growth_fixture(self):
        centers = (248, 257, 266, 275, 283, 291)
        original = [2000000000 + i if i < 30 else 1090300000 + i for i in range(248)]
        extra = [2000060000 + i if i in centers else 1790160000 + i for i in range(248, 300)]
        self.tables["charactertreeconfig"] = [
            dict(
                OriginId=488,
                TreeLayoutName="layout_snowflake_01",
                AwakeningTreeName="original_andras",
                SpecialNodes=list(range(30)),
            ),
            dict(
                OriginId=350,
                TreeLayoutName="layout_snowflake_01_myth",
                AwakeningTreeName="stock_myth",
                SpecialNodes=[*range(30), 995, 996, 997, 998, 999, 989],
            ),
        ]
        self.tables["awakeningtreenodes"] = {
            "original_andras": original,
            "stock_myth": original + extra,
        }
        self.tables["awakeningnodelayout"] = {
            name: [dict(NodeIndex=i, ConnectedNodes=[]) for i in range(count)]
            for name, count in (("layout_snowflake_01", 248), ("layout_snowflake_01_myth", 300))
        }
        self.tables["awakeningnodelayout_client"] = {
            name: dict(Circles=[dict(NodeIndex=i) for i in range(count)], Edges=[])
            for name, count in (("layout_snowflake_01", 30), ("layout_snowflake_01_myth", 36))
        }
        self.tables["awakeningnodedata"] = dict(
            NodeOptions=[],
            OverrideOptions=[],
            ResourcesToOpenNode=[
                dict(Id=20000 + i, OriginId=542, Gold=28000, Item1=60017, Item1Amount=1)
                for i in (995, 996, 997, 998, 999, 989)
            ],
        )
        self.tables["options"] = [
            dict(
                Id=20500542,
                Name="stock_eunha_leader",
                Class="MythBattleAction",
                BattleActionName="MythDokkaebi",
            ),
            dict(Id=320488, Name="original_andras_passive", OverrideModifier=2.8),
            dict(Id=10820, Class="Buff", BuffId=10820),
            dict(
                Id=300488,
                Name="demon_slayer_support_skill",
                Class="BattleAction",
                BattleActionName="BasicSupport:DemonSlayer",
            ),
        ]
        self.tables["buffs"] = [
            dict(Id=10820, ClassName="ProjectileAttackScale", AttackScaleAdd=0.001),
            dict(
                Id=3204880,
                Name="buff_demon_slayer_special_option_0",
                AttackScaleBase=0.3,
                Duration=5,
            ),
            dict(
                Id=3204881,
                Name="buff_demon_slayer_special_option_1",
                DefenseScaleBase=0.3,
                Duration=5,
            ),
            dict(
                Id=320488,
                Name="buff_demon_slayer_special_option",
                BuffId=[3204880, 3204881],
                Level=[0, 0],
            ),
        ]
        self.tables["battleactions"] = [
            dict(Name="MythDokkaebi", UseScript=True, ScriptName="Myth"),
            *[
                dict(Name="ManualDemonSlayer:" + name, ModifierBase=value)
                for name, value in (("First", 0.8), ("Second", 0.8), ("Third", 1.4))
            ],
            dict(Name="RoleDemonSlayer", ModifierBase=0.25),
            dict(Name="CwpDemonSlayer", ModifierBase=0.95, ModifierAdd=0.3),
            dict(Name="BasicSupport:DemonSlayer", HitDpsMultipliers=[0.3, 0.3, 0.3, 0.3, 1.8]),
            dict(Name="UnrelatedAction", ModifierBase=9),
        ]
        self.tables["battleactions-bin"] = pack_rows(
            [
                (i, i + 100, json.dumps(row).encode())
                for i, row in enumerate(self.tables["battleactions"])
            ]
        )

    def write_source(self):
        text = ""
        for name, value in self.tables.items():
            content = value if name.endswith("-bin") else json.dumps(value)
            raw = base64.b64decode(content) if name.endswith("-bin") else content.encode()
            text += f"{name}\n{content}\n31\n{digest(raw)}\n"
        self.original = compress(text.encode())
        (self.refs / "static_data_get.bin").write_bytes(self.original)
        (self.refs / "static_data_check.bin").write_text('{"UpToDate":true}')

    def cli(self, action, data_dir=None):
        with redirect_stdout(io.StringIO()) as output:
            main(
                [
                    "andras-trial",
                    action,
                    "--reference-dir",
                    str(self.refs),
                    "--data-dir",
                    str(data_dir or self.state),
                ]
            )
        return json.loads(output.getvalue())

    def reject(self, action, data_dir=None):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.cli(action, data_dir)
        self.assertEqual(error.exception.code, 2)

    def fetch(self):
        return json.loads(self.session.handle(request("/auth/fetch-account", {})).body)

    def test_disabled_feature_retains_exact_original_responses_and_files(self):
        before = list(self.db.iterdump())
        paths = {p.name: p.read_bytes() for p in self.refs.iterdir()}
        packet = request("/auth/fetch-account", {})
        self.assertEqual(self.session.handle(packet), self.session._handle(packet))
        self.assertFalse(self.cli("status")["active"])
        self.assertFalse(self.cli("disable")["active"])
        self.assertEqual({p.name: p.read_bytes() for p in self.refs.iterdir()}, paths)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_enable_projects_only_owned_target_without_database_writes(self):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        expected = copy.deepcopy(self.store.account.profile())
        expected["User"]["Characters"][0]["CharacterId"] = VARIANT
        from guardian_tales.andras_trial_growth import activated_tree

        expected["User"]["Characters"][0]["AwakeningTree"] = activated_tree(
            expected["User"]["Characters"][0]["AwakeningTree"]
        )
        self.db.execute("PRAGMA query_only=ON")
        self.assertTrue(self.cli("enable")["active"])
        self.assertEqual(self.fetch(), expected)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(
            self.store.account.profile()["User"]["Characters"][0]["CharacterId"], SOURCE
        )

    def test_disable_restores_original_view_and_keeps_progress_since_enable(self):
        self.cli("enable")
        self.assertEqual(self.fetch()["User"]["Characters"][0]["CharacterId"], VARIANT)
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["Experience"] += 123
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        before = list(self.db.iterdump())
        self.assertFalse(self.cli("disable")["active"])
        self.assertEqual(self.fetch(), profile)
        self.assertEqual(load(self.store.references)["generation"], 2)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_static_json_binary_and_assets_retain_original_combat_and_visual_fields(self):
        body, _ = prepare(self.original, 1, True)
        tables = records(decode(body))[1]
        heroes = json.loads(tables["heroes"][1])
        source, other, variant = heroes
        self.assertEqual(
            source, dict(self.heroes[0], MythTo={"KakaoGlobal": VARIANT}, MythStoneId=STONE)
        )
        self.assertEqual(other, self.heroes[1])
        self.assertEqual(
            variant,
            dict(
                self.heroes[0],
                Id=VARIANT,
                Name="demon_slayer_6",
                Rank=6,
                Options=[{"OptionId": 20500542}, *self.heroes[0]["Options"]],
            ),
        )
        binary = {ident: json.loads(raw) for ident, _, raw in binary_rows(tables["heroes-bin"][1])}
        self.assertEqual(binary, {row["Id"]: row for row in heroes})
        stone = json.loads(tables["items"][1])[-1]
        self.assertEqual(stone["SpriteName"], self.tables["items"][0]["SpriteName"])
        self.assertEqual(
            json.loads(tables["charactertreeconfig"][1])[1], self.tables["charactertreeconfig"][1]
        )
        self.assertEqual((self.refs / "static_data_get.bin").read_bytes(), self.original)

    def test_disable_recovers_all_original_static_contents_with_new_revisions(self):
        active, first = prepare(self.original, 1, True)
        restored, second = prepare(self.original, 2, False)
        before, after = records(decode(self.original))[1], records(decode(restored))[1]
        for name in before.keys() - {"__checksum__"}:
            self.assertEqual(after[name][1], before[name][1])
        self.assertNotEqual(first, second)
        self.assertGreater(after["heroes"][2], records(decode(active))[1]["heroes"][2])

    def test_growth_uses_stock_leader_and_preserves_all_other_hero_and_resource_definitions(self):
        body, _ = prepare(self.original, 1, True)
        tables, original = records(decode(body))[1], records(decode(self.original))[1]
        variant = json.loads(tables["heroes"][1])[-1]
        self.assertEqual(variant["Options"][0], {"OptionId": 20500542})
        self.assertEqual(variant["Class"], self.heroes[0]["Class"])
        self.assertEqual(variant["SpineAssetName"], self.heroes[0]["SpineAssetName"])
        for name in ("awakeningnodelayout", "awakeningnodelayout_client"):
            self.assertEqual(tables[name], original[name])
        before = self.tables["battleactions"][0]
        after = json.loads(tables["battleactions"][1])[0]
        self.assertEqual(before, after)
        self.assertEqual(json.loads(tables["options"][1])[0], self.tables["options"][0])

    def test_growth_tree_retains_original_indices_and_adds_six_owned_special_centers(self):
        from guardian_tales.andras_trial_growth import MARKERS, SPECIALS, TREE

        body, _ = prepare(self.original, 1, True)
        tables = records(decode(body))[1]
        trees = json.loads(tables["awakeningtreenodes"][1])
        self.assertEqual(trees[TREE][:248], self.tables["awakeningtreenodes"]["original_andras"])
        self.assertEqual(trees[TREE][248:], self.tables["awakeningtreenodes"]["stock_myth"][248:])
        self.assertEqual(len(trees[TREE]), 300)
        self.assertEqual(trees["stock_myth"], self.tables["awakeningtreenodes"]["stock_myth"])
        config = json.loads(tables["charactertreeconfig"][1])[0]
        self.assertEqual(config["SpecialNodes"], [*range(30), *SPECIALS])
        self.assertEqual(config["AwakeningTreeName"], TREE)
        nodes = json.loads(tables["awakeningnodedata"][1])
        own = [row for row in nodes["NodeOptions"] if row["OriginId"] == 488]
        self.assertEqual([row["OptionId"] for row in own], [10820, *MARKERS])
        self.assertEqual(own[0]["OptionLevel"], 50)
        self.assertEqual(
            nodes["ResourcesToOpenNode"][:6],
            self.tables["awakeningnodedata"]["ResourcesToOpenNode"],
        )
        self.assertEqual(
            nodes["ResourcesToOpenNode"][6:],
            [dict(row, OriginId=488) for row in nodes["ResourcesToOpenNode"][:6]],
        )

    def test_growth_mask_preserves_original_prefix_bits_and_reserved_bits(self):
        from guardian_tales.andras_trial_growth import activated_tree

        for original in (b"", b"\x81" * 31, b"\x55" * 50):
            prefix = b"old!"
            encoded = base64.b64encode(prefix).decode() + "|" + base64.b64encode(original).decode()
            projected = activated_tree(encoded)
            actual_prefix, flags = [base64.b64decode(part) for part in projected.split("|")]
            self.assertEqual(actual_prefix, prefix)
            for i in range(max(len(original), 38) * 8):
                actual = bool(flags[i // 8] & (1 << (i % 8)))
                expected = 248 <= i < 300 or (
                    i // 8 < len(original) and bool(original[i // 8] & (1 << (i % 8)))
                )
                self.assertEqual(actual, expected, i)
            self.assertEqual(activated_tree(projected), projected)
        empty = base64.b64decode(activated_tree("").split("|")[1])
        self.assertEqual(empty[:31], b"\0" * 31)

    def test_growth_partial_awakening_reply_does_not_invent_other_fields_or_touch_other_owners(
        self,
    ):
        from guardian_tales.andras_trial_growth import activated_tree

        self.cli("enable")
        hero = {"Id": self.target, "AwakeningTree": ""}
        body = {
            "User": {"Id": self.owner, "Characters": [hero]},
            "OtherUser": {"Id": self.owner + 1, "Characters": [hero]},
        }
        reply = Packet(1, json.dumps(body).encode(), body_type=1)
        actual = json.loads(project_response(reply, load(self.store.references)).body)
        self.assertEqual(
            actual["User"]["Characters"], [{"Id": self.target, "AwakeningTree": activated_tree("")}]
        )
        self.assertEqual(actual["OtherUser"], body["OtherUser"])

    def test_growth_applies_exact_moderate_combat_changes_and_preserves_unrelated_binary_bytes(
        self,
    ):
        body, _ = prepare(self.original, 1, True)
        tables = records(decode(body))[1]
        actions = {r["Name"]: r for r in json.loads(tables["battleactions"][1])}
        self.assertEqual(actions["ManualDemonSlayer:First"]["ModifierBase"], 0.88)
        self.assertEqual(actions["ManualDemonSlayer:Third"]["ModifierBase"], 1.54)
        self.assertEqual(actions["RoleDemonSlayer"]["ModifierBase"], 0.275)
        self.assertEqual(actions["CwpDemonSlayer"]["ModifierBase"], 1.045)
        self.assertEqual(actions["CwpDemonSlayer"]["ModifierAdd"], 0.33)
        self.assertEqual(
            actions["BasicSupport:DemonSlayer"]["HitDpsMultipliers"], [0.36, 0.36, 0.36, 0.36, 2.16]
        )
        options = {r["Id"]: r for r in json.loads(tables["options"][1])}
        self.assertEqual(options[320488]["OverrideModifier"], 3.08)
        self.assertEqual(options[300488]["MythOptionId"], 20300488)
        buffs = {r["Id"]: r for r in json.loads(tables["buffs"][1])}
        self.assertEqual((buffs[3204880]["AttackScaleBase"], buffs[3204880]["Duration"]), (0.35, 6))
        self.assertEqual(
            (buffs[3204881]["DefenseScaleBase"], buffs[3204881]["Duration"]), (0.35, 6)
        )
        before = binary_rows(self.tables["battleactions-bin"], require_id=False)
        after = binary_rows(tables["battleactions-bin"][1], require_id=False)
        for old, new in zip(before, after):
            name = json.loads(old[2])["Name"]
            self.assertEqual(old[:2], new[:2])
            self.assertEqual(json.loads(new[2]), actions[name])
            if name in ("MythDokkaebi", "UnrelatedAction"):
                self.assertEqual(old, new)

    def test_growth_markers_display_matching_values_without_consuming_source_resources(self):
        from guardian_tales.andras_trial_growth import MARKERS

        before = list(self.db.iterdump())
        self.cli("enable")
        self.fetch()
        tables = records(decode(self.session.handle(request("/static-data/get", {})).body))[1]
        options = {r["Id"]: r for r in json.loads(tables["options"][1])}
        for ident in MARKERS[:3]:
            self.assertEqual(options[ident]["Increase"], 10)
            self.assertTrue(options[ident]["AwakenTitle"].endswith("_awaken"))
            self.assertEqual(options[ident]["AwakenDescription"], options[ident]["DescKey"])
        self.assertEqual(sum(options[MARKERS[3]]["HitDpsMultipliers"]), 3.6)
        self.assertEqual(options[MARKERS[4]]["BuffName"], "buff_demon_slayer_special_option")
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertFalse((self.state / "andras-myth-trial.sqlite3").exists())

    def test_growth_bad_awakening_encodings_reject_before_training_or_other_handler_writes(self):
        from guardian_tales.andras_trial_growth import activated_tree

        for value in (
            True,
            42,
            "bad",
            "AAAA|!!!!",
            "AA==|",
            "AAAAAA==|" + base64.b64encode(b"x" * 126).decode(),
        ):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                activated_tree(value)
        self.cli("enable")
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["AwakeningTree"] = "invalid"
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.fetch()
        self.assertEqual(list(self.db.iterdump()), before)
        self.cli("disable")
        self.assertEqual(self.fetch(), profile)

    def test_growth_missing_corrupt_and_conflicting_contracts_cannot_publish_active_configuration(
        self,
    ):
        original = copy.deepcopy(self.tables)
        changes = (
            lambda: self.tables.pop("battleactions-bin"),
            lambda: self.tables["charactertreeconfig"][0].update(TreeLayoutName="different"),
            lambda: self.tables["options"].append(dict(Id=20350488)),
            lambda: self.tables["options"].append(dict(Id=999999, Name="local_andras_myth_manual")),
            lambda: self.tables["options"][0].update(BattleActionName="other"),
            lambda: self.tables["buffs"][0].update(AttackScaleAdd=1),
            lambda: self.tables["awakeningtreenodes"]["stock_myth"].pop(),
            lambda: self.tables["awakeningnodelayout_client"]["layout_snowflake_01_myth"][
                "Circles"
            ][0].update(NodeIndex=9),
            lambda: self.tables["battleactions"][-1].update(ModifierBase=10),
            lambda: self.tables["awakeningnodedata"].update(NodeOptions=None),
            lambda: self.tables["awakeningnodedata"]["ResourcesToOpenNode"].clear(),
        )
        for change in changes:
            self.tables = copy.deepcopy(original)
            change()
            self.write_source()
            self.reject("enable")
            self.assertFalse((self.refs / SELECTION).exists())

    def test_bootstrap_get_and_check_share_active_and_restored_checksums(self):
        before = list(self.db.iterdump())
        self.db.execute("PRAGMA query_only=ON")
        previous = None
        for action in ("enable", "disable", "enable"):
            self.cli(action)
            body = self.session.handle(request("/static-data/get", {})).body
            checksum = records(decode(body))[1]["__checksum__"][1]
            for value, expected in ((checksum, True), (previous, False)):
                check = json.loads(
                    self.session.handle(
                        request("/static-data/check-update", {"Checksum": value})
                    ).body
                )
                self.assertEqual(check["Checksum"], checksum)
                self.assertEqual(check["UpToDate"], expected)
            previous = checksum
        self.assertEqual(list(self.db.iterdump()), before)

    def test_reply_projection_handles_partial_and_nested_resources_without_other_owners(self):
        self.cli("enable")
        selection = load(self.store.references)
        target = {"Id": self.target, "CharacterId": SOURCE, "Experience": 42}
        value = {
            "User": {"Id": self.owner, "Characters": [target]},
            "UserProfileCard": {"User": {"Id": self.owner, "Characters": [target]}},
            "OtherUser": {"Id": self.owner + 1, "Characters": [target]},
        }
        original = Packet(
            1, json.dumps(value).encode(), body_type=1, sequence_id=77, hint="synthetic"
        )
        result = project_response(original, selection)
        expected = json.loads(json.dumps(value))
        expected["User"]["Characters"][0]["CharacterId"] = VARIANT
        expected["UserProfileCard"]["User"]["Characters"][0]["CharacterId"] = VARIANT
        self.assertEqual(json.loads(result.body), expected)
        self.assertEqual(replace(result, body=original.body), original)
        self.assertEqual(json.loads(original.body), value)

    def test_unrelated_and_binary_replies_are_returned_unchanged(self):
        self.cli("enable")
        selection = load(self.store.references)
        for packet in (
            Packet(1),
            Packet(1, b"data", body_type=2),
            Packet(1, b'{"User":{"Cas":4}}', body_type=1),
            Packet(1, b'{"User":{"Characters":[{"Id":999,"CharacterId":490}]}}', body_type=1),
        ):
            self.assertIs(project_response(packet, selection), packet)

    def test_missing_wrong_or_multiple_owned_andras_cannot_be_enabled(self):
        profile = self.store.account.profile()
        for change in (
            lambda u: u["Characters"].clear(),
            lambda u: u["Characters"].append(dict(u["Characters"][0], Id=999)),
        ):
            modified = copy.deepcopy(profile)
            change(modified["User"])
            with self.db:
                self.db.execute(
                    "UPDATE local_account SET profile=? WHERE id=1", (json.dumps(modified),)
                )
            self.reject("enable")
            self.assertFalse((self.refs / SELECTION).exists())
        self.reject("enable", self.root / "missing")
        self.assertFalse((self.root / "missing").exists())

    def test_wrong_owner_and_changed_content_reject_before_handler_writes(self):
        self.cli("enable")
        path = self.refs / SELECTION
        original = load(self.store.references)
        before = list(self.db.iterdump())
        for change in (
            {"owner_id": self.owner + 1},
            {"source_sha256": "0" * 64},
            {"inventory_id": self.target + 1},
        ):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(PacketError):
                self.fetch()
        self.assertEqual(list(self.db.iterdump()), before)

    def training_catalog(self):
        from guardian_tales.campaign import FIRST_STAGE_ID

        profile = self.store.account.profile()
        profile["UserProgress"]["StageStates"][str(FIRST_STAGE_ID)] = 7
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        value = dict(
            client=CLIENT,
            free_experience=True,
            experience_by_level=[n * 100 for n in range(30)],
            caps=[{"opened_stage_id": 0, "max_level": 5}],
            character_ids=[SOURCE, 200],
            myth_ids=[],
            limit_break_coefficient=3,
            blessing_coefficient=5,
            myth_coefficient=2,
            max_limit_breaks=5,
            max_bless_level=3,
        )
        (self.refs / "imported_training_catalog.json").write_text(json.dumps(value))

    def train(self, amount, sequence=100):
        packet = request(
            "/user/add-character-experience", {"Experiences": {str(self.target): amount}}
        )
        packet["sequence_id"] = sequence
        return json.loads(self.session.handle(packet).body)

    def test_trial_hero_training_leaves_the_original_save_unchanged(self):
        from guardian_tales.andras_trial_training import state_path

        self.training_catalog()
        self.cli("enable")
        before = list(self.db.iterdump())
        changes = self.db.total_changes
        self.db.execute("PRAGMA query_only=ON")
        result = self.train(100)
        self.assertEqual(result["User"]["Characters"][0]["Experience"], 100)
        self.assertEqual(result["User"]["Characters"][0]["CharacterId"], VARIANT)
        self.assertTrue(state_path(self.db).is_file())
        self.assertEqual(self.store.account.profile()["User"]["Characters"][0]["Experience"], 0)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_trial_training_retries_and_old_replays_return_current_virtual_progress(self):
        from guardian_tales.andras_trial_training import state_path

        self.training_catalog()
        self.cli("enable")
        self.train(100, 100)
        path = state_path(self.db)
        with closing(sqlite3.connect(path)) as trial:
            before = list(trial.iterdump())
        self.assertEqual(self.train(100, 100)["User"]["Characters"][0]["Experience"], 100)
        with closing(sqlite3.connect(path)) as trial:
            self.assertEqual(list(trial.iterdump()), before)
        self.train(200, 101)
        self.assertEqual(self.train(100, 100)["User"]["Characters"][0]["Experience"], 300)
        with self.assertRaises(PacketError):
            self.train(150, 100)
        self.assertEqual(self.fetch()["User"]["Characters"][0]["Experience"], 300)

    def test_trial_training_reopens_and_disable_restores_original_while_retaining_trial_progress(
        self,
    ):
        self.training_catalog()
        self.cli("enable")
        self.train(700)
        reopened = BootstrapSession(GuestStore(self.db, self.refs))
        reopened.signed_in = True
        self.assertEqual(
            json.loads(reopened.handle(request("/auth/fetch-account", {})).body)["User"][
                "Characters"
            ][0]["Experience"],
            700,
        )
        self.cli("disable")
        normal = self.fetch()["User"]["Characters"][0]
        self.assertEqual((normal["CharacterId"], normal["Experience"]), (SOURCE, 0))
        self.cli("enable")
        self.assertEqual(self.fetch()["User"]["Characters"][0]["Experience"], 700)

    def test_trial_training_enforces_myth_cap_and_rejects_invalid_deltas_without_new_state(self):
        from guardian_tales.andras_trial_training import state_path

        self.training_catalog()
        self.cli("enable")
        for amount in (0, -1, True, 1.0, 701, 0x80000000):
            with self.subTest(amount=amount), self.assertRaises(PacketError):
                self.train(amount)
        self.assertFalse(state_path(self.db).exists())
        self.train(700)
        with self.assertRaises(PacketError):
            self.train(1, 101)
        self.assertEqual(self.fetch()["User"]["Characters"][0]["Experience"], 700)

    def test_trial_training_keeps_user_revisions_coherent_in_partial_and_unrelated_replies(self):
        self.training_catalog()
        self.cli("enable")
        original = self.store.account.profile()
        result = self.train(100)
        self.assertEqual(result["User"]["Cas"], original["User"]["Cas"] + 1)
        self.assertEqual(result["UserRecord"], original["UserRecord"])
        packet = Packet(
            1,
            json.dumps(
                {
                    "User": {
                        "Id": self.owner,
                        "Cas": original["User"]["Cas"],
                        "Characters": [{"Id": self.target, "Experience": 0}],
                    },
                    "UserRecord": original["UserRecord"],
                }
            ).encode(),
            body_type=1,
        )
        result = json.loads(project_response(packet, load(self.store.references), self.store).body)
        self.assertEqual(result["User"]["Cas"], original["User"]["Cas"] + 1)
        self.assertEqual(result["User"]["Characters"], [{"Id": self.target, "Experience": 100}])
        self.assertEqual(result["UserRecord"], original["UserRecord"])
        packet = replace(
            packet,
            body=json.dumps({"User": {"Id": self.owner, "Cas": original["User"]["Cas"]}}).encode(),
        )
        self.assertEqual(
            json.loads(project_response(packet, load(self.store.references), self.store).body)[
                "User"
            ]["Cas"],
            original["User"]["Cas"] + 1,
        )

    def test_trial_training_mixed_targets_and_unauthenticated_or_malformed_packets_cannot_write(
        self,
    ):
        from guardian_tales.andras_trial_training import state_path

        self.training_catalog()
        self.cli("enable")
        before = list(self.db.iterdump())
        mixed = request(
            "/user/add-character-experience", {"Experiences": {str(self.target): 100, "999": 100}}
        )
        with self.assertRaises(PacketError):
            self.session.handle(mixed)
        self.session.signed_in = False
        with self.assertRaises(PacketError):
            self.train(100)
        self.session.signed_in = True
        invalid = request(
            "/user/add-character-experience", {"Experiences": {str(self.target): 100}}
        )
        invalid["version"] = 2
        with self.assertRaises(PacketError):
            self.session.handle(invalid)
        self.assertFalse(state_path(self.db).exists())
        self.assertEqual(list(self.db.iterdump()), before)

    def test_trial_training_missing_catalog_and_revision_overflow_preserve_original(self):
        self.cli("enable")
        with self.assertRaises(PacketError):
            self.train(100)
        self.training_catalog()
        profile = self.store.account.profile()
        profile["User"]["Cas"] = 0x7FFFFFFFFFFFFFFF
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.train(100)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_trial_training_can_decode_compressed_request_bodies(self):
        self.training_catalog()
        self.cli("enable")
        payload = {"Experiences": {str(self.target): 100}}
        packet = request("/user/add-character-experience", payload)
        packet.update(body_type=2, body_hex=compress(json.dumps(payload).encode()).hex())
        result = json.loads(self.session.handle(packet).body)
        self.assertEqual(result["User"]["Characters"][0]["Experience"], 100)

    def test_trial_progress_is_bound_to_original_experience_and_never_overwrites_later_growth(self):
        self.training_catalog()
        self.cli("enable")
        self.train(100)
        self.cli("disable")
        profile = self.store.account.profile()
        profile["User"]["Characters"][0]["Experience"] = 50
        profile["User"]["Cas"] += 1
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        self.cli("enable")
        self.assertEqual(self.fetch()["User"]["Characters"][0]["Experience"], 50)
        self.train(100, 101)
        self.assertEqual(self.fetch()["User"]["Characters"][0]["Experience"], 150)
        self.cli("disable")
        self.assertEqual(self.fetch()["User"]["Characters"][0]["Experience"], 50)

    def test_trial_training_receipt_failure_rolls_back_sidecar_progress_and_revision(self):
        from guardian_tales.andras_trial_training import state_path

        self.training_catalog()
        self.cli("enable")
        self.train(100)
        with closing(sqlite3.connect(state_path(self.db))) as trial:
            trial.execute(
                "CREATE TRIGGER fail_receipt BEFORE INSERT ON requests BEGIN SELECT RAISE(ABORT,'synthetic'); END"
            )
            trial.commit()
            before = list(trial.iterdump())
        original = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.train(100, 101)
        with closing(sqlite3.connect(state_path(self.db))) as trial:
            self.assertEqual(list(trial.iterdump()), before)
        self.assertEqual(self.fetch()["User"]["Characters"][0]["Experience"], 100)
        self.assertEqual(list(self.db.iterdump()), original)

    def test_invalid_sidecar_can_be_disabled_without_touching_original_hero(self):
        from guardian_tales.andras_trial_training import state_path

        self.training_catalog()
        self.cli("enable")
        self.train(100)
        with closing(sqlite3.connect(state_path(self.db))) as trial:
            trial.execute("PRAGMA user_version=999")
        original = self.store.account.profile()
        with self.assertRaises(PacketError):
            self.fetch()
        self.cli("disable")
        self.assertEqual(self.fetch(), original)

    def test_repeated_enable_disable_and_status_are_configuration_noops(self):
        for action in ("enable", "disable"):
            self.cli(action)
            before = (self.refs / SELECTION).read_bytes()
            self.cli(action)
            self.cli("status")
            self.assertEqual((self.refs / SELECTION).read_bytes(), before)

    def test_failed_publication_retains_configuration_and_removes_temporary_file(self):
        self.cli("enable")
        before = {p.name: p.read_bytes() for p in self.refs.iterdir()}
        with patch(
            "guardian_tales.raid_static.atomic_replace", side_effect=OSError("disk failure")
        ):
            self.reject("disable")
        self.assertEqual({p.name: p.read_bytes() for p in self.refs.iterdir()}, before)

    def test_malformed_configuration_and_revision_overflow_do_not_write(self):
        self.cli("enable")
        path = self.refs / SELECTION
        original = load(self.store.references)
        for change in (
            {"version": True},
            {"active": 1},
            {"inventory_id": True},
            {"generation": -1},
        ):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(ValueError):
                load(self.store.references)
        path.write_text(json.dumps(dict(original, generation=0x7FFFFFFF)))
        before = path.read_bytes()
        self.reject("disable")
        self.assertEqual(path.read_bytes(), before)

    def test_binary_repacking_preserves_large_records_and_block_boundaries(self):
        rows = [
            (i, i + 100, json.dumps({"Id": i, "data": "x" * 30000}).encode()) for i in range(1, 5)
        ]
        self.assertEqual(binary_rows(pack_rows(rows)), rows)
        broken = base64.b64encode(b"bad").decode()
        with self.assertRaises(ValueError):
            binary_rows(broken)

    def test_collisions_and_mismatched_source_tables_are_rejected(self):
        for change in (
            lambda: self.heroes[0].update(Rank=5),
            lambda: self.heroes.append(dict(self.heroes[0], Id=VARIANT)),
            lambda: self.tables["items"].append({"Id": STONE}),
            lambda: self.heroes[0].update(Atk=99),
        ):
            old_heroes, old_items = copy.deepcopy(self.heroes), copy.deepcopy(self.tables["items"])
            change()
            self.write_source()
            self.reject("enable")
            self.assertFalse((self.refs / SELECTION).exists())
            self.heroes[:] = old_heroes
            self.tables["items"] = old_items
