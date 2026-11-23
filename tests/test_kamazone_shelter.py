# SPDX-License-Identifier: Apache-2.0
"""Shelter rest/revive/purify and leaving without a choice preserve the account."""

import copy
import json
import unittest
from unittest.mock import patch

from guardian_tales import kamazone_run as run
from guardian_tales import kamazone_shelter as shelter
from guardian_tales.bootstrap import BootstrapSession
from guardian_tales.protocol import PacketError
from tests import test_kamazone_run as fixtures
from tests.test_snapshots import request


class KamazoneShelterTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.KamazoneRunTests()
        self.addCleanup(self.owner.doCleanups)
        self.owner.setUp()
        self.session, self.db, self.root = self.owner.session, self.owner.db, self.owner.root
        # Three synthetic owned IDs distinguish recovery of living heroes from
        # resurrecting exactly one defeated hero; no external account is used.
        profile = self.session.store.account.profile()
        for ident in (2, 3):
            hero = copy.deepcopy(profile["User"]["Characters"][0])
            hero["Id"] = ident
            profile["User"]["Characters"].append(hero)
        with self.db:
            self.db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),))
        self.owner.owner.practice("disable")
        mode = self.owner.fixture.tables["kamazonland2"]
        mode["Constants"] = {"ShelterHpRecover": 0.4}
        for season in mode["Seasons"]:
            season["ArtifactsCurse"] = [801, 802]
        for row in mode["FloorPresets"]:
            if row["Id"] in (110, 111):
                for kind in run.PROBABILITIES:
                    row[kind + "Prob"] = int(
                        (row["Id"], kind) in ((110, "Normal"), (111, "Shelter"))
                    )
        self.owner.fixture.write_source()
        self.owner.owner.command("select", "--season-id", "43")
        self.owner.owner.enable()
        self.owner.owner.save({"174": 1}, 951)
        self.sequence = 8000
        self.before = list(self.db.iterdump()), self.db.total_changes
        self.files = {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != run.STATE}
        self.static = self.session.handle(request("/static-data/get", {})).body
        self.initial = self.call(run.CHALLENGE, {"Difficulty": 3})["UserKamazonLand"]
        self.path = self.root / run.STATE
        self.source = self.session.store.references.read_bytes("static_data_get.bin")
        state = run.load(self.session.store.references)
        self.map = copy.deepcopy(run.floor_nodes(self.source, 43, state["seed"]))

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

    def open(self):
        return self.call(run.START, {"NodeId": 111})["UserKamazonLand"]

    def take(self, choice, sequence=None):
        return self.call(shelter.TAKE, dict(NodeId=111, ChoiceType=choice), sequence)

    def seed(self, **changes):
        value = json.loads(self.path.read_bytes())
        value.update(changes)
        self.path.write_text(json.dumps(value))

    def reject(self, route, body):
        before = self.path.read_bytes()
        with self.assertRaises(PacketError):
            self.call(route, body)
        self.assertEqual(self.path.read_bytes(), before)

    def unchanged(self, user):
        self.assertEqual((list(self.db.iterdump()), self.db.total_changes), self.before)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.root.iterdir() if p.name != run.STATE}, self.files
        )
        self.assertEqual(self.session.handle(request("/static-data/get", {})).body, self.static)
        self.assertEqual(
            run.floor_nodes(self.source, 43, run.load(self.session.store.references)["seed"]),
            self.map,
        )
        for key in (
            "Characters",
            "Benefits",
            "KamazonPoint",
            "KamazonPointTotal",
            "SilverCoin",
            "Artifacts",
        ):
            self.assertEqual(user[key], self.initial[key], key)

    def test_rest_recovers_original_percentage_for_living_heroes_caps_hp_and_preserves_dead(self):
        self.seed(hps={"1": 2000, "2": 0, "3": 9000})
        opened = self.open()
        self.assertEqual(next(n for n in opened["Nodes"] if n["Id"] == 111)["State"], 3)
        self.assertEqual(opened["Progress"]["Shelter"], 1)
        result = self.take(1, 901)
        self.assertEqual(
            set(result), {"NewSeason", "UserKamazonLand", "ChoiceEffectResults", "AddedItems"}
        )
        self.assertEqual((result["ChoiceEffectResults"], result["AddedItems"]), ([], []))
        user = result["UserKamazonLand"]
        self.assertEqual(user["Hps"], {"1": 6000, "2": 0, "3": 10000})
        self.assertEqual(next(n for n in user["Nodes"] if n["Id"] == 111)["State"], 11)
        self.assertEqual(self.take(1)["UserKamazonLand"], user)
        before = self.path.read_bytes()
        self.take(1, 901)
        self.assertEqual(self.path.read_bytes(), before)
        self.session = BootstrapSession(self.session.store)
        self.session.signed_in = True
        self.assertEqual(self.entry(), user)
        self.unchanged(user)

    def test_revive_restores_exactly_one_random_dead_hero_and_retry_never_revives_another(self):
        self.seed(hps={"1": 0, "2": 0, "3": 5000})
        self.open()
        user = self.take(2)["UserKamazonLand"]
        self.assertEqual(sorted(user["Hps"].values()), [0, 5000, 10000])
        self.assertEqual(user["Hps"]["3"], 5000)
        self.assertEqual(self.take(2)["UserKamazonLand"], user)
        self.reject(shelter.TAKE, dict(NodeId=111, ChoiceType=1))
        self.unchanged(user)

    def test_purify_removes_one_seasonal_curse_once_without_rewards(self):
        self.seed(curses=[801, 802])
        self.open()
        user = self.take(3)["UserKamazonLand"]
        self.assertEqual(len(user["Curses"]), 1)
        self.assertIn(user["Curses"][0], (801, 802))
        self.assertEqual(self.take(3)["UserKamazonLand"], user)
        self.unchanged(user)

    def test_leaving_without_a_choice_advances_without_a_missing_close_api_or_free_heal(self):
        self.seed(hps={"1": 2000})
        self.open()
        self.open()
        self.assertEqual(self.entry()["Progress"]["Shelter"], 1)
        self.reject(run.START, {"NodeId": 100})
        user = self.call(run.START, {"NodeId": 120})["UserKamazonLand"]
        value = run.load(self.session.store.references)
        self.assertEqual(value["shelters"]["111"]["choice"], 0)
        self.assertEqual(value["states"]["111"], 11)
        self.assertEqual(user["Hps"]["1"], 2000)
        self.reject(shelter.TAKE, dict(NodeId=111, ChoiceType=1))
        self.unchanged(user)

    def test_explicit_no_action_closes_the_shelter_without_changing_hp(self):
        self.seed(hps={"1": 2000})
        self.open()
        user = self.take(0)["UserKamazonLand"]
        self.assertEqual(user["Hps"]["1"], 2000)
        self.assertEqual(run.load(self.session.store.references)["shelters"]["111"]["choice"], 0)
        self.reject(shelter.TAKE, dict(NodeId=111, ChoiceType=1))
        self.unchanged(user)

    def test_choice_guards_reject_unopened_foreign_malformed_and_unavailable_actions(self):
        self.reject(shelter.TAKE, dict(NodeId=111, ChoiceType=1))
        self.open()
        for body in (
            {},
            dict(NodeId=120, ChoiceType=1),
            dict(NodeId=True, ChoiceType=1),
            dict(NodeId=111, ChoiceType=True),
            dict(NodeId=111, ChoiceType=4),
            dict(NodeId=111, ChoiceType="Rest"),
            dict(NodeId=111, ChoiceType=2),
            dict(NodeId=111, ChoiceType=3),
        ):
            self.reject(shelter.TAKE, body)
        self.reject(run.BATTLE, dict(NodeId=111, Formation=[12, 3, 19, 9]))
        self.unchanged(self.entry())

    def test_failed_open_or_take_publication_and_unsigned_requests_are_atomic(self):
        self.seed(hps={"1": 2000})
        for route, body in (
            (run.START, {"NodeId": 111}),
            (shelter.TAKE, dict(NodeId=111, ChoiceType=1)),
        ):
            self.session.signed_in = False
            self.reject(route, body)
            self.session.signed_in = True
            with patch(
                "guardian_tales.kamazone_run.atomic_write", side_effect=OSError("synthetic")
            ):
                self.reject(route, body)
            if route == run.START:
                self.open()
        self.assertEqual(self.entry()["Hps"]["1"], 2000)
        self.unchanged(self.entry())

    def test_old_run_defaults_and_invalid_shelter_or_curse_data_never_rewrite_on_read(self):
        old = json.loads(self.path.read_bytes())
        for key in shelter.defaults():
            del old[key]
        self.path.write_text(json.dumps(old))
        before = self.path.read_bytes()
        self.assertEqual(self.entry(), self.initial)
        self.assertEqual(self.path.read_bytes(), before)
        self.open()
        saved = self.path.read_bytes()
        for changes in (
            dict(curses=[999]),
            dict(shelters={"120": {"choice": None}}),
            dict(shelters={"111": {"choice": 4}}),
        ):
            value = json.loads(saved)
            value.update(changes)
            self.path.write_text(json.dumps(value))
            self.reject("/kamazonland/enter", {"IsPartial": False})
        self.path.write_bytes(saved)
        self.unchanged(self.entry())
