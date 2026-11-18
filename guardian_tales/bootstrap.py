# SPDX-License-Identifier: Apache-2.0
"""Observed bootstrap responses backed by a single local guest identity.

This is a loopback development service. Official credentials are never validated,
stored or sent elsewhere. A successful sign-in does not imply playable game state.
"""

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
import uuid
from datetime import datetime, timezone

from .account import ACCOUNT_ROUTES, AccountStore, valid_name, valid_prologue_info
from .guild_war_static import bootstrap_override as guild_war_bootstrap_override
from .jewel_upgrade import ROUTES as JEWEL_UPGRADE_ROUTES
from .lobby import LOBBY_ROUTES
from .lobby import respond as lobby_response
from .orbital import ORBITAL_ENTRY_ROUTE, ORBITAL_EXIT_ROUTE
from .orbital import end as end_orbital
from .orbital import enter as enter_orbital
from .packet_reader import lz4_block
from .party_members import ROUTE as PARTY_MEMBER_ROUTE
from .play_menu import PLAY_MENU_ROUTES
from .play_menu import read as play_menu_read
from .protocol import Packet, PacketError
from .punchking import END as PUNCHKING_END
from .punchking import ROUTES as PUNCHKING_ROUTES
from .punchking import START as PUNCHKING_START
from .punchking import handle as handle_punchking
from .punchking_static import bootstrap_override as punchking_bootstrap_override
from .raid_static import bootstrap_override as raid_bootstrap_override
from .reference import compressed_empty_list
from .snapshots import (
    ACCOUNT_READS,
    IMPORTED_MUTATIONS,
    is_imported,
    preserved_read,
    validate_preserved_request,
)

BOOTSTRAP_ROUTES = (
    "/auth/get-server-info",
    "/announcement/all",
    "/auth/sign-in",
    "/static-data/resource-url",
    "/static-data/device-specific-settings",
    "/static-data/in-app-product-ids",
    "/static-data/get",
    "/static-data/check-update",
    *ACCOUNT_ROUTES,
    *LOBBY_ROUTES,
    *PLAY_MENU_ROUTES,
    ORBITAL_ENTRY_ROUTE,
    ORBITAL_EXIT_ROUTE,
    *PUNCHKING_ROUTES,
)
STATIC_SEEDS = {
    "/static-data/resource-url": ("resource_urls.bin", 2),
    "/static-data/in-app-product-ids": ("product_ids.bin", 2),
    "/static-data/get": ("static_data_get.bin", 2),
    "/static-data/check-update": ("static_data_check.bin", 1),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class GuestStore:
    def __init__(self, db, reference_dir=None):
        self.db = db
        self.account = AccountStore(db, reference_dir)
        self.references = self.account.references
        db.execute(
            "CREATE TABLE IF NOT EXISTS guest (id INTEGER PRIMARY KEY CHECK(id=1), uuid TEXT NOT NULL, created_at TEXT NOT NULL, last_sign_in TEXT, sign_in_count INTEGER NOT NULL DEFAULT 0)"
        )
        db.execute(
            "INSERT OR IGNORE INTO guest(id,uuid,created_at) VALUES(1,?,?)",
            (str(uuid.uuid4()), utc_now()),
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS client_request_state (id INTEGER PRIMARY KEY CHECK(id=1), epoch TEXT NOT NULL)"
        )
        db.execute("INSERT OR IGNORE INTO client_request_state VALUES(1,?)", (str(uuid.uuid4()),))
        db.commit()

    def request_epoch(self, reconnect):
        with self.db:
            if not reconnect:
                self.db.execute(
                    "UPDATE client_request_state SET epoch=? WHERE id=1", (str(uuid.uuid4()),)
                )
        return self.db.execute("SELECT epoch FROM client_request_state WHERE id=1").fetchone()[0]

    def platform_credentials(self):
        """Generate this server's own guest token; never copy official tokens."""
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS guest_secrets (name TEXT PRIMARY KEY,value BLOB NOT NULL)"
            )
            for name in ("signing_key", "guest_token"):
                self.db.execute(
                    "INSERT OR IGNORE INTO guest_secrets VALUES(?,?)",
                    (name, secrets.token_bytes(32)),
                )
        keys = dict(self.db.execute("SELECT name,value FROM guest_secrets"))
        guest_uuid = self.db.execute("SELECT uuid FROM guest WHERE id=1").fetchone()[0]

        def b64(data):
            return base64.b64encode(data).decode().rstrip("=")

        header = b64(b'{"alg":"HS256","typ":"JWT"}')
        # DecodeKATPayload in this client reads standard Base64 segment 1.
        # Claims/casing follow KPUser.DecodeToken. This is a local issuer only.
        payload = b64(
            json.dumps(
                {
                    "PlayerId": guest_uuid,
                    "AuthCode": "LOCAL",
                    "Exp": int(time.time()) + 3600,
                    "BindingInfo": {},
                    "Issuer": "guardian-local",
                },
                separators=(",", ":"),
            ).encode()
        )
        signed = header + "." + payload
        signature = b64(hmac.new(keys["signing_key"], signed.encode(), hashlib.sha256).digest())
        return {
            "kongAccessToken": signed + "." + signature,
            "guestToken": "local." + keys["guest_token"].hex(),
        }

    def sign_in(self):
        now = utc_now()
        with self.db:
            identity = self.db.execute(
                "SELECT id,uuid,created_at,last_sign_in FROM guest WHERE id=1"
            ).fetchone()
            self.db.execute(
                "UPDATE guest SET last_sign_in=?,sign_in_count=sign_in_count+1 WHERE id=1", (now,)
            )
        _, guest_uuid, created_at, last = identity
        user_id = self.account.profile()["User"]["Id"]
        return {
            "GuildMember": None,
            "ServerTime": now,
            "StartOfDay": "00:00:00",
            "TimeWarpSpan": None,
            "UserId": user_id,
            "Uuid": guest_uuid,
            "NeedPrologue": self.account.needs_prologue(),
            "CreatedAt": created_at,
            "Playtime": 0,
            "LastSignIn": last or now,
        }


def read_json_body(request):
    if request["body_type"] == 0:
        return None
    body = bytes.fromhex(request["body_hex"])
    if request["body_type"] == 2:
        if len(body) < 5:
            raise PacketError("Truncated compressed JSON body")
        body = lz4_block(body[:-4], struct.unpack_from("<I", body, len(body) - 4)[0])
    elif request["body_type"] != 1:
        raise PacketError("Unsupported bootstrap body type")
    if len(body) > 1024 * 1024:
        raise PacketError("Bootstrap JSON exceeds limit")
    try:

        def reject_constant(value):
            raise ValueError("Non-finite JSON number")

        return json.loads(body.decode("utf-8-sig"), parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PacketError("Invalid bootstrap JSON") from exc


def json_response(request, value):
    # Observed responses have an empty Api and echo the request SequenceId.
    return Packet(
        packet_type=1,
        body_type=1,
        sequence_id=request["sequence_id"],
        body=json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        ),
    )


class BootstrapSession:
    def __init__(self, store):
        self.store = store
        self.signed_in = False
        self.request_epoch = None

    def handle(self, request):
        if (
            request["version"] != 1
            or request["packet_type"] != 0
            or request["result_type"] != 0
            or request["reliable_type"] != 0
            or not request["sequence_id"]
            or request["hint"]
        ):
            raise PacketError("Unsupported API request header")
        route = request["api"]
        if route not in BOOTSTRAP_ROUTES:
            raise PacketError("API operation not implemented")
        body = read_json_body(request)
        if route in PUNCHKING_ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                operation_id = None
                if route in (PUNCHKING_START, PUNCHKING_END):
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                return json_response(
                    request,
                    handle_punchking(self.store.account, route, body, operation_id),
                )
            except ValueError as error:
                raise PacketError(str(error)) from error
        if self.signed_in and is_imported(self.store.db):
            if route in ACCOUNT_ROUTES and route not in ACCOUNT_READS | IMPORTED_MUTATIONS:
                raise PacketError("Imported-account operation requires its own validated contract")
            preserved = preserved_read(self.store.db, route)
            if preserved is not None:
                try:
                    validate_preserved_request(route, body)
                except ValueError as error:
                    raise PacketError(str(error)) from error
                return json_response(request, preserved)
        if route == ORBITAL_ENTRY_ROUTE:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return json_response(request, enter_orbital(self.store, body))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route == ORBITAL_EXIT_ROUTE:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                epoch = self.request_epoch or self.store.request_epoch(True)
                operation_id = epoch + ":" + str(request["sequence_id"])
                return json_response(request, end_orbital(self.store, body, operation_id))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in PLAY_MENU_ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return json_response(request, play_menu_read(self.store, route, body))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in LOBBY_ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return lobby_response(request, self.store.references)
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in ACCOUNT_ROUTES:
            if route == "/auth/sign-up/v2":
                if (
                    not isinstance(body, dict)
                    or type(body.get("AuthKind")) is not int
                    or not 0 <= body["AuthKind"] <= 0x7FFFFFFF
                    or not isinstance(body.get("AccessToken"), str)
                    or len(body["AccessToken"]) > 131072
                    or not valid_name(body.get("Name"))
                    or not valid_prologue_info(body.get("Info"))
                ):
                    raise PacketError("Malformed local prologue sign-up")
                try:
                    self.store.account.complete_prologue(body["Name"], body["Info"])
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
                # Fresh signup precedes API sign-in. ServerTimeHandler and
                # MyUserKeyHandler consume the same keys as the sign-in response.
                self.signed_in = True
                self.request_epoch = self.store.request_epoch(False)
                return json_response(request, self.store.sign_in())
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            if route == "/festival-pass/redeem-point-rewards":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.redeem_festival_points(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/collection/claim-hero-knowledge-all":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.claim_hero_knowledge(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/user/charge-stamina":
                try:
                    return json_response(request, self.store.account.charge_stamina(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == PARTY_MEMBER_ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.save_party_members(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/item/enhance-weapon":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.enhance_weapon(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in JEWEL_UPGRADE_ROUTES:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.upgrade_jewel(body, operation_id, route)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/item/decompose-jewel":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.decompose_jewels(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in ("/item/change-relic-options/v2", "/item/apply-relic-options"):
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request,
                        self.store.account.change_or_apply_relic_options(body, operation_id, route),
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/item/change-lock-options":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.change_weapon_option_locks(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/item/engrave-weapon":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.engrave_weapon(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in ("/item/change-options", "/item/apply-options"):
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request,
                        self.store.account.change_or_apply_weapon_options(
                            body, operation_id, route
                        ),
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/item/limitbreak-weapon/v2":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.limit_break_weapon(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/user/charge-stamina-by-gem":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.purchase_stamina(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/lobby-village/harvest-basecamp":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.harvest_basecamp(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/lobby-village/receive-gift":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.receive_village_gift(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/lobby-village/remove-obstacle":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.remove_village_obstacle(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/user/guardian-mastery-level-up":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.upgrade_guardian_mastery(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/user/reset-guardian-mastery-level":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.reset_guardian_mastery(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/lobby-village/harvest-all":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.harvest_village(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/preset/delete-preset":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.delete_party_preset(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/preset/set-presets":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.save_party_preset(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/preset/set-selected-preset":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.select_party_preset(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/summon/select-character":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.draw_summon_characters(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/user/claim-daily-attendance":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request,
                        self.store.account.claim_attendance(
                            request=body, operation_id=operation_id
                        ),
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/start-stage":
                try:
                    return json_response(request, self.store.account.start_stage(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/start-quest":
                try:
                    return json_response(request, self.store.account.start_quest(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/progress-quest":
                try:
                    return json_response(request, self.store.account.progress_quest(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/pick-stage-coins":
                try:
                    return json_response(request, self.store.account.pick_stage_coins(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/beat-monsters":
                try:
                    return json_response(request, self.store.account.beat_monsters(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/pick-stage-item":
                try:
                    return json_response(request, self.store.account.pick_stage_item(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/open-treasure":
                try:
                    return json_response(request, self.store.account.open_treasure(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/interact-substage-item":
                try:
                    return json_response(request, self.store.account.interact_substage_item(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/stage/end-stage":
                try:
                    return json_response(request, self.store.account.end_stage(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/user/mark-tutorial":
                try:
                    return json_response(request, self.store.account.mark_tutorial(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/user/add-character-experience":
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.add_character_experience(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/mission/claim-beginner-all":
                try:
                    return json_response(request, self.store.account.claim_beginner_missions(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in ("/mission/claim-challenge-all", "/mission/claim-challenge-all-step"):
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request,
                        self.store.account.claim_challenge_missions(
                            body, operation_id, route == "/mission/claim-challenge-all-step"
                        ),
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/guardian-pass/claim-all":
                try:
                    return json_response(request, self.store.account.claim_guardian_pass(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/festival-pass/claim-all":
                try:
                    return json_response(request, self.store.account.claim_festival_pass(body))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == "/auth/check-name":
                name = body.get("Name") if isinstance(body, dict) else None
                if not valid_name(name):
                    return Packet(
                        packet_type=1,
                        body_type=1,
                        sequence_id=request["sequence_id"],
                        result_type=1,
                        error="ERROR_USER_NAME_INVALID_LENGTH",
                        body=b"{}",
                    )
                # The native prologue success callback ignores the response body.
                # This is validation only; it does not change the saved profile.
                return json_response(request, {})
            if route == "/auth/sign-name":
                if (
                    not isinstance(body, dict)
                    or not valid_name(body.get("Name"))
                    or not valid_prologue_info(body.get("Info"))
                ):
                    raise PacketError("Malformed local prologue selection")
                try:
                    value = self.store.account.complete_prologue(body["Name"], body["Info"])
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
                return json_response(request, value)
            try:
                value = self.store.account.read(route, body)
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
            return json_response(request, value)
        if route == "/static-data/device-specific-settings":
            if body not in (None, {}):
                raise PacketError("Device-specific settings accepts no parameters")
            # The native consumer expects LZ4-compressed static-item text, not JSON.
            # A blank line yields no overrides and retains its built-in DSP fallback.
            return Packet(
                packet_type=1,
                body_type=2,
                sequence_id=request["sequence_id"],
                body=b"\x10\n" + struct.pack("<I", 1),
            )
        if route in STATIC_SEEDS:
            filename, kind = STATIC_SEEDS[route]
            try:
                seed = guild_war_bootstrap_override(self.store.references, filename, body)
                if seed is None:
                    seed = punchking_bootstrap_override(self.store.references, filename, body)
                if seed is None:
                    seed = raid_bootstrap_override(self.store.references, filename, body)
                if seed is None:
                    seed = self.store.references.read_bytes(filename)
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
            return Packet(
                packet_type=1, body_type=kind, sequence_id=request["sequence_id"], body=seed
            )
        if route == "/auth/get-server-info":
            value = {
                "ServerTime": utc_now(),
                "StartOfDay": "00:00:00",
                "InMaintenance": False,
                "ServerInfo": {
                    "PatchServer": None,
                    "PurchaseBlockApplyAppStore": False,
                    "PurchaseBlockApplyGooglePlay": False,
                    "PurchaseBlockTimeFrom": "2022-10-05T22:00:00+09:00",
                    "PurchaseBlockTimeTo": "2022-10-05T23:59:00+09:00",
                },
                "Mode": 0,
                "Build": 1,
                "Region": 6,
                "World": 1,
            }
        elif route == "/announcement/all":
            return Packet(
                packet_type=1,
                body_type=2,
                sequence_id=request["sequence_id"],
                body=compressed_empty_list(),
            )
        else:
            if (
                not isinstance(body, dict)
                or type(body.get("AuthKind")) is not int
                or not 0 <= body["AuthKind"] <= 0x7FFFFFFF
                or not isinstance(body.get("AccessToken"), str)
                or len(body["AccessToken"]) > 131072
                or type(body.get("Reconnect")) is not bool
            ):
                raise PacketError("Malformed sign-in request")
            # AccessToken is deliberately not retained. All connections in this
            # local development instance use the same isolated guest identity.
            value = self.store.sign_in()
            self.request_epoch = self.store.request_epoch(body["Reconnect"])
            self.signed_in = True
        return json_response(request, value)
