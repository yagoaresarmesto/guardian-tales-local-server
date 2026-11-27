# SPDX-License-Identifier: Apache-2.0
"""Exercise the public Mac CLI against a local emulator ADB transcript."""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from guardian_tales.runtime import android_bridge, mac_bridge


class FakeAdb:
    serial = "127.0.0.1:16416"
    android_id = b"0123456789abcdef"
    package = b"versionCode=431 minSdk=23\n versionName=3.57.0\n"
    health = b'HTTP/1.0 200 OK\r\n\r\n{"service":"Guardian Tales 3.57.0 local"}'

    def __init__(self):
        self.calls = []
        self.ports = {}
        self.race = None

    def __call__(self, argv):
        assert argv[:5] == ["adb", "-H", "127.0.0.1", "-P", "5037"]
        args = argv[5:]
        self.calls.append(args)
        if args == ["devices", "-l"]:
            data = f"List of devices attached\n{self.serial} device product:test transport_id:7\n".encode()
        elif args == ["connect", self.serial]:
            data = b"connected"
        else:
            assert args[:2] == ["-t", "7"]
            args = args[2:]
            answers = {
                ("get-serialno",): self.serial.encode(),
                ("shell", "settings", "get", "secure", "android_id"): self.android_id,
                ("shell", "getprop", "ro.build.version.release"): b"12",
                ("shell", "getprop", "ro.product.cpu.abilist"): b"arm64-v8a,x86_64",
                ("shell", "dumpsys", "package", "com.kakaogames.gdts"): self.package,
            }
            if tuple(args) in answers:
                data = answers[tuple(args)]
            elif args == ["reverse", "--list"]:
                data = "".join(f"host-7 {a} {b}\n" for a, b in self.ports.items()).encode()
            elif args[:2] == ["reverse", "--no-rebind"]:
                a, b = args[2:]
                if a == self.race:
                    self.ports[a] = b
                    raise RuntimeError("adb: error: cannot rebind existing socket")
                assert a not in self.ports
                self.ports[a] = b
                data = b""
            elif args[:2] == ["reverse", "--remove"]:
                del self.ports[args[2]]
                data = b""
            elif args[0] == "exec-out" and "GET /health" in args[1]:
                assert self.ports["tcp:17657"] == "tcp:17657"
                data = self.health
            else:
                raise AssertionError(args)
        return SimpleNamespace(stdout=data)


class MacBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.adb = FakeAdb()
        for name, kwargs in [
            ("command", {"side_effect": self.adb}),
            ("adb_executable", {"return_value": "adb"}),
            ("preflight", {}),
        ]:
            p = patch.object(mac_bridge, name, **kwargs)
            p.start()
            self.addCleanup(p.stop)

    def cli(self, action):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            android_bridge.main(
                ["mac", action, "--serial", self.adb.serial, "--session-dir", str(self.folder)]
            )
        return output.getvalue()

    def test_check_accepts_both_local_serial_styles_without_installing_ports(self):
        for value in ("127.0.0.1:16416", "emulator-5554"):
            self.adb.serial = value
            self.assertIn("ADB CHECK PASSED", self.cli("check"))
        self.assertEqual(self.adb.ports, {})
        self.assertFalse(list(self.folder.iterdir()))
        self.assertNotIn(["connect", "emulator-5554"], self.adb.calls)
        self.adb.package = b"versionCode=4310 minSdk=23\n versionName=3.57.0\n"
        with self.assertRaises(SystemExit):
            self.cli("check")
        for invalid in ("other:5555", "127.0.0.1:70000", "emulator-1", "usb-device"):
            with self.assertRaises(argparse.ArgumentTypeError):
                mac_bridge.local_serial(invalid)

    def test_run_reaches_guest_health_and_cleans_up_on_interrupt(self):
        self.adb.ports["tcp:33333"] = "tcp:33333"
        with patch.object(mac_bridge.time, "sleep", side_effect=KeyboardInterrupt):
            output = self.cli("run")
        self.assertIn("LOCAL PORTS READY", output)
        self.assertIn("LOCAL PORTS INACTIVE", output)
        self.assertEqual(self.adb.ports, {"tcp:33333": "tcp:33333"})
        self.assertFalse((self.folder / "mac-forward.json").exists())
        self.assertIn(
            ["-t", "7", "reverse", "--no-rebind", "tcp:18080", "tcp:18081"], self.adb.calls
        )

    def test_partial_failure_preserves_a_concurrent_mapping(self):
        self.adb.race = "tcp:10500"
        with self.assertRaises(SystemExit):
            self.cli("run")
        self.assertEqual(self.adb.ports, {"tcp:10500": "tcp:10500"})

    def test_wrong_backend_rolls_back(self):
        self.adb.health = b"HTTP/1.1 404 Not Found\r\n\r\n"
        with self.assertRaises(SystemExit):
            self.cli("run")
        self.assertEqual(self.adb.ports, {})

    def test_restore_checks_device_and_only_removes_matching_forwards(self):
        device = mac_bridge.LocalDevice("adb", self.adb.serial)
        session = mac_bridge.ForwardSession(self.folder, device)
        session.start(18081)
        with self.assertRaises(SystemExit):
            self.cli("run")
        self.assertEqual(len(self.adb.ports), 4)
        self.adb.android_id = b"fedcba9876543210"
        with self.assertRaises(SystemExit):
            self.cli("restore")
        self.assertEqual(len(self.adb.ports), 4)
        self.adb.android_id = FakeAdb.android_id
        self.adb.ports["tcp:18080"] = "tcp:29999"
        with self.assertRaises(SystemExit):
            self.cli("restore")
        self.assertEqual(self.adb.ports, {"tcp:18080": "tcp:29999"})
        self.assertEqual(json.loads(session.path.read_text())["ports"], [18080])
        self.adb.ports.clear()
        self.cli("restore")
        self.assertFalse(session.path.exists())
