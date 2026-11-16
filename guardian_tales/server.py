# SPDX-License-Identifier: Apache-2.0
"""Loopback guest/prologue development server; full campaign remains pending."""

import argparse
import asyncio
import json
import re
import secrets
import sqlite3
import ssl
import struct
import time
from pathlib import Path

from .bootstrap import BOOTSTRAP_ROUTES, BootstrapSession, GuestStore
from .platform import PLATFORM_ROUTES
from .platform import dispatch as dispatch_platform
from .protocol import PacketError, decode_frame, encode_wire, frame_length, make_pong
from .reference import default_cert_dir


class LocalServer:
    def __init__(
        self,
        data_dir,
        api_port=10100,
        auth_port=10500,
        status_port=17657,
        cert_dir=None,
        reference_dir=None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ports = dict(api=api_port, auth=auth_port, status=status_port)
        self.cert_dir = Path(cert_dir) if cert_dir else default_cert_dir()
        self.listeners = []
        self.active = set()
        self.http_connections = set()
        self.tasks = set()
        self.db = sqlite3.connect(self.data_dir / "server.sqlite3")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)"
        )
        self.db.commit()
        self.guests = GuestStore(self.db, reference_dir)
        self.stopping = False

    def bump(self, name):
        self.db.execute(
            "INSERT INTO counters(name,value) VALUES(?,1) ON CONFLICT(name) DO UPDATE SET value=value+1",
            (name,),
        )
        self.db.commit()

    def status(self):
        return dict(
            service="Guardian Tales 3.57.0 local",
            stage="local_guest_prologue",
            authentication_implemented=True,
            local_guest_sign_in_implemented=True,
            authentication_scope="single_local_guest_only; no_official_credential_validation",
            starter_profile_implemented=True,
            first_phase_entry_implemented=True,
            first_phase_clear_implemented=True,
            knight_training_scope="catalog_levels_and_story_cap_for_unmodified_knights; initial_tutorial_fallback_without_catalog",
            campaign_scope="inn_clear_path; optional_interactions_and_later_phases_pending",
            full_game_implemented=False,
            prologue_selection_saved=not self.guests.account.needs_prologue(),
            game_state_implemented=False,
            host="127.0.0.1",
            ports=self.ports,
            active_connections=len(self.active),
            counters=dict(self.db.execute("SELECT name,value FROM counters")),
            supported=[
                "TLS",
                "application_handshake",
                "LZ4_frames",
                "ping_pong",
                "persistent_local_guest",
                *BOOTSTRAP_ROUTES,
                *PLATFORM_ROUTES,
            ],
            pending=[
                "remaining_first_phase_collectibles_and_custom_state",
                "later_campaign_phases",
                "campaign_progression_and_rewards",
                "game_rules",
            ],
        )

    async def start(self):
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(
                self.cert_dir / "localhost-cert.pem", self.cert_dir / "localhost-key.pem"
            )
            context.set_servername_callback(
                lambda connection, name, ctx: self.bump("tls_client_hellos")
            )
            for name, handler in (("api", self.handle), ("auth", self.platform_http)):
                listener = await asyncio.start_server(
                    handler,
                    "127.0.0.1",
                    self.ports[name],
                    ssl=context,
                    limit=8192 if name == "auth" else 1024 * 1024,
                    ssl_handshake_timeout=5,
                    ssl_shutdown_timeout=1,
                )
                self.listeners.append(listener)
                self.ports[name] = listener.sockets[0].getsockname()[1]
            listener = await asyncio.start_server(
                self.health, "127.0.0.1", self.ports["status"], limit=8192
            )
            self.listeners.append(listener)
            self.ports["status"] = listener.sockets[0].getsockname()[1]
        except BaseException:
            await self.close()
            raise

    async def platform_http(self, reader, writer):
        """10500 is platform HTTPS, not the 10100 binary game transport.

        Configuration and local guest credentials are implemented.
        Other operations return explicit 503.
        Request content (which may contain credentials) is never logged/stored.
        """
        task = asyncio.current_task()
        self.tasks.add(task)
        self.http_connections.add(writer)
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            if len(header) > 8192:
                return
            self.bump("platform_https_requests")
            first, *lines = header.decode("iso-8859-1").split("\r\n")
            parts = first.split(" ")
            fields = {}
            for line in lines:
                if not line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip().lower()
                if key in fields:
                    raise ValueError("Duplicate HTTP header")
                fields[key] = value.strip()
            if "transfer-encoding" in fields:
                raise ValueError("Chunked platform requests are not supported")
            length = int(fields.get("content-length", "0"))
            if not 0 <= length <= 1024 * 1024:
                raise ValueError("Platform body too large")
            raw = await asyncio.wait_for(reader.readexactly(length), 5) if length else b"{}"
            if len(parts) != 3 or parts[0] != "POST" or parts[2] not in ("HTTP/1.0", "HTTP/1.1"):
                code, value = 405, {"Error": "LOCAL_METHOD_NOT_ALLOWED"}
            else:
                request_body = json.loads(raw.decode("utf-8-sig"))
                code, value = dispatch_platform(
                    parts[1], request_body, self.ports["api"], guest_store=self.guests
                )
                if code == 200:
                    self.bump("platform:" + parts[1])
                elif parts[1] in ("/kong/sign-in", "/kong/sign-up"):
                    self.bump("platform_pending:" + parts[1])
            payload = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
            reason = {
                200: "OK",
                400: "Bad Request",
                405: "Method Not Allowed",
                503: "Service Unavailable",
            }[code]
            writer.write(
                (
                    "HTTP/1.1 "
                    + str(code)
                    + " "
                    + reason
                    + "\r\nContent-Type: application/json\r\nContent-Length: "
                ).encode()
                + str(len(payload)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + payload
            )
            await writer.drain()
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
            ConnectionError,
            ValueError,
            RecursionError,
        ):
            pass
        finally:
            self.http_connections.discard(writer)
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (ConnectionError, ssl.SSLError, asyncio.TimeoutError):
                pass
            self.tasks.discard(task)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        if len(self.active) >= 32 or self.stopping:
            writer.close()
            self.tasks.discard(task)
            return
        self.active.add(writer)
        self.bump("connections")
        try:
            hello = await asyncio.wait_for(reader.readexactly(16), 10)
            if hello.rstrip(b"\0") != b"3.57.0":
                self.bump("unsupported_client_version")
                return
            seed = secrets.randbelow(0x70000000) + 0x10000000
            writer.write(struct.pack("<I", seed))
            await writer.drain()
            self.bump("handshakes")
            inbound = outbound = seed
            session = BootstrapSession(self.guests)
            while not self.stopping:
                header = await asyncio.wait_for(reader.readexactly(8), 90)
                size = frame_length(header, inbound)
                rest = await asyncio.wait_for(reader.readexactly(size - 8), 10)
                request = decode_frame(header + rest, inbound)
                inbound = (inbound + 1) & 0xFFFFFFFF
                if request["packet_type"] == 3:
                    response = make_pong(request, int(time.time() * 1000))
                    self.bump("pongs_sent")
                elif request["api"] in BOOTSTRAP_ROUTES:
                    response = session.handle(request)
                    self.bump("api:" + request["api"])
                else:
                    self.bump("unsupported_operations")
                    if re.fullmatch(r"/[a-z0-9/_-]{1,120}", request["api"]):
                        self.bump("unsupported_api:" + request["api"])
                    return
                writer.write(encode_wire(response, outbound))
                await writer.drain()
                outbound = (outbound - 1) & 0xFFFFFFFF
        except asyncio.IncompleteReadError:
            pass
        except (PacketError, asyncio.TimeoutError, ConnectionError, ssl.SSLError):
            if not self.stopping:
                self.bump("invalid_or_interrupted_messages")
        finally:
            self.active.discard(writer)
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (ConnectionError, ssl.SSLError, asyncio.TimeoutError):
                pass
            self.tasks.discard(task)

    async def health(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.http_connections.add(writer)
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
            ok = data.split(b"\r\n", 1)[0] in (
                b"GET /health HTTP/1.1",
                b"GET /health HTTP/1.0",
                b"GET / HTTP/1.1",
            )
            payload = json.dumps(
                self.status() if ok else {"error": "not_found"}, ensure_ascii=False
            ).encode("utf-8")
            code = b"200 OK" if ok else b"404 Not Found"
            writer.write(
                b"HTTP/1.1 "
                + code
                + b"\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: "
                + str(len(payload)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + payload
            )
            await writer.drain()
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
            ConnectionError,
        ):
            pass
        finally:
            self.http_connections.discard(writer)
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (ConnectionError, asyncio.TimeoutError):
                pass
            self.tasks.discard(task)

    async def close(self):
        if self.stopping:
            return
        self.stopping = True
        for listener in self.listeners:
            listener.close()
        await asyncio.gather(*(s.wait_closed() for s in self.listeners), return_exceptions=True)
        for writer in list(self.active | self.http_connections):
            writer.close()
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        self.db.close()


async def run(args):
    server = LocalServer(
        args.data_dir,
        args.api_port,
        args.auth_port,
        args.status_port,
        args.cert_dir,
        args.reference_dir,
    )
    await server.start()
    print("Local guest server started. Full campaign gameplay is not implemented.", flush=True)
    print(
        "Game TLS: 127.0.0.1:"
        + str(server.ports["api"])
        + " | Platform HTTPS: 127.0.0.1:"
        + str(server.ports["auth"]),
        flush=True,
    )
    print("Health: http://127.0.0.1:" + str(server.ports["status"]) + "/health", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        if args.run_seconds:
            await asyncio.sleep(args.run_seconds)
        else:
            await asyncio.Event().wait()
    finally:
        await server.close()


def main(argv=None):
    p = argparse.ArgumentParser(description="Local single-guest server for Guardian Tales 3.57.0.")
    p.add_argument("--data-dir", type=Path, default=Path("local/state"))
    p.add_argument("--api-port", type=int, default=10100)
    p.add_argument("--auth-port", type=int, default=10500)
    p.add_argument("--status-port", type=int, default=17657)
    p.add_argument(
        "--cert-dir",
        type=Path,
        help="Directory with a certificate/key provisioned for this local installation",
    )
    p.add_argument(
        "--reference-dir",
        type=Path,
        help="External bootstrap data and attendance catalog directory",
    )
    p.add_argument("--run-seconds", type=float, default=0)
    args = p.parse_args(argv)
    certificates = args.cert_dir or default_cert_dir()
    if not all(
        (certificates / name).is_file() for name in ("localhost-cert.pem", "localhost-key.pem")
    ):
        p.error(
            "TLS files are missing. Run python scripts/generate_dev_cert.py or pass --cert-dir."
        )
    if args.run_seconds < 0:
        p.error("--run-seconds must be zero or positive")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Server stopped.")


if __name__ == "__main__":
    main()
