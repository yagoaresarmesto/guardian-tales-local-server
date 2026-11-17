# SPDX-License-Identifier: Apache-2.0
"""Protocol regression and real loopback TLS integration tests, stdlib only."""

import asyncio
import json
import os
import ssl
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import (
    Packet,
    PacketError,
    decode_frame,
    encode_packet,
    encode_wire,
    frame_length,
    make_pong,
)
from guardian_tales.reference import default_cert_dir
from guardian_tales.server import LocalServer

NETWORK_AUDIT = []


def audit(event, args):
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple):
            if address[0] not in ("127.0.0.1", "::1"):
                raise AssertionError("Tests attempted an external connection")
            NETWORK_AUDIT.append(address)


sys.addaudithook(audit)


class CodecTests(unittest.TestCase):
    def test_real_server_pong_golden_bytes(self):
        golden = (Path(__file__).parent / "fixtures" / "pong_real.bin").read_bytes()
        packet = parse_packet(golden)
        original_stamp, server_stamp = struct.unpack("<qq", bytes.fromhex(packet["body_hex"]))
        ping = parse_packet(
            encode_packet(Packet(3, struct.pack("<q", original_stamp), body_type=2))
        )
        self.assertEqual(encode_packet(make_pong(ping, server_stamp)), golden)

    def test_corruption_rejected(self):
        encoded = bytearray(
            encode_wire(Packet(3, struct.pack("<q", 1234), body_type=2), 1000, nonce=321)
        )
        encoded[-1] ^= 1
        with self.assertRaisesRegex(PacketError, "checksum"):
            decode_frame(bytes(encoded), 1000)

    def test_invalid_length_rejected_before_allocation(self):
        header = struct.pack("<HIH", 0, 0, 1)
        with self.assertRaises(PacketError):
            frame_length(header, 0)


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_root = Path(os.environ.get("GT_TEST_TMP", Path("local/test-tmp"))).resolve()
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_root)
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(self.temp_root))
        self.server = LocalServer(self.temp.name, 0, 0, 0)
        await self.server.start()
        self.context = ssl.create_default_context()
        self.context.load_verify_locations(cafile=str(default_cert_dir() / "localhost-cert.pem"))

    async def asyncTearDown(self):
        await self.server.close()
        self.temp.cleanup()

    async def connect(self, endpoint="api", version=b"3.57.0"):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            self.server.ports[endpoint],
            ssl=self.context,
            server_hostname="localhost",
            ssl_handshake_timeout=5,
        )
        writer.write(version.ljust(16, b"\0"))
        await writer.drain()
        return reader, writer

    async def read_pong(self, reader, counter):
        header = await asyncio.wait_for(reader.readexactly(8), 3)
        size = frame_length(header, counter)
        frame = header + await asyncio.wait_for(reader.readexactly(size - 8), 3)
        return decode_frame(frame, counter)

    async def finish(self, writer):
        writer.close()
        await writer.wait_closed()

    async def test_tls_pipelining_and_fragmentation(self):
        reader, writer = await self.connect()
        seed = struct.unpack("<I", await reader.readexactly(4))[0]
        packets = [
            encode_wire(
                Packet(3, struct.pack("<q", 10000 + i), body_type=2), seed + i, nonce=100 + i
            )
            for i in range(3)
        ]
        writer.write(packets[0][:3])
        await writer.drain()
        await asyncio.sleep(0.01)
        writer.write(packets[0][3:] + packets[1] + packets[2])
        await writer.drain()
        for i in range(3):
            response = await self.read_pong(reader, seed - i)
            self.assertEqual(response["packet_type"], 4)
            echoed, stamp = struct.unpack("<qq", bytes.fromhex(response["body_hex"]))
            self.assertEqual(echoed, 10000 + i)
            self.assertLess(abs(stamp - int(time.time() * 1000)), 5000)
        self.assertEqual(self.server.status()["counters"]["pongs_sent"], 3)
        await self.finish(writer)

    async def test_idle_authenticated_client_can_resume_without_a_heartbeat(self):
        loop = asyncio.get_running_loop()
        schedule = loop.call_later

        def accelerated_long_deadline(delay, callback, *args, **kwargs):
            # Make obsolete long idle timers expire quickly; short I/O/test bounds stay real.
            return schedule(0.03 if delay >= 60 else delay, callback, *args, **kwargs)

        with patch.object(loop, "call_later", side_effect=accelerated_long_deadline):
            reader, writer = await self.connect()
            seed = struct.unpack("<I", await reader.readexactly(4))[0]
            body = {"AuthKind": 0, "AccessToken": "TEST_IDLE_GUEST", "Reconnect": False}
            writer.write(
                encode_wire(
                    Packet(
                        0,
                        json.dumps(body).encode(),
                        body_type=1,
                        api="/auth/sign-in",
                        sequence_id=1,
                    ),
                    seed,
                )
            )
            await writer.drain()
            await self.read_pong(reader, seed)
            before = self.server.guests.account.profile()
            # Download choices can leave the native client without keepalives.
            await asyncio.sleep(0.12)
            writer.write(encode_wire(Packet(3, struct.pack("<q", 123), body_type=2), seed + 1))
            await writer.drain()
            pong = await self.read_pong(reader, seed - 1)
            self.assertEqual(pong["packet_type"], 4)
            self.assertEqual(struct.unpack("<q", bytes.fromhex(pong["body_hex"])[:8])[0], 123)
            self.assertEqual(self.server.guests.account.profile(), before)
            self.assertNotIn("invalid_or_interrupted_messages", self.server.status()["counters"])
            await self.finish(writer)

    async def test_shutdown_closes_idle_game_connection(self):
        reader, writer = await self.connect()
        await reader.readexactly(4)
        await self.server.close()
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        self.assertFalse(self.server.active)
        await self.finish(writer)

    async def test_started_frame_header_still_has_a_completion_deadline(self):
        reader, writer = await self.connect()
        seed = struct.unpack("<I", await reader.readexactly(4))[0]
        loop = asyncio.get_running_loop()
        schedule = loop.call_later

        def accelerated_io_deadline(delay, callback, *args, **kwargs):
            return schedule(0.03 if delay >= 10 else delay, callback, *args, **kwargs)

        with patch.object(loop, "call_later", side_effect=accelerated_io_deadline):
            frame = encode_wire(Packet(3, struct.pack("<q", 123), body_type=2), seed)
            writer.write(frame[:1])
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.server.status()["counters"]["invalid_or_interrupted_messages"], 1)
        await self.finish(writer)

    async def test_platform_https_returns_explicit_not_implemented(self):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            self.server.ports["auth"],
            ssl=self.context,
            server_hostname="localhost",
            ssl_handshake_timeout=5,
        )
        writer.write(
            b"POST /kong/unsupported HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 3)
        self.assertTrue(response.startswith(b"HTTP/1.1 503 "))
        self.assertEqual(
            json.loads(response.split(b"\r\n\r\n", 1)[1]),
            {"Error": "LOCAL_PLATFORM_NOT_IMPLEMENTED"},
        )
        self.assertFalse(self.server.status()["game_state_implemented"])
        await self.finish(writer)

    async def test_platform_configuration_over_tls(self):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            self.server.ports["auth"],
            ssl=self.context,
            server_hostname="localhost",
            ssl_handshake_timeout=5,
        )
        body = json.dumps(
            {"Version": "v3.57.0", "Market": "googleplay", "SystemInfo": {"AppId": "422316"}}
        ).encode()
        header = (
            b"POST /app-info HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
        )
        writer.write(header[:12])
        await writer.drain()
        await asyncio.sleep(0.01)
        writer.write(header[12:] + body)
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 3)
        self.assertTrue(response.startswith(b"HTTP/1.1 200 "))
        config = json.loads(response.split(b"\r\n\r\n", 1)[1])["Body"]["AppInfoData"]
        self.assertEqual(config["ServerAddress"], "127.0.0.1:" + str(self.server.ports["api"]))
        self.assertFalse(config["UpdateRequired"])
        self.assertNotIn(b"guardiantales.com", response)
        await self.finish(writer)

    async def test_invalid_platform_length_does_not_kill_server(self):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            self.server.ports["auth"],
            ssl=self.context,
            server_hostname="localhost",
            ssl_handshake_timeout=5,
        )
        writer.write(b"POST /app-info HTTP/1.1\r\nContent-Length: 9999999999999\r\n\r\n")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), b"")
        await self.finish(writer)

    async def test_wrong_version(self):
        reader, writer = await self.connect(version=b"9.99.0")
        self.assertEqual(await asyncio.wait_for(reader.read(1), 3), b"")
        self.assertEqual(self.server.status()["counters"]["unsupported_client_version"], 1)
        await self.finish(writer)

    async def test_invalid_frame_does_not_kill_listener(self):
        reader, writer = await self.connect()
        await reader.readexactly(4)
        writer.write(struct.pack("<HIH", 0, 0, 1))
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(1), 3), b"")
        await self.finish(writer)
        reader, writer = await self.connect()
        await reader.readexactly(4)
        await self.finish(writer)

    async def test_http_status_exposes_actual_stage(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.ports["status"])
        writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        response = await reader.read()
        payload = json.loads(response.split(b"\r\n\r\n", 1)[1])
        self.assertFalse(payload["full_game_implemented"])
        self.assertEqual(payload["stage"], "local_guest_prologue")
        await self.finish(writer)

    async def test_counters_survive_restart(self):
        self.server.bump("pongs_sent")
        await self.server.close()
        self.server = LocalServer(self.temp.name, 0, 0, 0)
        await self.server.start()
        self.assertEqual(self.server.status()["counters"]["pongs_sent"], 1)

    async def test_shutdown_closes_pending_status_connection(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.ports["status"])
        writer.write(b"GET /health ")
        await writer.drain()
        await asyncio.sleep(0.01)
        await self.server.close()
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        await self.finish(writer)

    async def test_bootstrap_over_tls_and_identity_survives_restart(self):
        async def sign_in(endpoint):
            reader, writer = await self.connect(endpoint)
            seed = struct.unpack("<I", await reader.readexactly(4))[0]
            routes = [
                ("/auth/get-server-info", {}),
                ("/announcement/all", {}),
                (
                    "/auth/sign-in",
                    {"AuthKind": 0, "AccessToken": "SYNTHETIC_TEST_ONLY", "Reconnect": False},
                ),
                ("/auth/fetch-account", None),
            ]
            result = []
            for i, (route, body) in enumerate(routes):
                request = Packet(
                    0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=i + 1
                )
                writer.write(encode_wire(request, (seed + i) & 0xFFFFFFFF))
                await writer.drain()
                response = await self.read_pong(reader, (seed - i) & 0xFFFFFFFF)
                self.assertEqual(response["sequence_id"], i + 1)
                self.assertEqual(response["packet_type"], 1)
                self.assertEqual(response["api"], "")
                result.append(read_json_body(response))
                if route == "/announcement/all":
                    self.assertEqual(response["body_type"], 2)
            await self.finish(writer)
            self.assertFalse(result[0]["InMaintenance"])
            self.assertEqual(result[1], [])
            self.assertEqual(result[-1]["User"]["Id"], result[-2]["UserId"])
            self.assertEqual(result[-1]["User"]["Name"], "Local")
            self.assertEqual(result[-1]["UserProgress"]["StageStates"], {})
            return result[-2]

        first = await sign_in("api")
        await self.server.close()
        self.server = LocalServer(self.temp.name, 0, 0, 0)
        await self.server.start()
        second = await sign_in("api")
        self.assertEqual(first["UserId"], second["UserId"])
        self.assertEqual(first["Uuid"], second["Uuid"])
        self.assertEqual(first["CreatedAt"], second["CreatedAt"])
        self.assertEqual(second["LastSignIn"], first["ServerTime"])
        self.assertNotIn(
            b"SYNTHETIC_TEST_ONLY", (Path(self.temp.name) / "server.sqlite3").read_bytes()
        )

    async def test_battle_stays_explicitly_unimplemented(self):
        reader, writer = await self.connect()
        seed = struct.unpack("<I", await reader.readexactly(4))[0]
        writer.write(encode_wire(Packet(0, sequence_id=1, api="/battle/start"), seed))
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(1), 3), b"")
        self.assertFalse(self.server.status()["game_state_implemented"])
        await self.finish(writer)

    async def test_prologue_save_survives_server_restart_over_tls(self):
        async def exchange(operations):
            reader, writer = await self.connect()
            seed = struct.unpack("<I", await reader.readexactly(4))[0]
            values = []
            for i, (route, value) in enumerate(operations):
                packet = Packet(
                    0, json.dumps(value).encode(), body_type=1, sequence_id=i + 1, api=route
                )
                writer.write(encode_wire(packet, (seed + i) & 0xFFFFFFFF))
                await writer.drain()
                response = await self.read_pong(reader, (seed - i) & 0xFFFFFFFF)
                self.assertEqual(response["result_type"], 0)
                values.append(read_json_body(response))
            await self.finish(writer)
            return values

        credentials = {"AuthKind": 0, "AccessToken": "LOCAL_SYNTHETIC_TEST", "Reconnect": False}
        info = {
            "IsMale": False,
            "VoiceType": 0,
            "Weapon1ItemId": 9010010,
            "Weapon2ItemId": 0,
            "BobLindaQuestGrade": 0,
        }
        first = await exchange(
            [("/auth/sign-in", credentials), ("/auth/sign-name", {"Name": "lab", "Info": info})]
        )
        self.assertTrue(first[0]["NeedPrologue"])
        await self.server.close()
        self.server = LocalServer(self.temp.name, 0, 0, 0)
        await self.server.start()
        after = await exchange([("/auth/sign-in", credentials), ("/auth/fetch-account", None)])
        self.assertFalse(after[0]["NeedPrologue"])
        self.assertEqual(after[1], first[1])
        self.assertEqual(after[1]["User"]["Name"], "lab")
        self.assertEqual(after[1]["User"]["Characters"][0]["CharacterId"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
