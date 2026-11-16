# SPDX-License-Identifier: Apache-2.0
"""Loopback-only client for exercising the transport prototype."""

import argparse
import asyncio
import json
import ssl
import struct
import time
from pathlib import Path

from .protocol import Packet, decode_frame, encode_wire, frame_length
from .reference import default_cert_dir


def tls_context(cert_dir=None):
    context = ssl.create_default_context()
    context.load_verify_locations(
        cafile=str((Path(cert_dir) if cert_dir else default_cert_dir()) / "localhost-cert.pem")
    )
    return context


async def probe(port, count=3, cert_dir=None):
    context = tls_context(cert_dir)
    reader, writer = await asyncio.open_connection(
        "127.0.0.1", port, ssl=context, server_hostname="localhost", ssl_handshake_timeout=5
    )
    try:
        tls = writer.get_extra_info("ssl_object").version()
        writer.write(b"3.57.0".ljust(16, b"\0"))
        await writer.drain()
        seed = struct.unpack("<I", await asyncio.wait_for(reader.readexactly(4), 5))[0]
        pongs = []
        for i in range(count):
            stamp = int(time.time() * 1000)
            ping = Packet(packet_type=3, body_type=2, body=struct.pack("<q", stamp))
            writer.write(encode_wire(ping, (seed + i) & 0xFFFFFFFF))
            await writer.drain()
            counter = (seed - i) & 0xFFFFFFFF
            header = await asyncio.wait_for(reader.readexactly(8), 5)
            size = frame_length(header, counter)
            frame = header + await asyncio.wait_for(reader.readexactly(size - 8), 5)
            decoded = decode_frame(frame, counter)
            echoed, server_stamp = struct.unpack("<qq", bytes.fromhex(decoded["body_hex"]))
            if decoded["packet_type"] != 4 or echoed != stamp:
                raise ValueError("Unexpected keepalive response")
            pongs.append(
                dict(
                    index=i + 1,
                    packet_type="Pong",
                    echo_matches=True,
                    server_timestamp_ms=server_stamp,
                )
            )
        return dict(
            result="PASS",
            host="127.0.0.1",
            port=port,
            tls=tls,
            pongs=pongs,
            original_client_exercised=False,
        )
    finally:
        writer.close()
        await writer.wait_closed()


async def probe_bootstrap(port, cert_dir=None):
    context = tls_context(cert_dir)
    reader, writer = await asyncio.open_connection(
        "127.0.0.1", port, ssl=context, server_hostname="localhost"
    )
    try:
        writer.write(b"3.57.0".ljust(16, b"\0"))
        await writer.drain()
        seed = struct.unpack("<I", await reader.readexactly(4))[0]
        identities = []
        for i in range(2):
            body = json.dumps(
                {"AuthKind": 0, "AccessToken": "LOCAL_SYNTHETIC_DEMO", "Reconnect": bool(i)}
            ).encode()
            writer.write(
                encode_wire(
                    Packet(0, body, body_type=1, sequence_id=i + 1, api="/auth/sign-in"),
                    (seed + i) & 0xFFFFFFFF,
                )
            )
            await writer.drain()
            counter = (seed - i) & 0xFFFFFFFF
            header = await asyncio.wait_for(reader.readexactly(8), 5)
            n = frame_length(header, counter)
            p = decode_frame(header + await reader.readexactly(n - 8), counter)
            if p["sequence_id"] != i + 1 or p["packet_type"] != 1 or p["result_type"] != 0:
                raise ValueError("Unexpected sign-in response header")
            identities.append(json.loads(bytes.fromhex(p["body_hex"])))
        if identities[0]["Uuid"] != identities[1]["Uuid"]:
            raise ValueError("Guest identity changed during reconnect")
        writer.write(
            encode_wire(
                Packet(0, sequence_id=3, api="/auth/fetch-account"), (seed + 2) & 0xFFFFFFFF
            )
        )
        await writer.drain()
        counter = (seed - 2) & 0xFFFFFFFF
        header = await asyncio.wait_for(reader.readexactly(8), 5)
        n = frame_length(header, counter)
        packet = decode_frame(header + await reader.readexactly(n - 8), counter)
        profile = json.loads(bytes.fromhex(packet["body_hex"]))
        if (
            packet["sequence_id"] != 3
            or packet["result_type"] != 0
            or profile["User"]["Id"] != identities[-1]["UserId"]
            or profile["UserProgress"]["StageStates"]
        ):
            raise ValueError("Unexpected starter profile")
        return {
            "result": "PASS",
            "local_guest_sign_ins": 2,
            "same_identity": True,
            "starter_profile_received": True,
            "prologue_characters": len(profile["User"]["Characters"]),
            "original_client_exercised": False,
        }
    finally:
        writer.close()
        await writer.wait_closed()


async def probe_platform(port, cert_dir=None):
    context = tls_context(cert_dir)

    async def post(route, value, expected):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=context, server_hostname="localhost"
        )
        try:
            data = json.dumps(value).encode()
            writer.write(
                (
                    "POST "
                    + route
                    + " HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
                    + str(len(data))
                    + "\r\n\r\n"
                ).encode()
                + data
            )
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 5)
            if not response.startswith(("HTTP/1.1 " + str(expected) + " ").encode()):
                raise ValueError("Unexpected platform HTTP status")
            return json.loads(response.split(b"\r\n\r\n", 1)[1])
        finally:
            writer.close()
            await writer.wait_closed()

    app = await post(
        "/app-info",
        {"Version": "v3.57.0", "Market": "googleplay", "SystemInfo": {"AppId": "422316"}},
        200,
    )
    assert not app["Body"]["UpdateRequired"]
    credentials = await post(
        "/kong/sign-up", {"AuthKind": "guest", "Token": "LOCAL_SYNTHETIC_DEMO"}, 200
    )
    assert credentials["Body"]["guestToken"].startswith("local.")
    await post("/kong/unsupported", {}, 503)
    return {
        "https_reachable": True,
        "app_info_received": True,
        "local_guest_signup": True,
        "unsupported_route_http_status": 503,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Probe only the local transport; no official services are contacted."
    )
    p.add_argument("--port", type=int, default=10100)
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--cert-dir", type=Path)
    args = p.parse_args(argv)
    if not 1 <= args.count <= 100:
        p.error("--count must be between 1 and 100")
    print(
        json.dumps(
            asyncio.run(probe(args.port, args.count, args.cert_dir)), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
