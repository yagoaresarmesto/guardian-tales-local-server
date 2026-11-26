# SPDX-License-Identifier: Apache-2.0
"""Exercise real listeners with synthetic requests and a temporary database."""

import argparse
import asyncio
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

from .probe import probe, probe_bootstrap, probe_platform
from .server import LocalServer


def loopback_guard(event, args):
    if event == "socket.connect" and isinstance(args[1], tuple):
        if args[1][0] not in ("127.0.0.1", "::1"):
            raise RuntimeError("The demonstration allows only loopback connections")


async def run_demo(cert_dir):
    sys.addaudithook(loopback_guard)
    interfaces = [name for _, name in socket.if_nameindex()]
    isolated = os.environ.get("GT_EXPECT_NO_NETWORK") == "1"
    if isolated and interfaces != ["lo"]:
        raise RuntimeError("Expected an environment started with --network none")
    with tempfile.TemporaryDirectory(
        prefix="gt-local-demo-", dir=os.environ.get("GT_TEST_TMP")
    ) as directory:
        server = LocalServer(directory, 0, 0, 0, cert_dir=cert_dir)
        await server.start()
        try:
            api = await probe(server.ports["api"], 3, cert_dir)
            guest = await probe_bootstrap(server.ports["api"], cert_dir)
            platform = await probe_platform(server.ports["auth"], cert_dir)
            assert server.status()["counters"]["pongs_sent"] == 3
            print(
                json.dumps(
                    dict(
                        result="PASS",
                        external_network_disabled=isolated,
                        network_interfaces=interfaces,
                        api_pongs=len(api["pongs"]),
                        guest=guest,
                        platform=platform,
                        tls=api["tls"],
                        original_client_exercised=False,
                        full_game_implemented=False,
                        scope="Synthetic loopback probes; this command does not open the APK.",
                    ),
                    indent=2,
                )
            )
        finally:
            await server.close()


def main(argv=None):
    from guardian_tales.content.reference import default_cert_dir

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cert-dir", type=Path, default=default_cert_dir())
    args = parser.parse_args(argv)
    asyncio.run(run_demo(args.cert_dir))


if __name__ == "__main__":
    main()
