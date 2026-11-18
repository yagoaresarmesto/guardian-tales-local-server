# SPDX-License-Identifier: Apache-2.0
"""Synthetic account imports preserve identity/state and reject unsafe overwrites."""

import copy
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession, GuestStore
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.snapshots import CLIENT, FORMAT, import_snapshot, load_snapshot
from guardian_tales.state_lock import StateLock


def synthetic_snapshot():
    with closing(sqlite3.connect(":memory:")) as db:
        account = AccountStore(db)
        account.complete_prologue(
            "Synthetic",
            {
                "IsMale": True,
                "VoiceType": 0,
                "Weapon1ItemId": 101,
                "Weapon2ItemId": 102,
                "BobLindaQuestGrade": 0,
            },
        )
        profile = account.profile()
    profile["User"]["Id"] = 9400
    profile["User"]["Assets"][0]["Spent"] = -1
    for section in profile.values():
        if isinstance(section, dict) and "UserId" in section:
            section["UserId"] = 9400
    reads = {
        "/collection/list-all": {
            "ItemCollections": {"101": 1},
            "CustomCollections": [],
            "ItemMastery": {},
            "NewItems": [101],
            "NewCustomCollections": [],
            "NewItemMastery": [],
        },
        "/pasture/collection-all": {"PastureMonsterCollections": {"1": 2}},
        "/lobby-village/enter": {"User": {}, "UserLobbyVillage": {"Level": 4}},
        "/preset/get-presets": {"UserPartyPreset2": {"SavedPreset": {"Characters": [1]}}},
    }
    return {
        "format": FORMAT,
        "format_version": 1,
        "client": dict(CLIENT),
        "profile": profile,
        "startup_reads": {
            route: {"body_type": 1, "value": value} for route, value in reads.items()
        },
        "stage_progresses": {"1000101": "AgAAAA==", "1000102": None},
    }


def request(route, value=None):
    return parse_packet(
        encode_packet(
            Packet(
                0,
                json.dumps(value).encode(),
                body_type=1,
                api=route,
                sequence_id=12,
            )
        )
    )


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        self.source = self.root / "synthetic.json"
        self.snapshot = synthetic_snapshot()
        self.write_source()
        self.state = self.root / "state"

    def tearDown(self):
        self.temporary.cleanup()

    def write_source(self, value=None):
        self.source.write_text(
            json.dumps(self.snapshot if value is None else value), encoding="utf-8"
        )

    def test_import_preserves_profile_identity_reads_and_restart(self):
        original_source = self.source.read_bytes()
        result = import_snapshot(self.source, self.state)
        self.assertTrue(result["imported"])
        self.assertTrue(result["network_mutations_enabled"])
        self.assertEqual(
            result["enabled_mutation_routes"],
            [
                "/collection/claim-hero-knowledge-all",
                "/item/apply-options",
                "/item/apply-relic-options",
                "/item/change-lock-options",
                "/item/change-options",
                "/item/change-relic-options/v2",
                "/item/engrave-weapon",
                "/item/enhance-weapon",
                "/item/limitbreak-weapon/v2",
                "/lobby-village/harvest-all",
                "/lobby-village/harvest-basecamp",
                "/lobby-village/receive-gift",
                "/lobby-village/remove-obstacle",
                "/mission/claim-challenge-all",
                "/mission/claim-challenge-all-step",
                "/preset/delete-preset",
                "/preset/set-presets",
                "/preset/set-selected-preset",
                "/summon/select-character",
                "/summon/set-select-character",
                "/tower-infinity/end-stage",
                "/user/add-character-experience",
                "/user/charge-stamina",
                "/user/charge-stamina-by-gem",
                "/user/claim-daily-attendance",
                "/user/guardian-mastery-level-up",
                "/user/reset-guardian-mastery-level",
            ],
        )
        self.assertEqual(result["source_sha256"], hashlib.sha256(original_source).hexdigest())
        self.assertEqual(self.source.read_bytes(), original_source)
        for _ in range(2):
            with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
                store = GuestStore(db)
                session = BootstrapSession(store)
                with self.assertRaises(PacketError):
                    session.handle(request("/preset/get-presets"))
                sign_in = json.loads(
                    session.handle(
                        request(
                            "/auth/sign-in",
                            {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False},
                        )
                    ).body
                )
                self.assertEqual(sign_in["UserId"], 9400)
                self.assertFalse(sign_in["NeedPrologue"])
                self.assertEqual(
                    json.loads(session.handle(request("/auth/fetch-account")).body),
                    self.snapshot["profile"],
                )
                for route, expected in self.snapshot["startup_reads"].items():
                    changes = db.total_changes
                    response = session.handle(request(route))
                    self.assertEqual(response.body_type, 1)
                    self.assertEqual(json.loads(response.body), expected["value"])
                    self.assertEqual(db.total_changes, changes)
                new_items = json.loads(session.handle(request("/collection/list-new")).body)
                self.assertEqual(new_items["NewItems"], [101])
                self.assertEqual(store.account.profile(), self.snapshot["profile"])
                preserved_progress = db.execute(
                    "SELECT stage_progresses FROM imported_account WHERE id=1"
                ).fetchone()[0]
                self.assertEqual(json.loads(preserved_progress), self.snapshot["stage_progresses"])

    def test_network_mutations_and_repeated_prologue_reject_without_state_changes(self):
        import_snapshot(self.source, self.state)
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            store = GuestStore(db)
            session = BootstrapSession(store)
            session.signed_in = True
            before = db.total_changes
            for route, body in (
                ("/user/charge-stamina-by-gem", {"Count": 1}),
                ("/user/add-character-experience", {}),
                ("/mission/claim-beginner-all", {}),
                ("/user/mark-tutorial", {}),
            ):
                with self.subTest(route=route), self.assertRaises(PacketError):
                    session.handle(request(route, body))
            with self.assertRaises(ValueError):
                store.account.complete_prologue("Changed", {})
            with self.assertRaises(PacketError):
                session.handle(request("/preset/get-presets", {"Unexpected": True}))
            self.assertEqual(db.total_changes, before)
            self.assertEqual(store.account.profile(), self.snapshot["profile"])

    def test_catalog_startup_does_not_unlock_or_change_an_imported_profile(self):
        import_snapshot(self.source, self.state)
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            with patch("guardian_tales.account.load_story_catalog", return_value={"synthetic": {}}):
                with patch(
                    "guardian_tales.account.open_eligible_stages",
                    side_effect=AssertionError("unexpected progress mutation"),
                ):
                    store = GuestStore(db)
            self.assertEqual(store.account.profile(), self.snapshot["profile"])

    def test_village_cache_hints_return_preserved_state_without_mutation(self):
        import_snapshot(self.source, self.state)
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            session = BootstrapSession(GuestStore(db))
            session.signed_in = True
            before = db.total_changes
            expected = self.snapshot["startup_reads"]["/lobby-village/enter"]["value"]
            for partial in (False, True):
                for timestamp in ("2026-01-01T00:00:00.1234567+00:00", "0001-01-01T00:00:00Z"):
                    response = session.handle(
                        request(
                            "/lobby-village/enter",
                            {
                                "isPartial": partial,
                                "lastLobbyShopUpdated": timestamp,
                            },
                        )
                    )
                    self.assertEqual(json.loads(response.body), expected)
            self.assertEqual(db.total_changes, before)
            self.assertEqual(session.store.account.profile(), self.snapshot["profile"])

    def test_invalid_village_cache_hints_reject_without_changes(self):
        import_snapshot(self.source, self.state)
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            session = BootstrapSession(GuestStore(db))
            session.signed_in = True
            before = db.total_changes
            valid = {"isPartial": False, "lastLobbyShopUpdated": "2026-01-01T00:00:00Z"}
            for body in (
                {**valid, "isPartial": 0},
                {**valid, "lastLobbyShopUpdated": None},
                {**valid, "lastLobbyShopUpdated": "2026-99-99T00:00:00Z"},
                {**valid, "lastLobbyShopUpdated": "2026-01-01T00:00:00"},
                {**valid, "lastLobbyShopUpdated": "synthetic-private-value"},
                {**valid, "Extra": True},
                {"isPartial": False},
            ):
                with self.subTest(body=body), self.assertRaises(PacketError) as error:
                    session.handle(request("/lobby-village/enter", body))
                self.assertNotIn("synthetic-private-value", str(error.exception))
            self.assertEqual(db.total_changes, before)
            self.assertEqual(session.store.account.profile(), self.snapshot["profile"])

    def test_imported_event_coupon_check_preserves_counters_and_inventory(self):
        self.snapshot["profile"]["UserShop"]["SummonPickUpTickets"] = {"12": 7, "17": 0}
        self.snapshot["profile"]["UserShop"]["CollaborationPickUpTickets"] = {"21": 3}
        self.snapshot["profile"]["User"]["ItemStackables"] = [
            {"Id": 3, "ItemId": 110007, "Amount": 20},
            {"Id": 4, "ItemId": 110015, "Amount": 4},
        ]
        self.snapshot["profile"]["User"]["ItemIdCounter"] = 4
        self.write_source()
        import_snapshot(self.source, self.state)
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            session = BootstrapSession(GuestStore(db))
            session.signed_in = True
            before = db.total_changes
            for body in (None, {}, None):
                value = json.loads(
                    session.handle(request("/user/exchange-summon-pickup-ticket", body)).body
                )
                self.assertEqual(
                    value,
                    {
                        "UserShop": self.snapshot["profile"]["UserShop"],
                        "ExchangeSummonPickUpTickets": {},
                        "ExchangeCollaborationPickUpTickets": {},
                    },
                )
            self.assertEqual(db.total_changes, before)
            self.assertEqual(session.store.account.profile(), self.snapshot["profile"])

    def test_imported_coupon_check_returns_current_shop_after_reopen(self):
        self.snapshot["profile"]["UserShop"]["SummonPickUpTickets"] = {"12": 7}
        self.write_source()
        import_snapshot(self.source, self.state)
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            account = GuestStore(db).account
            account.read("/user/exchange-summon-pickup-ticket")
            current = account.profile()
            current["UserShop"]["SelectedSummonCharacters"] = [101, 102, 103, 104, 105]
            current["UserShop"]["Cas"] += 1
            with db:
                db.execute("UPDATE local_account SET profile=? WHERE id=1", (json.dumps(current),))
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            account = GuestStore(db).account
            before = db.total_changes
            result = account.read("/user/exchange-summon-pickup-ticket")
            self.assertEqual(result["UserShop"], current["UserShop"])
            self.assertEqual(account.profile(), current)
            self.assertEqual(db.total_changes, before)

    def test_imported_coupon_check_rejects_malformed_counts_without_mutation(self):
        import_snapshot(self.source, self.state)
        with closing(sqlite3.connect(self.state / "server.sqlite3")) as db:
            session = BootstrapSession(GuestStore(db))
            session.signed_in = True
            for values in ([1], {"12": True}, {"12": -1}, {"12": "7"}, {"bad": 7}, {"12": 1 << 63}):
                profile = copy.deepcopy(self.snapshot["profile"])
                profile["UserShop"]["SummonPickUpTickets"] = values
                with db:
                    db.execute(
                        "UPDATE local_account SET profile=? WHERE id=1", (json.dumps(profile),)
                    )
                before = db.total_changes
                with self.subTest(values=values), self.assertRaises(PacketError):
                    session.handle(request("/user/exchange-summon-pickup-ticket"))
                self.assertEqual(db.total_changes, before)
                self.assertEqual(session.store.account.profile(), profile)
            with self.assertRaises(PacketError):
                session.handle(request("/user/exchange-summon-pickup-ticket", {"Unexpected": True}))

    def test_existing_state_and_repeat_import_are_never_overwritten(self):
        import_snapshot(self.source, self.state)
        original = (self.state / "server.sqlite3").read_bytes()
        changed = copy.deepcopy(self.snapshot)
        changed["profile"]["User"]["Name"] = "Different"
        for value in (self.snapshot, changed):
            self.write_source(value)
            with self.assertRaisesRegex(ValueError, "empty state directory"):
                import_snapshot(self.source, self.state)
            self.assertEqual((self.state / "server.sqlite3").read_bytes(), original)
        self.assertEqual({p.name for p in self.state.iterdir()}, {"server.sqlite3", ".state.lock"})

    def test_invalid_inputs_do_not_create_the_state_directory(self):
        cases = []

        def invalid(edit):
            value = copy.deepcopy(self.snapshot)
            edit(value)
            cases.append(value)

        invalid(lambda v: v["profile"].pop("UserShop"))
        invalid(lambda v: v["client"].update(version="unsupported"))
        invalid(lambda v: v.update(format_version=True))
        invalid(lambda v: v["profile"]["UserRecord"].update(UserId=9401))
        invalid(
            lambda v: v["profile"]["User"]["Characters"].append(
                copy.deepcopy(v["profile"]["User"]["Characters"][0])
            )
        )
        invalid(lambda v: v["profile"]["User"]["Characters"][0].update(Weapon1=99999))
        invalid(lambda v: v["profile"]["User"]["Party"].update(Characters=[True]))
        invalid(lambda v: v["profile"]["User"].update(ItemIdCounter=0))
        invalid(lambda v: v["profile"]["User"]["Assets"][0].update(Amount=True))
        invalid(lambda v: v["profile"]["User"]["Assets"][0].update(Spent=False))
        invalid(lambda v: v["profile"]["User"]["Characters"][0].update(CharacterId=False))
        invalid(lambda v: v["profile"]["User"].update(AccessToken="synthetic-secret"))
        invalid(lambda v: v["startup_reads"].pop("/preset/get-presets"))
        invalid(
            lambda v: v["startup_reads"]["/lobby-village/enter"]["value"].update(
                User={"Name": "stale"}
            )
        )
        invalid(lambda v: v["stage_progresses"].update({"1000101": "not base64!"}))
        invalid(lambda v: v["stage_progresses"].update({"1000101": 3}))
        for index, value in enumerate(cases):
            self.write_source(value)
            with self.subTest(index=index), self.assertRaises(ValueError) as result:
                import_snapshot(self.source, self.state)
            self.assertNotIn("synthetic-secret", str(result.exception))
            self.assertFalse(self.state.exists())

    def test_json_duplicate_keys_and_nonfinite_values_are_rejected(self):
        for raw in ('{"format":"first","format":"second"}', '{"value":NaN}', '{"value":1e400}'):
            self.source.write_text(raw, encoding="utf-8")
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                load_snapshot(self.source)

    def test_in_use_directory_is_not_modified(self):
        self.state.mkdir()
        with StateLock(self.state):
            with self.assertRaises(RuntimeError):
                import_snapshot(self.source, self.state)
        self.assertFalse((self.state / "server.sqlite3").exists())

    def test_failed_publication_does_not_leave_a_partial_account(self):
        with patch(
            "guardian_tales.snapshots.os.link", side_effect=OSError("synthetic publication failure")
        ):
            with self.assertRaises(OSError):
                import_snapshot(self.source, self.state)
        self.assertEqual({p.name for p in self.state.iterdir()}, {".state.lock"})
        self.assertEqual(load_snapshot(self.source)[0], self.snapshot)


if __name__ == "__main__":
    unittest.main()
