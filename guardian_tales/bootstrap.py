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
from .lobby import LOBBY_ROUTES
from .lobby import respond as lobby_response
from .packet_reader import lz4_block
from .protocol import Packet, PacketError
from .reference import compressed_empty_list

BOOTSTRAP_ROUTES = (
    "/auth/get-server-info",
    "/announcement/all",
    "/auth/sign-in",
    "/static-data/resource-url",
    "/static-data/in-app-product-ids",
    "/static-data/get",
    "/static-data/check-update",
    *ACCOUNT_ROUTES,
    *LOBBY_ROUTES,
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
        db.commit()

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
        user_id, guest_uuid, created_at, last = identity
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
        if route in LOBBY_ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            return lobby_response(request)
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
                return json_response(request, self.store.sign_in())
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            if route == "/user/claim-daily-attendance":
                try:
                    return json_response(request, self.store.account.claim_attendance())
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
                    return json_response(request, self.store.account.add_character_experience(body))
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
        if route in STATIC_SEEDS:
            filename, kind = STATIC_SEEDS[route]
            try:
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
            self.signed_in = True
        return json_response(request, value)
