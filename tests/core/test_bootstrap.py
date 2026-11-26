# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
import sqlite3
import time
import unittest
from datetime import datetime, timedelta, timezone

from guardian_tales.account import AccountStore
from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.lobby import LOBBY_ROUTES, READ_RESPONSES
from guardian_tales.packet_reader import lz4_block, parse_packet
from guardian_tales.platform import dispatch
from guardian_tales.protocol import Packet, PacketError, encode_packet
from tests import FIXTURES

REFERENCE_DIR = FIXTURES / "reference"


def request(value, route="/auth/sign-in"):
    return parse_packet(
        encode_packet(Packet(0, json.dumps(value).encode(), body_type=1, api=route, sequence_id=17))
    )


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.session = BootstrapSession(GuestStore(self.db, REFERENCE_DIR))

    def tearDown(self):
        self.db.close()

    def test_sign_in_matches_observed_response_shape(self):
        response = self.session.handle(
            request({"AuthKind": 0, "AccessToken": "test-only", "Reconnect": False})
        )
        value = json.loads(response.body)
        fixture = json.loads((FIXTURES / "sign_in_schema.json").read_text())
        types = {"null": type(None), "string": str, "integer": int, "boolean": bool}
        self.assertEqual(set(value), set(fixture))
        for k, kind in fixture.items():
            self.assertIs(type(value[k]), types[kind], k)
        self.assertEqual(response.sequence_id, 17)
        self.assertEqual(response.api, "")

    def test_invalid_credentials_shape_does_not_create_a_session(self):
        for body in [
            [],
            None,
            {},
            {"AuthKind": False, "AccessToken": "x", "Reconnect": False},
            {"AuthKind": 0, "AccessToken": 3, "Reconnect": False},
            {"AuthKind": 0, "AccessToken": "x", "Reconnect": "false"},
        ]:
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.session.handle(request(body))
        self.assertFalse(self.session.signed_in)
        self.assertEqual(self.db.execute("SELECT sign_in_count FROM guest").fetchone()[0], 0)

    def test_corrupt_json_does_not_update_guest(self):
        packet = Packet(0, b"{bad", body_type=1, api="/auth/sign-in", sequence_id=5)
        with self.assertRaises(PacketError):
            self.session.handle(parse_packet(encode_packet(packet)))
        self.assertEqual(self.db.execute("SELECT sign_in_count FROM guest").fetchone()[0], 0)

    def test_unknown_route_is_not_acknowledged_as_success(self):
        with self.assertRaises(PacketError):
            self.session.handle(request({}, "/battle/unimplemented"))

    def test_unpause_syncs_server_time_without_changes(self):
        route = "/auth/unpause"
        packet = parse_packet(encode_packet(Packet(0, b"", api=route, sequence_id=17)))
        with self.assertRaisesRegex(PacketError, "sign-in"):
            self.session.handle(packet)
        self.session.handle(
            request({"AuthKind": 0, "AccessToken": "test-only", "Reconnect": False})
        )
        before = self.db.total_changes
        for request_packet in (packet, request({}, route), packet):
            response = self.session.handle(request_packet)
            value = json.loads(response.body)
            self.assertEqual(set(value), {"ServerTime", "StartOfDay"})
            self.assertEqual(value["StartOfDay"], "00:00:00")
            self.assertEqual(datetime.fromisoformat(value["ServerTime"]).utcoffset(), timedelta(0))
            self.assertEqual(response.sequence_id, 17)
        with self.assertRaises(PacketError):
            self.session.handle(request({"Pause": False}, route))
        self.assertEqual(self.db.total_changes, before)

    def test_device_settings_before_sign_in_returns_static_text_without_account_writes(self):
        route = "/static-data/device-specific-settings"
        profile = self.session.store.account.profile()
        changes = self.db.total_changes
        for body in (None, {}):
            response = parse_packet(encode_packet(self.session.handle(request(body, route))))
            self.assertEqual(response["packet_type"], 1)
            self.assertEqual(response["body_type"], 2)
            self.assertEqual(response["sequence_id"], 17)
            self.assertEqual(response["api"], "")
            payload = bytes.fromhex(response["body_hex"])
            decoded = lz4_block(payload[:-4], int.from_bytes(payload[-4:], "little"))
            self.assertEqual(decoded.decode("utf-8").split(), [])
        for body in (False, [], {"Device": "test"}, ""):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.session.handle(request(body, route))
        self.assertFalse(self.session.signed_in)
        self.assertEqual(self.session.store.account.profile(), profile)
        self.assertEqual(self.db.total_changes, changes)

    def test_empty_channel_listening_is_authenticated_and_read_only(self):
        route = "/chat/listen-channel"
        body = {"Listen": True, "Since": None}
        with self.assertRaises(PacketError):
            self.session.handle(request(body, route))
        self.session.signed_in = True
        before = self.session.store.account.profile()
        changes = self.db.total_changes
        for listen in (True, False, True):
            reply = self.session.handle(request({"Listen": listen, "Since": None}, route))
            self.assertEqual(json.loads(reply.body), {"History": []})
        for invalid in (None, {}, {"Listen": 1, "Since": None}, {"Listen": True, "Since": 1}):
            with self.subTest(body=invalid), self.assertRaises(PacketError):
                self.session.handle(request(invalid, route))
        self.assertEqual(self.session.store.account.profile(), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_profile_requires_sign_in_and_contains_only_new_guest_state(self):
        with self.assertRaises(PacketError):
            self.session.handle(request(None, "/auth/fetch-account"))
        self.session.handle(
            request({"AuthKind": 0, "AccessToken": "test-only", "Reconnect": False})
        )
        value = json.loads(self.session.handle(request(None, "/auth/fetch-account")).body)
        user = value["User"]
        self.assertEqual(user["Name"], "Local")
        self.assertEqual(user["Characters"], [])
        self.assertEqual(user["Party"]["Characters"], [])
        self.assertEqual(user["ItemWeapons"], [])
        self.assertTrue(all(a["Amount"] == a["Spent"] == 0 for a in user["Assets"]))
        self.assertEqual(value["UserProgress"]["StageStates"], {})
        self.assertEqual(value["UserProgress"]["Tutorials"], [])
        self.assertIsNone(value["GuildMember"])

    def test_profile_reads_do_not_mutate_saved_state(self):
        first = self.session.store.account.profile()
        first["User"]["Name"] = "unsaved"
        self.assertEqual(self.session.store.account.profile()["User"]["Name"], "Local")
        self.assertEqual(
            self.session.store.account.read("/friend2/has-changes"),
            {"Changed": False, "Gift": False},
        )
        self.assertEqual(self.session.store.account.read("/guild/get-my-guild")["GuildMembers"], [])
        # Reading a pass must retain saved progress, including a nonempty pass;
        # returning the empty guest template here would reset the client's view.
        saved = self.session.store.account.profile()
        saved["UserGuardianPass"].update(
            SeasonId=7,
            Experience=123,
            PassType=1,
            Claimed={"Free": 2, "Gold": 1, "Platinum": 0, "ExtraExp": 0},
            Missions={"1": 3},
        )
        saved["UserFestivalPass"].update(
            SeasonId=9,
            Experience=321,
            Point=45,
            PassType=2,
            Claimed={"Free": 3, "Gold": 2, "Platinum": 1, "ExtraExp": 0},
            Missions={"2": 4},
            Purchase={"1": 2},
        )
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(saved),))
        self.db.commit()
        entries = {
            "/guardian-pass/enter": "UserGuardianPass",
            "/festival-pass/enter": "UserFestivalPass",
        }
        for route in entries:
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.session.handle(request(None, route))
        self.session.handle(
            request({"AuthKind": 0, "AccessToken": "test-only", "Reconnect": False})
        )
        for route, field in entries.items():
            with self.subTest(route=route):
                for body in (None, {}):
                    response = json.loads(self.session.handle(request(body, route)).body)
                    self.assertEqual(response, {field: saved[field]})
                with self.assertRaises(PacketError):
                    self.session.handle(request({"SeasonId": 8}, route))
                self.assertEqual(AccountStore(self.db).read(route), response)
        self.assertEqual(self.session.store.account.profile(), saved)

    def test_platform_guest_uses_local_identity_and_does_not_store_received_token(self):
        code, response = dispatch(
            "/kong/sign-in",
            {"AuthKind": "guest", "Token": "SYNTHETIC_PROVIDER_TOKEN"},
            10100,
            guest_store=self.session.store,
        )
        self.assertEqual(code, 200)
        token = response["Body"]["kongAccessToken"]
        header, payload, signature = token.split(".")
        decoded = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))
        guest_uuid = self.db.execute("SELECT uuid FROM guest").fetchone()[0]
        self.assertEqual(decoded["PlayerId"], guest_uuid)
        self.assertEqual(decoded["BindingInfo"], {})
        self.assertGreater(decoded["Exp"], int(time.time()))
        key = self.db.execute(
            "SELECT value FROM guest_secrets WHERE name='signing_key'"
        ).fetchone()[0]
        expected = (
            base64.b64encode(
                hmac.new(key, (header + "." + payload).encode(), hashlib.sha256).digest()
            )
            .decode()
            .rstrip("=")
        )
        self.assertTrue(hmac.compare_digest(signature, expected))
        again = dispatch(
            "/kong/sign-in",
            {"AuthKind": "guest", "Token": "different"},
            10100,
            guest_store=self.session.store,
        )[1]
        self.assertEqual(response["Body"]["guestToken"], again["Body"]["guestToken"])
        self.assertNotIn("SYNTHETIC_PROVIDER_TOKEN", "\n".join(self.db.iterdump()))

    def test_prologue_name_validation_does_not_change_account(self):
        self.session.handle(
            request({"AuthKind": 0, "AccessToken": "test-only", "Reconnect": False})
        )
        for value in ("", "x", "x" * 11, "ab\x00"):
            response = self.session.handle(request({"Name": value}, "/auth/check-name"))
            self.assertEqual(response.result_type, 1)
            self.assertEqual(response.error, "ERROR_USER_NAME_INVALID_LENGTH")
        self.assertEqual(
            self.session.handle(request({"Name": "lab"}, "/auth/check-name")).result_type, 0
        )
        self.assertEqual(self.session.store.account.profile()["User"]["Name"], "Local")

    def test_prologue_completion_is_persistent_idempotent_and_creates_one_knight(self):
        store = self.session.store.account
        info = {
            "IsMale": True,
            "VoiceType": 1,
            "Weapon1ItemId": 9010010,
            "Weapon2ItemId": 9080010,
            "BobLindaQuestGrade": 0,
        }
        first = store.complete_prologue("lab", info)
        again = store.complete_prologue("lab", info)
        self.assertEqual(first, again)
        self.assertFalse(AccountStore(self.db, REFERENCE_DIR).needs_prologue())
        self.assertFalse(self.session.store.sign_in()["NeedPrologue"])
        self.assertEqual(first["User"]["Party"]["Characters"], [1])
        self.assertEqual(len(first["User"]["Characters"]), 1)
        self.assertEqual([w["Id"] for w in first["User"]["ItemWeapons"]], [1, 2])
        self.assertEqual(first["User"]["Characters"][0]["Weapon1"], 1)
        with self.assertRaises(ValueError):
            store.complete_prologue("changed", info)
        self.assertEqual(store.profile(), first)

    def test_invalid_completion_and_legacy_migration_preserve_existing_state(self):
        store = self.session.store.account
        initial = store.profile()
        with self.assertRaises(ValueError):
            store.complete_prologue("lab", {"IsMale": True})
        self.assertTrue(store.needs_prologue())
        self.assertEqual(store.profile(), initial)
        # Unknown edits must never be silently replaced by the empty template.
        edited = json.dumps({"User": {"Name": "custom"}})
        self.db.execute("UPDATE local_account SET schema_version=1,profile=?", (edited,))
        self.db.commit()
        with self.assertRaises(ValueError):
            AccountStore(self.db, REFERENCE_DIR)
        self.assertEqual(self.db.execute("SELECT profile FROM local_account").fetchone()[0], edited)

    def test_fresh_prologue_signup_initializes_session_and_discards_provider_token(self):
        body = {
            "AuthKind": 0,
            "AccessToken": "SYNTHETIC_SIGNUP_PROVIDER_TOKEN",
            "Name": "lab",
            "Info": {
                "IsMale": True,
                "VoiceType": 1,
                "Weapon1ItemId": 9010010,
                "Weapon2ItemId": 9080010,
                "BobLindaQuestGrade": 0,
            },
        }
        self.assertFalse(self.session.signed_in)
        response = self.session.handle(request(body, "/auth/sign-up/v2"))
        identity = json.loads(response.body)
        self.assertEqual(identity["UserId"], 1)
        self.assertFalse(identity["NeedPrologue"])
        self.assertTrue(self.session.signed_in)
        profile = json.loads(self.session.handle(request(None, "/auth/fetch-account")).body)
        self.assertEqual(profile["User"]["Name"], "lab")
        self.assertEqual(len(profile["User"]["Characters"]), 1)
        self.assertNotIn("SYNTHETIC_SIGNUP_PROVIDER_TOKEN", "\n".join(self.db.iterdump()))

    def test_lobby_read_responses_preserve_body_kind_and_do_not_mutate_profile(self):
        self.session.handle(
            request({"AuthKind": 0, "AccessToken": "local-test", "Reconnect": False})
        )
        before = self.session.store.account.profile()
        for route in LOBBY_ROUTES:
            with self.subTest(route=route):
                response = self.session.handle(request({}, route))
                self.assertEqual(response.body_type, READ_RESPONSES[route]["body_type"])
                decoded = read_json_body(parse_packet(encode_packet(response)))
                self.assertEqual(type(decoded), type(READ_RESPONSES[route]["value"]))
                if route.startswith("/shop/get-"):
                    self.assertEqual(decoded, [])
        # The native summons loader compares this pair before reloading its
        # catalog. Divergent checksums would keep the empty local catalog stale.
        entry = json.loads(self.session.handle(request(None, "/summon/enter")).body)
        catalog = json.loads(self.session.handle(request(None, "/summon/on-event")).body)
        self.assertEqual(entry["Checksum"], catalog["Checksum"])
        self.assertIs(entry["IsActiveEvent"], False)
        self.assertEqual(self.session.store.account.profile(), before)

    def test_empty_event_exchange_preserves_inventory_and_refuses_existing_coupons(self):
        route = "/user/exchange-summon-pickup-ticket"
        self.session.handle(
            request({"AuthKind": 0, "AccessToken": "test-only", "Reconnect": False})
        )
        before = self.session.store.account.profile()
        before["User"]["ItemStackables"] = [
            {"Id": 1, "ItemId": 110007, "Amount": 20},
            {"Id": 2, "ItemId": 110015, "Amount": 4},
        ]
        before["User"]["ItemIdCounter"] = 2
        self.db.execute("UPDATE local_account SET profile=?", (json.dumps(before),))
        self.db.commit()
        for body in (None, {}):
            response = json.loads(self.session.handle(request(body, route)).body)
            self.assertEqual(
                response,
                {
                    "UserShop": before["UserShop"],
                    "ExchangeSummonPickUpTickets": {},
                    "ExchangeCollaborationPickUpTickets": {},
                },
            )
            self.assertEqual(self.session.store.account.profile(), before)
        self.assertEqual(AccountStore(self.db).read(route), response)
        for field in ("SummonPickUpTickets", "CollaborationPickUpTickets"):
            existing = json.loads(json.dumps(before))
            existing["UserShop"][field] = {"1": 1}
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(existing),))
            self.db.commit()
            with self.assertRaises(PacketError):
                self.session.handle(request(None, route))
            self.assertEqual(self.session.store.account.profile(), existing)

    def test_counter_catalog_migration_preserves_completed_guest_and_inventory(self):
        store = self.session.store.account
        info = {
            "IsMale": True,
            "VoiceType": 1,
            "Weapon1ItemId": 9010010,
            "Weapon2ItemId": 9080010,
            "BobLindaQuestGrade": 0,
        }
        expected = store.complete_prologue("lab", info)
        broken = json.loads(json.dumps(expected))
        broken["UserClaimedReward"]["Ad"]["Inbox"]["Ticket"]["Type"] = 0
        self.db.execute(
            "UPDATE local_account SET schema_version=2,profile=?", (json.dumps(broken),)
        )
        self.db.commit()
        migrated = AccountStore(self.db, REFERENCE_DIR)
        self.assertEqual(migrated.profile(), expected)
        self.assertFalse(migrated.needs_prologue())

    def test_attendance_uses_public_catalog_and_survives_retry_and_restart(self):
        store = self.session.store.account
        today = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        first = store.claim_attendance(today)
        self.assertEqual(first["User"]["MonthlyLoginCount"], 301)
        self.assertEqual(next(a["Amount"] for a in first["User"]["Assets"] if a["Id"] == 70032), 40)
        again = AccountStore(self.db, REFERENCE_DIR).claim_attendance(today + timedelta(hours=1))
        self.assertEqual(again, first)
        next_day = store.claim_attendance(today + timedelta(days=1))
        self.assertEqual(next_day["User"]["MonthlyLoginCount"], 302)
        self.assertEqual(next_day["UserRecord"]["LoginDayCount"], 2)
        self.assertEqual(
            next(a["Amount"] for a in next_day["User"]["Assets"] if a["Id"] == 70004), 200000
        )

    def test_unimplemented_inventory_attendance_reward_is_atomic(self):
        store = self.session.store.account
        now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        for day in range(3):
            store.claim_attendance(now + timedelta(days=day))
        before = store.profile()
        with self.assertRaises(ValueError):
            store.claim_attendance(now + timedelta(days=3))
        self.assertEqual(store.profile(), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM attendance_claims").fetchone()[0], 3)


class LZ4Tests(unittest.TestCase):
    def test_independent_native_compressor_vectors(self):
        vectors = json.loads((FIXTURES / "lz4_native_vectors.json").read_text())
        for vector in vectors["vectors"]:
            with self.subTest(size=vector["bytes"]):
                decoded = lz4_block(base64.b64decode(vector["compressed_base64"]), vector["bytes"])
                self.assertEqual(hashlib.sha256(decoded).hexdigest(), vector["sha256"])

    def test_malformed_blocks_are_rejected(self):
        for data, size in [
            (b"\xf0", 100),
            (b"\x10", 1),
            (b"\x00\x00\x00", 4),
            (b"\x10x\x02\x00", 5),
            (b"\x10x\x01\x00", 2),
            (b"\x10x", 2),
            (b"\x10x", 0),
            (b"", 16 * 1024 * 1024 + 1),
        ]:
            with self.subTest(data=data, size=size), self.assertRaises(PacketError):
                lz4_block(data, size)
