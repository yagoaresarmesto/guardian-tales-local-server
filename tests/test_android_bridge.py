# SPDX-License-Identifier: Apache-2.0
"""Guard the device identity, routing boundary and interrupted-session restoration."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from guardian_tales.android_bridge import (
    Bridge,
    Device,
    identity,
    local_hosts,
    serial,
    staging_path,
)
from guardian_tales.client_cert import generate


class AndroidBridgeTests(unittest.TestCase):
    def info(self):
        return {
            "index": "4",
            "name": "Synthetic test",
            "created_timestamp": 123,
            "is_main": False,
            "is_android_started": True,
            "adb_host_ip": "127.0.0.1",
            "adb_port": 16512,
        }

    def test_reject_main_wrong_name_and_replaced_instance_before_addressing_adb(self):
        info = self.info()
        self.assertEqual(identity(info, 4, "Synthetic test"), ("4", "Synthetic test", 123))
        for value in (
            {**info, "is_main": True},
            {**info, "name": "Other"},
            {**info, "created_timestamp": "123"},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                identity(value, 4, "Synthetic test")
        with patch.object(Device, "info", return_value=info):
            device = Device("synthetic.exe", 4, "Synthetic test")
        with (
            patch.object(device, "info", return_value={**info, "created_timestamp": 456}),
            patch("guardian_tales.android_bridge.command") as run,
        ):
            with self.assertRaises(ValueError):
                device.adb("shell", "id")
            run.assert_not_called()

    def test_loopback_serial_requires_running_android_and_valid_port(self):
        info = self.info()
        self.assertEqual(serial(info), "127.0.0.1:16512")
        for changes in (
            {"adb_port": True},
            {"adb_port": 1},
            {"adb_host_ip": "example.com"},
            {"is_android_started": False},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                serial({**info, **changes})

    def test_root_setting_is_read_from_mumu_configuration_without_enabling_it(self):
        for value in ("true", "false", "unexpected", True):
            result = SimpleNamespace(stdout=json.dumps({"root_permission": value}).encode())
            with (
                self.subTest(value=value),
                patch.object(Device, "info", return_value=self.info()),
                patch("guardian_tales.android_bridge.command", return_value=result) as run,
            ):
                device = Device("synthetic.exe", 4, "Synthetic test")
                if value in ("true", "false"):
                    self.assertEqual(device.root_setting(), value == "true")
                else:
                    with self.assertRaises(ValueError):
                        device.root_setting()
                self.assertNotIn("--value", run.call_args.args[0])

    def test_hosts_preserve_existing_entries_and_refuse_ambiguous_routing(self):
        original = b"127.0.0.1 localhost\n::1 localhost\n192.0.2.1 synthetic.example\n"
        value = local_hosts(original)
        self.assertTrue(value.startswith(original))
        self.assertIn(b"127.0.0.1 eu-auth.live.guardiantales.com\n", value)
        with self.assertRaises(ValueError):
            local_hosts(original + b"192.0.2.2 eu-auth.live.guardiantales.com\n")

    def test_staging_path_cannot_target_an_account_or_system_directory(self):
        self.assertEqual(
            staging_path("/data/local/tmp/gt357bridge_0123456789abcdef"),
            "/data/local/tmp/gt357bridge_0123456789abcdef",
        )
        for value in ("/", "/data/user/0", "/system", "/data/local/tmp/gt357bridge_../x", "x;id"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                staging_path(value)

    def test_existing_keys_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            key = folder / "localhost-key.pem"
            key.write_text("synthetic private input")
            with self.assertRaises(ValueError):
                generate(folder)
            self.assertEqual(key.read_text(), "synthetic private input")

    def test_restore_rejects_a_tampered_staging_path_before_any_device_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            record = {
                "active": True,
                "identity": ["4", "Synthetic test", 123],
                "base": "/data/user/0",
                "chain": "other",
                "reverse_ports": [],
            }
            (folder / "session.json").write_text(json.dumps(record))
            with patch.object(Device, "info", return_value=self.info()):
                device = Device("synthetic.exe", 4, "Synthetic test")
                bridge = Bridge(device, folder, folder, 18081)
                with (
                    patch.object(device, "root") as root,
                    patch.object(device, "set_root") as setting,
                ):
                    with self.assertRaises(ValueError):
                        bridge.restore()
                    root.assert_not_called()
                    setting.assert_not_called()
