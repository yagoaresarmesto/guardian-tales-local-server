# SPDX-License-Identifier: Apache-2.0
"""Kama-ZONE artifact retention and starting aid requests across run boundaries."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

from guardian_tales.modes.kamazone import kamazone_aids as aids
from guardian_tales.modes.kamazone import kamazone_run as run
from guardian_tales.runtime.bootstrap import BootstrapSession
from guardian_tales.runtime.protocol import PacketError
from tests.content import test_kamazone_run as fixtures


class KamazoneAidTests(unittest.TestCase):
    def setUp(self):
        self.game = fixtures.KamazoneRunTests()
        self.addCleanup(self.game.doCleanups)
        self.game.setUp()
        mode = self.game.fixture.tables["kamazonland2"]
        mode.setdefault("Constants", {})["ShelterHpRecover"] = 0.3
        mode["Artifacts"] = [
            dict(Id=i, Kind="Normal", Rarity=rarity, Lootable=i != 14)
            for i, rarity in ((10, 0), (11, 2), (12, 4), (13, 5), (14, 1), (15, 1))
        ] + [dict(Id=801, Kind="Curse", Rarity=3)]
        mode["Artifacts"][0].update(EffectType="CoinBonus", EffectValue=[10])
        benefits = ("ArtifactKeep", "ArtifactAid", "CurseAid", "SilverCoinAid")
        for i, effect in enumerate(benefits, 101):
            mode["Benefits"].append(
                dict(
                    Id=i,
                    EffectType=effect,
                    MaxLevel=1,
                    Points=[250],
                    OpenType="None",
                    EffectValue1=[150] if i == 104 else None,
                )
            )
        for season in mode["Seasons"]:
            season.update(
                Artifacts=list(range(10, 16)), ArtifactsCurse=[801], ArtifactsException=[15]
            )
            season["Benefits"].extend(range(101, 105))
        self.game.fixture.write_source()
        self.game.owner.command("select", "--season-id", "43")
        self.game.owner.save({str(i): 1 for i in range(101, 105)}, 555)
        self.path = self.game.root / run.STATE
        self.call = self.game.call
        self.game.files = {p.name: p.read_bytes() for p in self.game.root.iterdir()}
        self.game.static = self.game.session.handle(fixtures.request("/static-data/get", {})).body

    def pick(self, item=None, curse=None):
        return self.call(aids.PICK, dict(ArtifactId=item, CurseId=curse))

    def finish(self, ident=None):
        return self.call(run.CONCLUDE, {"keepingArtifactId": ident})

    def reject(self, route, body):
        original = self.path.read_bytes()
        with self.assertRaises(PacketError):
            self.call(route, body)
        self.assertEqual(self.path.read_bytes(), original)

    def test_pick_separately_or_together_reopen_and_keep_one_across_difficulties(self):
        opening = self.game.challenge()
        self.assertTrue(opening["Progress"]["CanPickArtifactAid"])
        self.assertTrue(opening["Progress"]["CanPickCurseAid"])
        self.assertEqual(opening["SilverCoin"], 150)
        first = self.pick(10)
        self.assertFalse(first["Progress"]["CanPickArtifactAid"])
        self.assertTrue(first["Progress"]["CanPickCurseAid"])
        self.assertEqual(self.pick(10), first)
        both = self.pick(curse=801)
        self.assertEqual(self.pick(10, 801), both)
        self.assertEqual(self.game.challenge(), both)
        self.assertEqual(both["Curses"], [801])
        self.game.session = BootstrapSession(self.game.session.store)
        self.game.session.signed_in = True
        self.assertEqual(self.game.entry(), both)
        self.call(run.START, {"NodeId": self.game.opening(both)["Id"]})
        ended = self.finish(10)
        self.assertEqual(ended["Progress"]["KeepingArtifactId"], 10)
        self.assertEqual(self.finish(10), ended)
        self.assertEqual(self.game.entry(), ended)
        for other in (None, 11):
            self.reject(run.CONCLUDE, {"keepingArtifactId": other})
        fresh = self.game.challenge(1)
        self.assertEqual(
            fresh["Artifacts"], [dict(Id=10, Shelter=0, Battle=0, EliminateArtifact=0)]
        )
        self.assertEqual(fresh["Curses"], [])
        self.assertEqual((both["SilverCoin"], fresh["SilverCoin"]), (150, 160))
        self.assertIsNone(fresh["Progress"]["KeepingArtifactId"])
        self.assertEqual(self.game.challenge(1), fresh)
        combined = self.pick(11, 801)
        self.assertEqual([r["Id"] for r in combined["Artifacts"]], [10, 11])
        self.call(run.START, {"NodeId": self.game.opening(fresh)["Id"]})
        self.finish()
        self.assertEqual(self.game.challenge()["Artifacts"], [])
        self.game.assert_untouched()

    def test_invalid_or_expired_aids_do_not_partially_grant_or_change_eligibility(self):
        opening = self.game.challenge()
        for body in (
            {},
            dict(ArtifactId=None, CurseId=None),
            dict(ArtifactId=True, CurseId=None),
            dict(ArtifactId=10, CurseId=888),
            dict(ArtifactId=12, CurseId=None),
            dict(ArtifactId=14, CurseId=None),
            dict(ArtifactId=15, CurseId=None),
            dict(ArtifactId=801, CurseId=None),
            dict(ArtifactId=None, CurseId=10),
        ):
            self.reject(aids.PICK, body)
        self.pick(10)
        self.reject(aids.PICK, dict(ArtifactId=11, CurseId=801))
        active = self.call(run.START, {"NodeId": self.game.opening(opening)["Id"]})
        self.assertFalse(active["Progress"]["CanPickCurseAid"])
        self.reject(aids.PICK, dict(ArtifactId=None, CurseId=801))
        self.reject(run.CONCLUDE, {"keepingArtifactId": 11})
        self.game.assert_untouched()

    def test_legacy_owned_items_duplicates_rarity_and_disabled_benefits(self):
        opening = self.game.challenge()
        self.call(run.START, {"NodeId": self.game.opening(opening)["Id"]})
        legacy = json.loads(self.path.read_bytes())
        del legacy["keeping_artifact_id"], legacy["opening_aids"]
        legacy["artifacts"] = [
            dict(Id=i, Shelter=8, Battle=7, EliminateArtifact=2) for i in (10, 10, 12, 13)
        ]
        self.path.write_text(json.dumps(legacy))
        for i in (12, 13):
            self.reject(run.CONCLUDE, {"keepingArtifactId": i})
        self.game.owner.save({}, 556)
        self.reject(run.CONCLUDE, {"keepingArtifactId": 10})
        self.game.owner.save({"101": 1}, 557)
        self.finish(10)
        kept = self.game.challenge()
        self.assertEqual(kept["Artifacts"], [dict(Id=10, Shelter=0, Battle=0, EliminateArtifact=0)])
        self.assertEqual(kept["SilverCoin"], 0)
        self.reject(aids.PICK, dict(ArtifactId=10, CurseId=None))
        self.call(run.START, {"NodeId": self.game.opening(kept)["Id"]})
        self.finish(10)
        self.game.owner.save({}, 558)
        self.assertEqual(self.game.challenge()["Artifacts"], [])

    def test_simultaneous_starting_picks_preserve_both_choices(self):
        self.game.challenge()
        profile = self.game.session.store.account.profile()
        refs = self.game.session.store.references
        source = refs.read_bytes("static_data_get.bin")
        account = SimpleNamespace(references=refs, profile=lambda: profile)
        barrier = Barrier(2)

        def pick(body, operation_id):
            barrier.wait(timeout=5)
            return run.handle(account, source, 43, aids.PICK, body, operation_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [
                pool.submit(pick, dict(ArtifactId=10, CurseId=None), "concurrent-artifact"),
                pool.submit(pick, dict(ArtifactId=None, CurseId=801), "concurrent-curse"),
            ]
            for job in jobs:
                job.result(timeout=10)
        user = self.game.entry()
        self.assertEqual(([r["Id"] for r in user["Artifacts"]], user["Curses"]), ([10], [801]))
        self.assertFalse(
            user["Progress"]["CanPickArtifactAid"] or user["Progress"]["CanPickCurseAid"]
        )
        self.game.assert_untouched()
