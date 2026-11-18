# SPDX-License-Identifier: Apache-2.0
"""Imported challenge claims retain official baselines and advance saved counters atomically."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.challenge_progress import progress_value
from guardian_tales.items import inventory_item
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import PacketError, encode_packet
from guardian_tales.snapshots import CLIENT
from tests.test_snapshots import request


class ImportedChallengeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db, self.root)
        self.account = self.store.account
        self.account.complete_prologue(
            "Synthetic",
            {
                "IsMale": True,
                "VoiceType": 0,
                "Weapon1ItemId": 101,
                "Weapon2ItemId": 102,
                "BobLindaQuestGrade": 0,
            },
        )
        self.db.execute(
            "INSERT INTO imported_account VALUES(1,?,?,?,?)", ("0" * 64, "synthetic", "{}", "{}")
        )
        self.profile = self.account.profile()
        self.profile["UserRecord"].update(SummonCharacterCount=27, LoginDayCount=4)
        self.profile["UserMission"]["ChallengeClaimed"] = {"206": 1, "209": 1}
        self.save()
        self.catalog = {
            "client": dict(CLIENT),
            "groups": {
                "206": {
                    "condition": "SummonCharacter",
                    "steps": [
                        self.step(10, 70003, 50),
                        self.step(20, 70004, 7),
                        self.step(30, 110014, 3, "stackable"),
                    ],
                },
                "209": {
                    "condition": "Attendance",
                    "steps": [
                        self.step(1, 70003, 99),
                        self.step(3, 70003, 5),
                        self.step(5, 70003, 9),
                    ],
                },
            },
        }
        self.path = self.root / "imported_challenge_mission_catalog.json"
        self.write_catalog()

    def step(self, threshold, item, amount, storage="asset"):
        return {
            "threshold": threshold,
            "rewards": [{"item_id": item, "amount": amount, "storage": storage}],
        }

    def write_catalog(self):
        self.path.write_text(json.dumps(self.catalog))

    def save(self):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(self.profile),))
        self.db.commit()

    def claim(self, ids=(206,), key="first", all_steps=True):
        return self.account.claim_challenge_missions({"missionIds": list(ids)}, key, all_steps)

    def asset(self, profile, ident):
        return next(a for a in profile["User"]["Assets"] if a["Id"] == ident)

    def reject_unchanged(self, function):
        before = list(self.db.iterdump())
        with self.assertRaises((ValueError, PacketError)):
            function()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_old_claimed_steps_are_baselines_not_paid_again_and_batch_is_deduplicated(self):
        expected = copy.deepcopy(self.profile)
        self.asset(expected, 70004)["Amount"] += 7
        self.asset(expected, 70003)["Amount"] += 5
        expected["User"]["Cas"] += 1
        expected["UserMission"]["Cas"] += 1
        expected["UserMission"]["ChallengeClaimed"] = {"206": 2, "209": 2}
        result = self.claim((206, 209, 206))
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            result,
            {
                "User": expected["User"],
                "UserMission": expected["UserMission"],
                "AddedItems": [
                    {"Id": 0, "ItemId": 70004, "Amount": 7},
                    {"Id": 0, "ItemId": 70003, "Amount": 5},
                ],
            },
        )
        self.assertEqual(
            self.db.execute(
                "SELECT * FROM imported_challenge_baselines ORDER BY group_id"
            ).fetchall(),
            [(206, 1), (209, 1)],
        )
        self.assertEqual(
            self.db.execute(
                "SELECT group_id,step FROM challenge_mission_claims ORDER BY group_id,step"
            ).fetchall(),
            [(206, 2), (209, 2)],
        )

    def test_new_counter_growth_earns_new_steps_but_stale_receipt_returns_current_state(self):
        first = self.claim()
        self.profile = self.account.profile()
        self.profile["UserRecord"]["SummonCharacterCount"] = 35
        self.asset(self.profile, 70004)["Amount"] -= 1
        self.save()
        second = self.claim(key="new-counter")
        self.assertEqual(second["UserMission"]["ChallengeClaimed"]["206"], 3)
        item = next(i for i in second["User"]["ItemStackables"] if i["ItemId"] == 110014)
        self.assertEqual(item["Amount"], 3)
        self.assertEqual(second["AddedItems"], [{"Id": item["Id"], "ItemId": 110014, "Amount": 3}])
        current = self.account.profile()
        self.path.unlink()
        writes = self.db.total_changes
        retry = self.claim()
        self.assertEqual(retry["AddedItems"], first["AddedItems"])
        self.assertEqual(retry["User"], current["User"])
        self.assertEqual(self.db.total_changes, writes)
        self.assertEqual(self.claim(key="new-counter"), second)

    def test_next_step_and_all_remaining_steps_are_separate_identities(self):
        self.profile["UserRecord"]["SummonCharacterCount"] = 100
        self.save()
        self.claim(all_steps=False)
        self.assertEqual(self.account.profile()["UserMission"]["ChallengeClaimed"]["206"], 2)
        self.reject_unchanged(lambda: self.claim(all_steps=True))
        self.claim(key="all", all_steps=True)
        self.assertEqual(self.account.profile()["UserMission"]["ChallengeClaimed"]["206"], 3)

    def test_reopen_and_reconnect_preserve_baselines_and_receipts(self):
        session = BootstrapSession(self.store)
        signin = {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False}
        session.handle(request("/auth/sign-in", signin))
        packet = request("/mission/claim-challenge-all-step", {"missionIds": [206]})
        result = read_json_body(parse_packet(encode_packet(session.handle(packet))))
        reopened = BootstrapSession(GuestStore(self.db, self.root))
        reopened.handle(request("/auth/sign-in", {**signin, "Reconnect": True}))
        before = list(self.db.iterdump())
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(reopened.handle(packet)))), result
        )
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(
            self.db.execute(
                "SELECT step FROM imported_challenge_baselines WHERE group_id=206"
            ).fetchone(),
            (1,),
        )

    def test_unknown_or_unearned_group_rejects_batch_without_recording_a_baseline(self):
        self.reject_unchanged(lambda: self.claim((206, 999)))
        self.profile["UserMission"]["ChallengeClaimed"].pop("209")
        self.profile["UserRecord"]["LoginDayCount"] = 0
        self.save()
        self.reject_unchanged(lambda: self.claim((206, 209)))
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM imported_challenge_baselines").fetchone(), (0,)
        )

    def test_missing_baseline_or_local_step_cannot_rebase_and_repeat_rewards(self):
        self.claim()
        with self.db:
            self.db.execute("DELETE FROM imported_challenge_baselines")
        self.reject_unchanged(lambda: self.claim(key="missing-baseline"))
        with self.db:
            self.db.execute("INSERT INTO imported_challenge_baselines VALUES(206,1)")
            self.db.execute("DELETE FROM challenge_mission_claims")
        self.reject_unchanged(lambda: self.claim(key="missing-step"))
        self.profile = self.account.profile()
        self.profile["UserMission"]["ChallengeClaimed"]["206"] = 0
        self.save()
        self.reject_unchanged(lambda: self.claim(key="below-baseline"))

    def test_matching_catalog_and_exact_authenticated_request_are_required(self):
        session = BootstrapSession(self.store)
        self.reject_unchanged(
            lambda: session.handle(
                request("/mission/claim-challenge-all-step", {"missionIds": [206]})
            )
        )
        original = copy.deepcopy(self.catalog)
        for value in (
            {},
            {"client": {}, "groups": original["groups"]},
            {"client": CLIENT, "groups": {"206": {"condition": [], "steps": []}}},
        ):
            self.catalog = value
            self.write_catalog()
            self.reject_unchanged(self.claim)
        self.catalog = original
        self.write_catalog()
        for body in (
            {},
            {"missionIds": []},
            {"missionIds": [True]},
            {"missionIds": [206], "anything": 1},
        ):
            self.reject_unchanged(lambda: self.account.claim_challenge_missions(body, "bad", True))
        self.path.unlink()
        self.reject_unchanged(self.claim)

    def test_all_verified_progress_sources_read_saved_native_fields(self):
        p = copy.deepcopy(self.profile)
        p["UserRecord"].update(
            SummonCharacterCount=17,
            SummonWeaponCount=18,
            LoginDayCount=19,
            EvolveCharacterCount=20,
            LimitBreakCharacterCount=21,
            LimitBreakWeaponCount=999,
            CraftMerchCount=22,
        )
        p["UserRecord"]["Misc"] = {
            "BlessCharacterCount": 23,
            "EngraveWeaponCount": 24,
            "MythCharacterCount": 25,
            "DecomposeJewelCount": 26,
            "ComplaintClear": 27,
        }
        p["UserProgress"]["TowerInfinity"]["Floor"] = 28
        self.asset(p, 70001).update(Amount=10, Spent=30)
        self.asset(p, 70006)["Spent"] = 29
        self.asset(p, 70032)["Spent"] = 31
        for condition, value in {
            "SummonCharacter": 17,
            "SummonEquip": 18,
            "Attendance": 19,
            "EvolveCharacters": 20,
            "LimitBreak": 21,
            "CraftMerch": 22,
            "BlessCharacters": 23,
            "EngraveWeapons": 24,
            "MythCharacters": 25,
            "DecomposeJewel": 26,
            "LobbyComplaintClear": 27,
            "TowerInfinityClear": 28,
            "CollectGold": 40,
            "UseStamina": 60,
            "CollectHero": 1,
        }.items():
            with self.subTest(condition=condition):
                self.assertEqual(progress_value(p, condition), value)
        self.asset(p, 70001)["Spent"] = 0x7FFFFFFFFFFFFFFF
        self.assertEqual(progress_value(p, "CollectGold"), 0x7FFFFFFF)
        self.asset(p, 70006)["Spent"] = 0x7FFFFFFF
        with self.assertRaises(ValueError):
            progress_value(p, "UseStamina")
        p["UserRecord"]["SummonCharacterCount"] = True
        with self.assertRaises(ValueError):
            progress_value(p, "SummonCharacter")

    def test_stackable_and_unique_cosmetic_rewards_allocate_distinct_owned_rows(self):
        self.catalog["groups"]["108"] = {
            "condition": "TowerInfinityClear",
            "steps": [self.step(1, 110014, 2, "stackable"), self.step(2, 130004, 1, "misc")],
        }
        self.write_catalog()
        self.profile["UserProgress"]["TowerInfinity"]["Floor"] = 2
        self.save()
        original_counter = self.profile["User"]["ItemIdCounter"]
        result = self.claim((108,))
        self.assertEqual(
            result["AddedItems"],
            [
                {"Id": original_counter + 1, "ItemId": 110014, "Amount": 2},
                {"Id": original_counter + 2, "ItemId": 130004, "Amount": 1},
            ],
        )
        self.assertEqual(result["User"]["ItemIdCounter"], original_counter + 2)
        self.assertEqual(
            result["User"]["ItemMiscs"][-1], inventory_item(original_counter + 2, 130004)
        )
        self.assertEqual(self.claim((108,)), result)

    def test_overflow_ambiguous_stacks_duplicate_cosmetic_and_revision_guards_are_atomic(self):
        self.profile["UserRecord"]["SummonCharacterCount"] = 35
        for mode in ("asset", "stack", "ambiguous", "counter", "revision", "owner", "cosmetic"):
            p = copy.deepcopy(self.profile)
            if mode == "asset":
                self.asset(p, 70004)["Amount"] = 0x7FFFFFFF
            if mode == "stack":
                p["User"]["ItemStackables"] = [dict(inventory_item(3, 110014), Amount=0x7FFFFFFF)]
            if mode == "ambiguous":
                p["User"]["ItemStackables"] = [inventory_item(3, 110014), inventory_item(4, 110014)]
            if mode == "counter":
                p["User"]["ItemIdCounter"] = 0x7FFFFFFF
            if mode == "revision":
                p["UserMission"]["Cas"] = 0x7FFFFFFFFFFFFFFF
            if mode == "owner":
                p["UserMission"]["UserId"] = 999
            if mode == "cosmetic":
                self.catalog["groups"]["206"]["steps"][2] = self.step(30, 130004, 1, "misc")
                self.write_catalog()
                p["User"]["ItemMiscs"] = [inventory_item(3, 130004)]
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
            self.db.commit()
            with self.subTest(mode=mode):
                self.reject_unchanged(self.claim)

    def test_receipt_failure_rolls_back_rewards_markers_and_new_baselines(self):
        self.db.execute(
            "CREATE TRIGGER fail_challenge BEFORE INSERT ON challenge_mission_requests BEGIN SELECT RAISE(ABORT,'synthetic'); END"
        )
        self.db.commit()
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.claim((206, 209))
        self.assertEqual(list(self.db.iterdump()), before)

    def test_fully_claimed_imported_group_stays_completed_without_rewards(self):
        self.profile["UserMission"]["ChallengeClaimed"]["206"] = 3
        self.save()
        result = self.claim()
        self.assertEqual(result["AddedItems"], [])
        self.assertEqual(self.account.profile(), self.profile)
        self.assertEqual(
            self.db.execute(
                "SELECT step FROM imported_challenge_baselines WHERE group_id=206"
            ).fetchone(),
            (3,),
        )
