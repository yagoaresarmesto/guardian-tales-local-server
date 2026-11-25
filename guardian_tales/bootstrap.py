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

from . import (
    andras_trial,
    classic_coop,
    colosseum,
    expedition,
    hero_blessing,
    hero_reset,
    jewel_socket,
    kamazone,
    kamazone_practice,
    kamazone_preview,
    kamazone_run,
    multi_presets,
    orbital_levels,
    story_interactions,
    story_rewards,
    story_world_pass,
    tetis,
    tetis_map_trial,
    tetis_presets,
    village_dispatch,
)
from .account import ACCOUNT_ROUTES, AccountStore, valid_name, valid_prologue_info
from .account_name import ROUTE as ACCOUNT_NAME_ROUTE
from .campaign_complete import campaign_test_enabled
from .guild_war_static import bootstrap_override as guild_war_bootstrap_override
from .head_hunter_static import bootstrap_seed as head_hunter_bootstrap_seed
from .hero_equipment import ROUTES as HERO_EQUIPMENT_ROUTES
from .item_extract import ROUTE as ITEM_EXTRACT_ROUTE
from .item_lock import ROUTES as ITEM_LOCK_ROUTES
from .item_sell import ROUTE as ITEM_SELL_ROUTE
from .jewel_upgrade import ROUTES as JEWEL_UPGRADE_ROUTES
from .lobby import LOBBY_ROUTES
from .lobby import respond as lobby_response
from .nickname_static import bootstrap_seed as nickname_bootstrap_seed
from .orbital import ORBITAL_ENTRY_ROUTE, ORBITAL_EXIT_ROUTE, ORBITAL_FORMATION_ROUTE
from .orbital import end as end_orbital
from .orbital import enter as enter_orbital
from .orbital import save_formation as save_orbital_formation
from .packet_reader import lz4_block
from .party_members import ROUTE as PARTY_MEMBER_ROUTE
from .play_menu import PLAY_MENU_ROUTES
from .play_menu import read as play_menu_read
from .portrait_frame import ROUTE as PORTRAIT_FRAME_ROUTE
from .preset_order import ROUTE as PRESET_REORDER_ROUTE
from .protocol import Packet, PacketError
from .punchking import END as PUNCHKING_END
from .punchking import ROUTES as PUNCHKING_ROUTES
from .punchking import START as PUNCHKING_START
from .punchking import handle as handle_punchking
from .punchking_static import bootstrap_override as punchking_bootstrap_override
from .raid_static import bootstrap_override as raid_bootstrap_override
from .raid_static import selected_static_seed
from .reference import compressed_empty_list
from .representative_character import ROUTE as REPRESENTATIVE_CHARACTER_ROUTE
from .snapshots import (
    ACCOUNT_READS,
    IMPORTED_MUTATIONS,
    is_imported,
    preserved_read,
    validate_preserved_request,
)
from .story_quests import ROUTES as STORY_QUEST_ROUTES
from .story_quests import handle as handle_story_quest
from .summon_payment import CHARACTER_ROUTE, WEAPON_ROUTE
from .test_item_static import bootstrap_seed as test_item_bootstrap_seed
from .weapon_summon import ROUTE as WEAPON_SUMMON_ROUTE

BOOTSTRAP_ROUTES = (
    "/auth/get-server-info",
    "/announcement/all",
    "/auth/sign-in",
    "/auth/unpause",
    "/static-data/resource-url",
    "/static-data/device-specific-settings",
    "/static-data/in-app-product-ids",
    "/static-data/get",
    "/static-data/check-update",
    *ACCOUNT_ROUTES,
    *LOBBY_ROUTES,
    *PLAY_MENU_ROUTES,
    *expedition.ROUTES,
    *multi_presets.ROUTES,
    *classic_coop.ROUTES,
    *tetis.ROUTES,
    *kamazone_preview.ROUTES,
    kamazone_practice.SAVE,
    *kamazone_run.ROUTES,
    ORBITAL_ENTRY_ROUTE,
    ORBITAL_EXIT_ROUTE,
    ORBITAL_FORMATION_ROUTE,
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


def static_seed(references, filename, body):
    seed = guild_war_bootstrap_override(references, filename, body)
    if seed is None:
        seed = punchking_bootstrap_override(references, filename, body)
    if seed is None:
        seed = raid_bootstrap_override(references, filename, body)
    return references.read_bytes(filename) if seed is None else seed


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
        self.colosseum_opponents = ()
        self.classic_coop = classic_coop.Practice()
        self.andras_trial_selection = None

    def handle(self, request):
        try:
            selection = andras_trial.load(self.store.references)
            if selection is None or not selection["active"]:
                self.andras_trial_selection = None
                return self._handle(request)
            if selection != self.andras_trial_selection:
                andras_trial.validate_active(self.store, selection)
                self.andras_trial_selection = selection
            return andras_trial.project_response(self._handle(request), selection, self.store)
        except ValueError as error:
            raise PacketError(str(error)) from error

    def _handle(self, request):
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
        if route in tetis.ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                epoch = self.request_epoch or self.store.request_epoch(True)
                return json_response(
                    request,
                    tetis.handle(
                        self.store.account, route, body, epoch + ":" + str(request["sequence_id"])
                    ),
                )
            except (ValueError, FileNotFoundError) as exc:
                raise PacketError(str(exc)) from exc
        if route == "/auth/unpause":
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            if body not in (None, {}):
                raise PacketError("Unpause accepts no parameters")
            return json_response(request, {"ServerTime": utc_now(), "StartOfDay": "00:00:00"})
        if (
            route == classic_coop.LEAVE
            and isinstance(body, dict)
            and type(body.get("StageId")) is int
            and body["StageId"] == classic_coop.STAGE_ID
        ):
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return json_response(request, classic_coop.leave(self.store.account))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
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
            test_story = (
                route.startswith("/stage/")
                or route in story_interactions.ROUTES
                or route in story_rewards.ROUTES
                or route in story_world_pass.ROUTES
            ) and campaign_test_enabled(self.store.db)
            if (
                route in ACCOUNT_ROUTES
                and route not in ACCOUNT_READS | IMPORTED_MUTATIONS
                and not test_story
            ):
                raise PacketError("Imported-account operation requires its own validated contract")
            if story_rewards.is_story_feature(route, body) and not campaign_test_enabled(
                self.store.db
            ):
                raise PacketError(
                    "Imported account requires campaign test mode for story feature rewards"
                )
            preserved = None if test_story else preserved_read(self.store.db, route)
            if preserved is not None:
                try:
                    validate_preserved_request(route, body)
                except ValueError as error:
                    raise PacketError(str(error)) from error
                return json_response(request, preserved)
        if route in kamazone_run.ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                selected, source = kamazone_preview.selected_source(self.store.account)
                epoch = self.request_epoch or self.store.request_epoch(True)
                extras = kamazone_run.handle(
                    self.store.account,
                    source,
                    selected["season_id"],
                    route,
                    body,
                    epoch + ":" + str(request["sequence_id"]),
                )
                response = kamazone_preview.enter(self.store.account, {"IsPartial": False})
                response.update(extras)
                return json_response(request, response)
            except (OSError, ValueError) as exc:
                raise PacketError(str(exc)) from exc
        if route == kamazone_practice.SAVE:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                selected, source = kamazone_preview.selected_source(self.store.account)
                epoch = self.request_epoch or self.store.request_epoch(True)
                kamazone_practice.save(
                    self.store.references,
                    source,
                    selected["season_id"],
                    body,
                    epoch + ":" + str(request["sequence_id"]),
                )
                # Return a complete idle singleton, including an exact positive-
                # level Benefits array, so cleared selections do not linger and
                # partial model defaults cannot erase the preview's other fields.
                return json_response(
                    request, kamazone_preview.enter(self.store.account, {"IsPartial": False})
                )
            except (OSError, ValueError) as exc:
                raise PacketError(str(exc)) from exc
        if route in kamazone_preview.ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                operation = (
                    kamazone_preview.enter
                    if route == kamazone_preview.ROUTE
                    else kamazone_preview.rankings
                )
                return json_response(request, operation(self.store.account, body))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route == ORBITAL_ENTRY_ROUTE:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return json_response(request, enter_orbital(self.store, body))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in (ORBITAL_EXIT_ROUTE, ORBITAL_FORMATION_ROUTE):
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                epoch = self.request_epoch or self.store.request_epoch(True)
                operation_id = epoch + ":" + str(request["sequence_id"])
                operation = end_orbital if route == ORBITAL_EXIT_ROUTE else save_orbital_formation
                return json_response(request, operation(self.store, body, operation_id))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in multi_presets.ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                epoch = self.request_epoch or self.store.request_epoch(True)
                operation_id = epoch + ":" + str(request["sequence_id"])
                return json_response(
                    request, multi_presets.handle(self.store.account, route, body, operation_id)
                )
            except ValueError as error:
                raise PacketError(str(error)) from error
        if route in PLAY_MENU_ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return json_response(request, play_menu_read(self.store, route, body))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in expedition.ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return json_response(request, expedition.read(self.store, route, body))
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in classic_coop.ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return json_response(
                    request, self.classic_coop.respond(self.store.references, route, body)
                )
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
        if route in LOBBY_ROUTES:
            if not self.signed_in:
                raise PacketError("Local guest sign-in required")
            try:
                return lobby_response(request, self.store.references, self.store.db, body)
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
            if route in hero_blessing.ROUTES or route == hero_reset.ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    if route == hero_reset.ROUTE:
                        result = hero_reset.reset(self.store.account, body, operation_id)
                    else:
                        result = hero_blessing.bless(self.store.account, route, body, operation_id)
                    return json_response(request, result)
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in HERO_EQUIPMENT_ROUTES:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.change_hero_equipment(body, operation_id, route)
                    )
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
            if route == REPRESENTATIVE_CHARACTER_ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request,
                        self.store.account.select_representative_character(body, operation_id),
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == ACCOUNT_NAME_ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.change_name(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == PORTRAIT_FRAME_ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.select_portrait_frame(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == ITEM_EXTRACT_ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.extract_items(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == ITEM_SELL_ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(request, self.store.account.sell_items(body, operation_id))
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in ITEM_LOCK_ROUTES:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.change_item_locks(body, operation_id, route)
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
            if route in jewel_socket.ROUTES:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, jewel_socket.handle(self.store.account, body, operation_id, route)
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
            if route == village_dispatch.PREPARE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, village_dispatch.prepare(self.store.account, body, operation_id)
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
            if route in ("/preset/delete-preset", tetis_presets.DELETE):
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request,
                        self.store.account.delete_party_preset(
                            body, operation_id, route == tetis_presets.DELETE
                        ),
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route == PRESET_REORDER_ROUTE:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request, self.store.account.reorder_party_presets(body, operation_id)
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in ("/preset/set-presets", tetis_presets.SAVE):
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    return json_response(
                        request,
                        self.store.account.save_party_preset(
                            body, operation_id, route == tetis_presets.SAVE
                        ),
                    )
                except ValueError as exc:
                    raise PacketError(str(exc)) from exc
            if route in colosseum.MUTATIONS:
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    value = colosseum.save(self.store.account, route, body, operation_id)
                    return json_response(request, value)
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
            if route in (
                "/summon/select-character",
                WEAPON_SUMMON_ROUTE,
                CHARACTER_ROUTE,
                WEAPON_ROUTE,
            ):
                try:
                    epoch = self.request_epoch or self.store.request_epoch(True)
                    operation_id = epoch + ":" + str(request["sequence_id"])
                    draw = (
                        self.store.account.draw_summon_weapons
                        if route in (WEAPON_SUMMON_ROUTE, WEAPON_ROUTE)
                        else self.store.account.draw_summon_characters
                    )
                    return json_response(
                        request,
                        draw(body, operation_id, regular=route in (CHARACTER_ROUTE, WEAPON_ROUTE)),
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
            if route in story_world_pass.ROUTES:
                return json_response(
                    request, story_world_pass.handle(self.store.account, route, body)
                )
            if route in story_interactions.ROUTES:
                epoch = self.request_epoch or self.store.request_epoch(True)
                operation_id = epoch + ":" + str(request["sequence_id"])
                return json_response(
                    request,
                    story_interactions.handle(self.store.account, route, body, operation_id),
                )
            if route in story_rewards.ROUTES or story_rewards.is_story_feature(route, body):
                return json_response(request, story_rewards.claim(self.store.account, route, body))
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
            if route in STORY_QUEST_ROUTES:
                try:
                    return json_response(
                        request, handle_story_quest(self.store.account, route, body)
                    )
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
            if route == classic_coop.LEAVE:
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
                    if self.andras_trial_selection is not None:
                        from .andras_trial_training import targets_trial, train

                        if targets_trial(body, self.andras_trial_selection):
                            return json_response(
                                request,
                                train(self.store, self.andras_trial_selection, body, operation_id),
                            )
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
                if route == colosseum.START:
                    value = colosseum.read(
                        self.store.account,
                        route,
                        body,
                        last_served_opponents=self.colosseum_opponents,
                    )
                else:
                    value = self.store.account.read(route, body)
            except ValueError as exc:
                raise PacketError(str(exc)) from exc
            if route in colosseum.OPPONENT_LIST_ROUTES:
                self.colosseum_opponents = value["Opponents"]
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

                def parent(references, name, value):
                    return nickname_bootstrap_seed(references, name, value, static_seed)

                def expedition_seed(references, name, value):
                    return expedition.bootstrap_seed(references, name, value, parent)

                def effective(references, name, value):
                    return andras_trial.bootstrap_seed(references, name, value, expedition_seed)

                def pinned(references, name, value):
                    return test_item_bootstrap_seed(
                        self.store.db, references, name, value, effective
                    )

                def equipped(references, name, value):
                    return head_hunter_bootstrap_seed(
                        self.store.db, references, name, value, pinned
                    )

                def calendar(references, name, value):
                    return kamazone.bootstrap_seed(references, name, value, equipped)

                def practice(references, name, value):
                    return kamazone_practice.bootstrap_seed(references, name, value, calendar)

                def tetis_seed(references, name, value):
                    return tetis_map_trial.bootstrap_seed(references, name, value, practice)

                seed = selected_static_seed(
                    self.store.references,
                    filename,
                    body,
                    tetis_seed,
                    orbital_levels.bootstrap_selection,
                    orbital_levels.prepare_selection,
                )
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
            self.colosseum_opponents = ()
            self.signed_in = True
        return json_response(request, value)
