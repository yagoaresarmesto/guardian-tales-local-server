# SPDX-License-Identifier: Apache-2.0
"""Synthetic challenge groups preserve legacy claims and freeze batch retries."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.characters import new_character
from guardian_tales.packet_reader import PacketError, parse_packet
from guardian_tales.protocol import Packet, encode_packet

FIXTURE = Path(__file__).parent / "fixtures/challenge_mission_catalog.json"


class ChallengeBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.references = Path(self.tmp.name)
        self.catalog_file = self.references / "challenge_mission_catalog.json"
        self.db_file = self.references / "test-account.sqlite3"
        self.db = sqlite3.connect(self.db_file)
        self.store = GuestStore(self.db, self.references)
        self.account = self.store.account
        self.account.complete_prologue(
            "lab",
            {
                "IsMale": True,
                "VoiceType": 1,
                "Weapon1ItemId": 9010010,
                "Weapon2ItemId": 9080010,
                "BobLindaQuestGrade": 0,
            },
        )
        # Create the existing first-step receipt through the old fallback.
        self.account.claim_challenge_missions({"missionIds": [200]})
        p = self.account.profile()
        p["User"]["Characters"].extend(new_character(i, 100 + i) for i in range(2, 5))
        p["User"]["CharacterIdCounter"] = 4
        p["UserRecord"]["SummonCharacterCount"] = 6
        self.asset(p, 70003)["Amount"] = 500
        self.asset(p, 70004)["Amount"] = 100
        self.save(p)
        self.catalog_file.write_bytes(FIXTURE.read_bytes())

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def asset(self, profile, item_id):
        return next(a for a in profile["User"]["Assets"] if a["Id"] == item_id)

    def save(self, p):
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(p),))
        self.db.commit()

    def claim(self, ids=None, operation="claim-1", all_steps=True):
        return self.account.claim_challenge_missions(
            {"missionIds": [200, 901] if ids is None else ids}, operation, all_steps
        )

    def assert_unchanged(self, p, steps=1, batches=0):
        self.assertEqual(self.account.profile(), p)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM challenge_mission_claims").fetchone(), (steps,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM challenge_mission_requests").fetchone(),
            (batches,),
        )

    def packet(self, route, body, seq=12):
        return parse_packet(
            encode_packet(
                Packet(
                    0,
                    json.dumps(body).encode(),
                    body_type=1,
                    api=route,
                    sequence_id=seq,
                )
            )
        )

    def test_all_steps_batch_preserves_legacy_claim_and_other_profile_state(self):
        expected = self.account.profile()
        self.asset(expected, 70003)["Amount"] += 18
        self.asset(expected, 70004)["Amount"] += 30
        expected["User"]["Cas"] += 1
        expected["UserMission"]["Cas"] += 1
        expected["UserMission"]["ChallengeClaimed"] = {"200": 3, "901": 2}
        response = self.claim([200, 901, 200])
        self.assertEqual(self.account.profile(), expected)
        self.assertEqual(
            response,
            {
                "User": expected["User"],
                "UserMission": expected["UserMission"],
                "AddedItems": [
                    {"Id": 0, "ItemId": 70003, "Amount": 7},
                    {"Id": 0, "ItemId": 70003, "Amount": 11},
                    {"Id": 0, "ItemId": 70004, "Amount": 13},
                    {"Id": 0, "ItemId": 70004, "Amount": 17},
                ],
            },
        )
        self.assertEqual(
            json.loads(
                self.db.execute(
                    "SELECT rewards FROM challenge_mission_claims WHERE group_id=200 AND step=1"
                ).fetchone()[0]
            ),
            [{"Id": 0, "ItemId": 70003, "Amount": 50}],
        )
        self.assert_unchanged(expected, 5, 1)

    def test_next_step_mode_advances_one_per_group_and_new_request_can_advance_again(self):
        self.claim(all_steps=False)
        first = self.account.profile()
        self.assertEqual(first["UserMission"]["ChallengeClaimed"], {"200": 2, "901": 1})
        self.assertEqual(self.asset(first, 70003)["Amount"], 507)
        self.assertEqual(self.asset(first, 70004)["Amount"], 113)
        self.claim(all_steps=False)
        self.assert_unchanged(first, 3, 1)
        self.claim(operation="next", all_steps=False)
        self.assertEqual(
            self.account.profile()["UserMission"]["ChallengeClaimed"], {"200": 3, "901": 2}
        )

    def test_persisted_retry_returns_frozen_notices_and_current_balances_without_catalog(self):
        original = self.claim()
        p = self.account.profile()
        self.asset(p, 70003)["Amount"] -= 5
        self.asset(p, 70004)["Amount"] -= 8
        self.save(p)
        self.db.close()
        self.db = sqlite3.connect(self.db_file)
        self.account = GuestStore(self.db, self.references).account
        self.catalog_file.unlink()
        retry = self.claim([901, 200, 901])
        self.assertEqual(retry["AddedItems"], original["AddedItems"])
        self.assertEqual(retry["User"], p["User"])
        self.assert_unchanged(p, 5, 1)

    def test_incomplete_unknown_or_malformed_group_rejects_entire_batch(self):
        p = self.account.profile()
        p["UserRecord"]["SummonCharacterCount"] = 1
        self.save(p)
        for ids in ([200, 901], [200, 999], [True], [], None, [[200]], [200] * 513):
            request = {"missionIds": ids}
            with self.subTest(ids=str(ids)[:40]), self.assertRaises(ValueError):
                self.account.claim_challenge_missions(request, "invalid", True)
            self.assert_unchanged(p)

    def test_next_step_retry_still_uses_saved_receipt_after_catalog_removal(self):
        first = self.claim(all_steps=False)
        p = self.account.profile()
        self.catalog_file.unlink()
        self.assertEqual(self.claim(all_steps=False), first)
        self.assert_unchanged(p, 3, 1)

    def test_invalid_catalog_conditions_thresholds_or_rewards_cannot_advance_claims(self):
        original = json.loads(FIXTURE.read_text())
        invalid = [[], {}, {"groups": {}}]
        for field, value in (("condition", "unknown"), ("steps", [])):
            bad = copy.deepcopy(original)
            bad["groups"]["200"][field] = value
            invalid.append(bad)
        for field, value in (("threshold", 0), ("threshold", True), ("rewards", [])):
            bad = copy.deepcopy(original)
            bad["groups"]["200"]["steps"][1][field] = value
            invalid.append(bad)
        bad = copy.deepcopy(original)
        bad["groups"]["200"]["steps"][2]["threshold"] = 1
        invalid.append(bad)
        for field, value in (("item_id", True), ("amount", -1)):
            bad = copy.deepcopy(original)
            bad["groups"]["200"]["steps"][1]["rewards"][0][field] = value
            invalid.append(bad)
        p = self.account.profile()
        for bad in invalid:
            self.catalog_file.write_text(json.dumps(bad))
            with self.subTest(catalog=bad), self.assertRaises(ValueError):
                self.claim()
            self.assert_unchanged(p)

    def test_claim_marker_and_missing_or_extra_step_receipt_are_rejected(self):
        p = self.account.profile()
        p["UserMission"]["ChallengeClaimed"]["200"] = 2
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p)
        p["UserMission"]["ChallengeClaimed"]["200"] = 1
        self.save(p)
        self.db.execute("DELETE FROM challenge_mission_claims WHERE group_id=200")
        self.db.commit()
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p, 0)

    def test_late_reward_overflow_or_missing_asset_cannot_save_earlier_steps(self):
        p = self.account.profile()
        self.asset(p, 70004)["Amount"] = 0x7FFFFFFF
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p)
        p["User"]["Assets"] = [a for a in p["User"]["Assets"] if a["Id"] != 70004]
        self.save(p)
        with self.assertRaises(ValueError):
            self.claim()
        self.assert_unchanged(p)

    def test_late_step_batch_receipt_or_profile_failure_rolls_back_the_whole_batch(self):
        p = self.account.profile()
        for table, action, condition in (
            ("challenge_mission_claims", "INSERT", "WHEN NEW.group_id=901"),
            ("challenge_mission_requests", "INSERT", ""),
            ("local_account", "UPDATE", ""),
        ):
            self.db.execute(
                f"CREATE TRIGGER reject_challenge BEFORE {action} ON {table} {condition} "
                "BEGIN SELECT RAISE(ABORT,'test'); END"
            )
            self.db.commit()
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.claim()
            self.assert_unchanged(p)
            self.db.execute("DROP TRIGGER reject_challenge")
            self.db.commit()

    def test_authenticated_routes_reconnect_and_fresh_login_preserve_request_identity(self):
        session = BootstrapSession(self.store)
        body = {"missionIds": [200, 901]}
        request = self.packet("/mission/claim-challenge-all", body)
        with self.assertRaises(PacketError):
            session.handle(request)
        signin = {"AuthKind": 0, "AccessToken": "synthetic-local", "Reconnect": False}
        session.handle(self.packet("/auth/sign-in", signin, 1))
        first = read_json_body(parse_packet(encode_packet(session.handle(request))))
        p = self.account.profile()
        reconnect = BootstrapSession(self.store)
        reconnect.handle(self.packet("/auth/sign-in", {**signin, "Reconnect": True}, 13))
        self.assertEqual(
            read_json_body(parse_packet(encode_packet(reconnect.handle(request)))), first
        )
        self.assert_unchanged(p, 3, 1)
        reconnect.handle(self.packet("/auth/sign-in", signin, 1))
        all_step = self.packet("/mission/claim-challenge-all-step", body)
        reconnect.handle(all_step)
        p = self.account.profile()
        self.assertEqual(p["UserMission"]["ChallengeClaimed"], {"200": 3, "901": 2})
        self.assert_unchanged(p, 5, 2)

    def test_same_operation_cannot_change_claim_mode_groups_or_use_missing_identity(self):
        self.claim(all_steps=False)
        p = self.account.profile()
        for ids, mode, operation in (
            ([200], False, "claim-1"),
            ([200, 901], True, "claim-1"),
            ([200], True, None),
            ([200], True, ""),
        ):
            with self.assertRaises(ValueError):
                self.claim(ids, operation, mode)
            self.assert_unchanged(p, 3, 1)

    def test_already_claimed_groups_in_new_batch_do_not_restore_spent_rewards(self):
        self.claim()
        p = self.account.profile()
        self.asset(p, 70003)["Amount"] = 1
        self.save(p)
        result = self.claim(operation="no-new-levels")
        self.assertEqual(result["AddedItems"], [])
        self.assert_unchanged(p, 5, 2)

    def test_unfinished_prologue_cannot_use_all_step_route(self):
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db, self.references).account
            before = account.profile()
            with self.assertRaises(ValueError):
                account.claim_challenge_missions({"missionIds": [200]}, "too-early", True)
            self.assertEqual(account.profile(), before)
