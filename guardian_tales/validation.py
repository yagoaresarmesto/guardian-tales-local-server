# SPDX-License-Identifier: Apache-2.0
"""Run tests from a repository checkout and emit a concise JSON result."""

import argparse
import json
import os
import socket
import sys
import unittest
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    if not (Path.cwd() / "tests").is_dir():
        parser.error(
            "Run validation from the repository root; tests are not installed with the package."
        )
    interfaces = [name for _, name in socket.if_nameindex()]
    isolated = os.environ.get("GT_EXPECT_NO_NETWORK") == "1"
    if isolated and interfaces != ["lo"]:
        parser.error("Expected an environment started with --network none")
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(
        json.dumps(
            dict(
                result="PASS" if result.wasSuccessful() else "FAIL",
                tests_run=result.testsRun,
                failures=len(result.failures),
                errors=len(result.errors),
                external_network_disabled=isolated,
                network_interfaces=interfaces,
                python=sys.version.split()[0],
                scope="Protocol, platform HTTPS, local account persistence, reward retries and read-only CDN. APK verification is documented separately.",
            ),
            indent=2,
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
