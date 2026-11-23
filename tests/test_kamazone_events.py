# SPDX-License-Identifier: Apache-2.0
"""Seasonal event variety, persistent story continuations and local-only effects."""

import copy
import json
import random
import unittest
from unittest.mock import patch

from guardian_tales import kamazone_event_effects as effects
from guardian_tales import kamazone_events as events
from guardian_tales import kamazone_run as run
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.protocol import PacketError
from tests import test_kamazone_run as fixtures
from tests.test_snapshots import request


def choice(ident, event, *actions, condition="None", args=None):
    row = dict(Id=ident, EventId=event, ConditionType=condition, ConditionValue=args)
    for i, (kind, values) in enumerate([*actions, *(("None", None),) * (3 - len(actions))], 1):
        row.update({"EffectType" + str(i): kind, "EffectValue" + str(i): values})
    return row


class KamazoneEventTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazoneRunTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.owner.owner.practice("disable")
        self.session, self.db, self.root = self.owner.session, self.owner.db, self.owner.root
        profile = self.session.store.account.profile()
        for ident in (2, 3):
            row = copy.deepcopy(profile["User"]["Characters"][0])
            row["Id"] = ident
            profile["User"]["Characters"].append(row)
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        mode = self.owner.fixture.tables["kamazonland2"]
        mode["Constants"] = dict(ShelterHpRecover=0.4)
        mode["SpecialEvents"] = [
            dict(
                Id=i,
                Hidden=i in (2, 3),
                AppearFloor=0,
                Difficulty=None,
                WeightBase=1 if i == 1 else 0,
                WeightAdd=0,
                WeightConditionType="None",
                WeightConditionValue=None,
            )
            for i in (1, 2, 3, 4)
        ]
        mode["SpecialEvents"][1]["WeightBase"] = 1
        mode["SpecialEvents"][2]["WeightBase"] = 1
        mode["SpecialEventChoices"] = [
            choice(101, 1, ("GetCoin", [50]), ("DamageAll", [10])),
            choice(102, 1, ("HealAll", [20])),
            choice(103, 1, ("ProgressInChallenge", [2])),
            choice(104, 1, ("GetArtifactById", [901])),
            choice(105, 1, ("GetCurseById", [801])),
            choice(106, 1, ("ConcludeByWeight", [1001])),
            choice(107, 1, ("Battle", [1])),
            choice(108, 1, ("GetCap", [20])),
            choice(
                109, 1, ("LoseCoin", [20]), ("GetArtifactById", [902]), condition="Coin", args=[20]
            ),
            choice(201, 2, ("GetArtifactById", [902]), ("ProgressInSeason", [3])),
            choice(301, 3, ("HealRandomOne", [20]), ("ProgressInSeason", [0])),
            choice(401, 4, ("None", None)),
        ]
        mode["RandomConclusions"] = [
            dict(choice(1, 1, ("GetCoin", [11])), ConclusionId=1001, Priority=0, Weight=1),
            dict(
                choice(2, 1, ("GetCoin", [22])),
                ConclusionId=1001,
                Priority=1,
                Weight=1,
                ConditionType="EventChoiceProgress",
                ConditionValue=[103],
            ),
        ]
        mode["Artifacts"] = [
            dict(Id=i, Kind="Normal", Rarity=i - 901, Lootable=True, Price=40) for i in (901, 902)
        ] + [dict(Id=801, Kind="Curse")]
        for season in mode["Seasons"]:
            season.update(
                SpecialEvents=[1, 2, 3, 4],
                Artifacts=[901, 902],
                ArtifactsException=[],
                ArtifactsCurse=[801],
            )
        for row in mode["FloorPresets"]:
            if row["Id"] in (110, 111):
                for kind in run.PROBABILITIES:
                    row[kind + "Prob"] = int(
                        (row["Id"], kind) in ((110, "Special"), (111, "Normal"))
                    )
            if row["Id"] == 120:
                row.update(NextNodeIds=[130])
                for kind in run.PROBABILITIES:
                    row[kind + "Prob"] = int(kind == "Special")
        mode["FloorPresets"].append(dict(Id=130, FloorId=1, Step=3, NextNodeIds=None))
        self.owner.fixture.write_source()
        self.owner.owner.command("select", "--season-id", "43")
        self.sequence = 11000
        self.before = list(self.db.iterdump()), self.db.total_changes
        self.files = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.static = self.session.handle(request("/static-data/get", {})).body
        self.initial = self.call(run.CHALLENGE, {"Difficulty": 3})["UserKamazonLand"]
        self.path = self.root / run.STATE
        self.source = self.session.store.references.read_bytes("static_data_get.bin")
        self.initial_seed = run.load(self.session.store.references)["seed"]
        self.map = copy.deepcopy(
            run.floor_nodes(self.source, 43, run.load(self.session.store.references)["seed"])
        )

    def call(self, route, body, sequence=None):
        self.sequence += 1
        packet = request(route, body)
        packet["sequence_id"] = self.sequence if sequence is None else sequence
        response = self.session.handle(packet)
        self.assertEqual(
            (response.packet_type, response.body_type, response.sequence_id),
            (1, 1, packet["sequence_id"]),
        )
        return json.loads(response.body)

    def entry(self):
        return self.call("/kamazonland/enter", {"IsPartial": False})["UserKamazonLand"]

    def open(self, ident=110):
        return self.call(run.START, {"NodeId": ident})["UserKamazonLand"]

    def choose(self, choice_id, ident=110, sequence=None):
        return self.call(events.CHOOSE, {"NodeId": ident, "ChoiceId": choice_id}, sequence)[
            "UserKamazonLand"
        ]

    def close(self, ident=110, **fields):
        return self.call(events.CLOSE, {"NodeId": ident, **fields})["UserKamazonLand"]

    def seed(self, **changes):
        value = json.loads(self.path.read_bytes())
        value.update(changes)
        self.path.write_text(json.dumps(value))

    def reject(self, route, body):
        before = self.path.read_bytes()
        with self.assertRaises(PacketError):
            self.call(route, body)
        self.assertEqual(self.path.read_bytes(), before)

    def untouched(self):
        self.assertEqual((list(self.db.iterdump()), self.db.total_changes), self.before)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != run.STATE}, self.files
        )
        self.assertEqual(self.session.handle(request("/static-data/get", {})).body, self.static)
        self.assertEqual(run.floor_nodes(self.source, 43, self.initial_seed), self.map)

    def node(self, user, ident=110):
        return next(n for n in user["Nodes"] if n["Id"] == ident)

    def test_special_entry_has_real_choices_unchosen_flags_stable_reopen_and_no_fake_battle(self):
        user = self.open()
        node = self.node(user)
        self.assertTrue(node["SpecialEventChoices"])
        self.assertTrue(all(v is False for v in node["SpecialEventChoices"].values()))
        self.assertNotIn("107", node["SpecialEventChoices"])
        self.assertNotIn("108", node["SpecialEventChoices"])
        self.assertNotIn("109", node["SpecialEventChoices"])
        self.assertEqual(user["KnownEvents"], [1])
        self.assertEqual(self.open(), user)
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.assertEqual(self.entry(), user)
        self.reject(run.BATTLE, dict(NodeId=110, Formation=[12, 3, 19, 9]))
        self.reject(run.START, {"NodeId": 120})
        self.untouched()

    def test_choice_updates_local_coin_hp_and_native_chosen_flag_only_once(self):
        self.seed(hps={"1": 5000, "2": 0, "3": 9000})
        self.open()
        user = self.choose(101, sequence=111)
        self.assertEqual(user["SilverCoin"], 50)
        self.assertEqual(user["Hps"], {"1": 4000, "2": 0, "3": 8000})
        node = self.node(user)
        self.assertEqual(node["State"], 9)
        self.assertEqual(self.open(), user)
        self.assertEqual([k for k, v in node["SpecialEventChoices"].items() if v], ["101"])
        self.assertTrue(
            all(set(r) == {"Type", "Targets", "Values"} for r in node["ChoiceEffectResults"])
        )
        self.assertEqual(self.choose(101), user)
        saved = self.path.read_bytes()
        self.assertEqual(self.choose(101, sequence=111), user)
        self.assertEqual(self.path.read_bytes(), saved)
        self.reject(events.CHOOSE, dict(NodeId=110, ChoiceId=102))
        self.reject(run.START, {"NodeId": 120})
        closed = self.close()
        self.assertEqual(self.node(closed)["State"], 11)
        self.assertEqual(closed["SilverCoin"], 50)
        self.open(120)
        self.untouched()

    def test_artifact_and_curse_grants_are_deferred_to_nullable_native_confirm_lists(self):
        for option, key, expected in ((104, "Artifact", 901), (105, "Curse", 801)):
            with self.subTest(option=option):
                self.call(run.CHALLENGE, {"Difficulty": 3})
                self.open()
                user = self.choose(option)
                self.assertEqual(user["Artifacts"], [])
                self.assertEqual(user["Curses"], [])
                self.reject(events.CLOSE, dict(NodeId=110, **{"Loot" + key + "Ids": [999]}))
                user = self.close(
                    **{"Loot" + key + "Ids": [expected], "Discard" + key + "Indices": [None]}
                )
                self.assertEqual(
                    (
                        effects.ids(run.load(self.session.store.references))
                        if key == "Artifact"
                        else user["Curses"]
                    ),
                    [expected],
                )
                self.assertEqual(self.entry(), user)
        self.untouched()

    def test_season_story_continues_after_new_challenge_and_challenge_story_resets(self):
        self.open()
        user = self.choose(103)
        self.assertEqual(user["ProgressInChallenge"], {"1": [103]})
        self.close()
        next_user = self.open(120)
        self.assertEqual(set(self.node(next_user, 120)["SpecialEventChoices"]), {"201"})
        self.choose(201, 120)
        self.close(120, LootArtifactIds=[902], DiscardArtifactIndices=[None])
        fresh = self.call(run.CHALLENGE, {"Difficulty": 3})["UserKamazonLand"]
        self.assertEqual(fresh["ProgressInChallenge"], {})
        self.assertEqual(fresh["ProgressInSeason"], {"1": [103, 201]})
        self.assertEqual(fresh["Artifacts"], [])
        user = self.open()
        self.assertEqual(set(self.node(user)["SpecialEventChoices"]), {"301"})
        self.choose(301)
        self.close()
        self.assertEqual(
            run.load(self.session.store.references)["event_progress"]["season"]["1"]["next"], 0
        )
        self.untouched()

    def test_challenge_only_story_is_removed_but_known_choices_survive_a_restart(self):
        self.open()
        self.choose(103)
        self.close()
        self.call(run.CHALLENGE, {"Difficulty": 3})
        user = self.open()
        self.assertIn("103", self.node(user)["SpecialEventChoices"])
        self.assertEqual(user["ProgressInChallenge"], {})
        self.assertEqual(user["KnownChoices"], [103])
        self.untouched()

    def test_random_conclusion_respects_priority_conditions_and_never_rerolls_on_retry(self):
        self.seed(known_choices=[103])
        self.open()
        user = self.choose(106)
        self.assertEqual(user["KnownRandomConclusions"], [2])
        self.assertEqual(user["SilverCoin"], 22)
        self.assertIn(
            dict(Type="ConcludeByWeight", Targets=[], Values=[2]),
            self.node(user)["ChoiceEffectResults"],
        )
        self.assertEqual(self.choose(106), user)
        self.untouched()

    def test_seeded_selection_varies_across_runs_preserves_original_rolls_and_gates_hidden_events(
        self,
    ):
        value = run.load(self.session.store.references)
        data = copy.deepcopy(events.catalog(self.source, 43))
        data["events"][4]["WeightBase"] = 1
        pool = events.available(data, value, {1, 2, 3})
        self.assertEqual({r[0] for r in pool}, {1, 4})
        sampled = {
            events.rng_for(dict(value, seed=i), 110, "event").choices(pool, [r[3] for r in pool])[
                0
            ][0]
            for i in range(30)
        }
        self.assertEqual(sampled, {1, 4})
        data["events"][1].update(
            WeightConditionType="EventChoiceProgress", WeightConditionValue=[103], WeightAdd=-1
        )
        value["known_choices"] = [103]
        self.assertEqual({r[0] for r in events.available(data, value, {1})}, {4})
        self.untouched()

    def test_full_inventory_replacement_or_decline_cannot_create_or_drop_unoffered_items(self):
        rows = [dict(Id=902, Shelter=0, Battle=0, EliminateArtifact=0) for _ in range(8)]
        self.seed(artifacts=rows)
        self.open()
        self.choose(104)
        self.reject(events.CLOSE, dict(NodeId=110, LootArtifactIds=[901]))
        self.reject(
            events.CLOSE, dict(NodeId=110, LootArtifactIds=[None], DiscardArtifactIndices=[0])
        )
        user = self.close(LootArtifactIds=[901], DiscardArtifactIndices=[2])
        self.assertEqual(len(user["Artifacts"]), 8)
        self.assertEqual(user["Artifacts"][2]["Id"], 901)
        self.assertTrue(
            all(r["EliminateArtifact"] == 1 for i, r in enumerate(user["Artifacts"]) if i != 2)
        )
        self.assertEqual(self.close(LootArtifactIds=[901], DiscardArtifactIndices=[2]), user)
        self.reject(
            events.CLOSE, dict(NodeId=110, LootArtifactIds=[901], DiscardArtifactIndices=[1])
        )
        self.untouched()

    def test_choice_authentication_phase_payload_and_failed_publication_guards_are_atomic(self):
        self.reject(events.CHOOSE, dict(NodeId=110, ChoiceId=101))
        self.open()
        for body in (
            {},
            dict(NodeId=110, ChoiceId=True),
            dict(NodeId=110, ChoiceId=107),
            dict(NodeId=120, ChoiceId=101),
        ):
            self.reject(events.CHOOSE, body)
        self.reject(events.CLOSE, dict(NodeId=110))
        self.session.signed_in = False
        self.reject(events.CHOOSE, dict(NodeId=110, ChoiceId=101))
        self.session.signed_in = True
        with patch("guardian_tales.kamazone_run.atomic_write", side_effect=OSError("synthetic")):
            self.reject(events.CHOOSE, dict(NodeId=110, ChoiceId=101))
        self.assertEqual(self.entry()["SilverCoin"], 0)
        self.untouched()

    def test_legacy_fields_default_in_memory_and_foreign_event_state_rejects_without_rewrite(self):
        value = json.loads(self.path.read_bytes())
        for key in events.defaults():
            del value[key]
        self.path.write_text(json.dumps(value))
        saved = self.path.read_bytes()
        self.assertEqual(self.entry(), self.initial)
        self.assertEqual(self.path.read_bytes(), saved)
        self.open()
        saved = self.path.read_bytes()
        invalid_results = copy.deepcopy(json.loads(saved)["events"])
        invalid_results["110"]["results"] = [dict(Type=[], Targets=[], Values=[])]
        for changes in (
            dict(events={"120": dict(json.loads(saved)["events"]["110"], event_id=999)}),
            dict(known_choices=[999]),
            dict(silver_coin=-1),
            dict(events=invalid_results),
        ):
            value = json.loads(saved)
            value.update(changes)
            self.path.write_text(json.dumps(value))
            self.reject("/kamazonland/enter", {"IsPartial": False})
        self.path.write_bytes(saved)
        self.untouched()

    def test_hp_effects_keep_dead_heroes_dead_except_revive_and_emit_grouped_all_descriptions(self):
        value = run.load(self.session.store.references)
        value["hps"] = {"1": 9500, "2": 0, "3": 3000}
        data = events.catalog(self.source, 43)
        visit = dict(pending_artifacts=[], pending_curses=[])
        result = effects.apply(value, data, "HealAll", [20], {1, 2, 3}, random.Random(1), visit)
        self.assertEqual(value["hps"], {"1": 10000, "2": 0, "3": 5000})
        self.assertEqual(result, dict(Type="HealAll", Targets=[], Values=[2000]))
        result = effects.apply(
            value, data, "DamageRandomOne", [10], {1, 2, 3}, random.Random(1), visit
        )
        self.assertEqual(len(result["Targets"]), 1)
        self.assertEqual(value["hps"]["2"], 0)
        result = effects.apply(value, data, "Revive", [1], {1, 2, 3}, random.Random(1), visit)
        self.assertEqual(result["Targets"], [2])
        self.assertEqual(value["hps"]["2"], 10000)

    def test_rarity_all_grants_and_removal_effects_use_catalog_ids_and_local_artifact_counters(
        self,
    ):
        value = run.load(self.session.store.references)
        data = events.catalog(self.source, 43)
        visit = dict(pending_artifacts=[], pending_curses=[])
        rng = random.Random(5)
        self.assertEqual(
            effects.apply(value, data, "GetArtifactByRarity", [1], {1}, rng, visit)["Targets"],
            [902],
        )
        self.assertEqual(
            effects.apply(value, data, "GetArtifactByIdAll", [901, 902], {1}, rng, visit)[
                "Targets"
            ],
            [901, 902],
        )
        effects.grant(
            value, visit, dict(LootArtifactIds=[902, 901, 902], DiscardArtifactIndices=[None] * 3)
        )
        self.assertEqual(effects.ids(value), [902, 901, 902])
        removed = effects.apply(value, data, "LoseArtifact", [902], {1}, rng, visit)
        self.assertEqual(removed["Targets"], [902])
        self.assertEqual(effects.ids(value), [901, 902])
        removed = effects.apply(value, data, "LoseArtifactByIdAll", [902], {1}, rng, visit)
        self.assertEqual(removed["Targets"], [902])
        self.assertEqual(value["artifacts"][0]["EliminateArtifact"], 2)
        self.assertEqual(
            effects.apply(value, data, "LoseRandomArtifact", [1], {1}, rng, visit)["Targets"], [901]
        )
        self.assertEqual(value["artifacts"], [])
        self.untouched()

    def test_coin_condition_cost_and_all_artifact_conditions_are_rechecked_against_local_state(
        self,
    ):
        self.seed(silver_coin=50)
        self.open()
        user = self.choose(109)
        self.assertEqual(user["SilverCoin"], 30)
        user = self.close(LootArtifactIds=[902], DiscardArtifactIndices=[None])
        value = run.load(self.session.store.references)
        for kind, args, expected in (
            ("Coin", [30], True),
            ("Coin", [31], False),
            ("Artifact", [902], True),
            ("Artifact", [901, 902], False),
            ("ArtifactAny", [901, 902], True),
            ("ArtifactCount", [1], True),
            ("Curse", [801], False),
            ("Hero", [1], False),
        ):
            self.assertEqual(events.condition(kind, args, value, {1}), expected)
        self.untouched()

    def test_equivalent_empty_closures_retry_and_failed_confirm_never_publish_a_reward(self):
        self.open()
        self.choose(104)
        with patch("guardian_tales.kamazone_run.atomic_write", side_effect=OSError("synthetic")):
            self.reject(
                events.CLOSE, dict(NodeId=110, LootArtifactIds=[901], DiscardArtifactIndices=[None])
            )
        self.assertEqual(self.entry()["Artifacts"], [])
        self.close(LootArtifactIds=[None], DiscardArtifactIndices=[None])
        self.assertEqual(self.entry()["Artifacts"], [])
        self.call(run.CHALLENGE, {"Difficulty": 3})
        self.open()
        self.choose(102)
        user = self.close()
        self.assertEqual(
            self.close(
                LootArtifactIds=[],
                DiscardArtifactIndices=[],
                LootCurseIds=[],
                DiscardCurseIndices=[],
            ),
            user,
        )
        self.untouched()

    def test_artifact_battle_counter_increments_once_when_the_battle_result_is_retried(self):
        self.open()
        self.choose(104)
        self.close(LootArtifactIds=[901], DiscardArtifactIndices=[None])
        self.open(120)
        self.choose(102, 120)
        self.close(120)
        self.call(run.SELECT, {"CharacterIds": [1]})
        self.open(130)
        user = self.call(run.BATTLE, dict(NodeId=130, Formation=[12, 3, 19, 9]))["UserKamazonLand"]
        monsters = next(n for n in user["Nodes"] if n["Id"] == 130)["BattleMonsters"]
        body = dict(NodeId=130, Result=1, CharacterHps={"1": 10000}, MonsterHps=[0] * len(monsters))
        first = self.call("/kamazonland/end-battle", body)["UserKamazonLand"]
        self.assertEqual(first["Artifacts"][0]["Battle"], 1)
        self.assertEqual(self.call("/kamazonland/end-battle", body)["UserKamazonLand"], first)
        self.untouched()
