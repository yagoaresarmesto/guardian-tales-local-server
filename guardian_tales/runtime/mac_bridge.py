# SPDX-License-Identifier: Apache-2.0
"""Connect Android loopback ports to local services through a Mac emulator's ADB."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .android_bridge import PACKAGE, command, preflight
from .state_lock import StateLock


def local_serial(value):
    match = re.fullmatch(r"(?:127\.0\.0\.1:|emulator-)([1-9][0-9]{0,4})", value)
    if not match or not 1024 <= int(match[1]) <= 65535:
        raise argparse.ArgumentTypeError("Use the exact local ADB serial from the dedicated device")
    return value


def adb_executable(override):
    if override:
        paths = [Path(override).expanduser()]
    else:
        bundle = Path("/Applications/MuMuPlayer.app/Contents/MacOS")
        installed = shutil.which("adb")
        paths = [Path(installed)] if installed else []
        if os.environ.get("ANDROID_HOME"):
            paths.append(Path(os.environ["ANDROID_HOME"]) / "platform-tools/adb")
        paths.extend(
            [
                Path.home() / "Library/Android/sdk/platform-tools/adb",
                bundle / "MuMuPlayerPro.app/Contents/MacOS/tools/adb",
                bundle / "MuMuEmulator.app/Contents/MacOS/tools/adb",
            ]
        )
    for path in paths:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    raise ValueError("Provide the Mac ADB executable with --adb or install Android Platform-Tools")


class LocalDevice:
    def __init__(self, executable, serial):
        self.server = [executable, "-H", "127.0.0.1", "-P", "5037"]
        self.serial = serial
        if serial.startswith("127.0.0.1:"):
            command([*self.server, "connect", serial])
        listing = command([*self.server, "devices", "-l"]).stdout.decode()
        for row in listing.splitlines():
            fields = row.split()
            if fields[:2] == [serial, "device"]:
                for field in fields[2:]:
                    if re.fullmatch(r"transport_id:[1-9][0-9]*", field):
                        self.transport = field.split(":")[1]
                        return
        raise ValueError("Selected device is offline, unauthorized or missing a transport ID")

    def call(self, *args):
        return command([*self.server, "-t", self.transport, *args]).stdout

    def identity(self):
        if self.call("get-serialno").decode().strip() != self.serial:
            raise ValueError("ADB transport now identifies a different device")
        value = self.call("shell", "settings", "get", "secure", "android_id").strip()
        if not re.fullmatch(rb"[0-9a-fA-F]{16}", value):
            raise ValueError("Cannot identify this Android installation")
        return hashlib.sha256(value.lower()).hexdigest()

    def inspect(self):
        release = self.call("shell", "getprop", "ro.build.version.release").decode().strip()
        abis = self.call("shell", "getprop", "ro.product.cpu.abilist").decode().strip().split(",")
        package = self.call("shell", "dumpsys", "package", PACKAGE).decode(errors="replace")
        if "arm64-v8a" not in abis:
            raise ValueError("The selected device does not advertise arm64-v8a")
        if not re.search(r"\bversionName=3\.57\.0\b(?=\s|$)", package) or not re.search(
            r"\bversionCode=431(?=\s|$)", package
        ):
            raise ValueError("Install the European Google Play build 3.57.0/431 on this device")
        return release

    def mappings(self):
        pairs = {}
        for line in self.call("reverse", "--list").decode().splitlines():
            if line.strip():
                _, source, target = line.split()
                pairs[source] = target
        return pairs

    def check_health(self):
        response = self.call(
            "exec-out",
            r"printf 'GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n' | toybox nc -w 5 127.0.0.1 17657",
        )
        header, _, body = response.partition(b"\r\n\r\n")
        if not re.match(rb"HTTP/1\.[01] 200\b", header) or (
            json.loads(body).get("service") != "Guardian Tales 3.57.0 local"
        ):
            raise ValueError(
                "Android could not verify the backend through its loopback health port"
            )


def port_pairs(cdn_port):
    return {10100: 10100, 10500: 10500, 17657: 17657, 18080: cdn_port}


class ForwardSession:
    def __init__(self, directory, device):
        self.path = directory / "mac-forward.json"
        self.device = device
        self.identity = None

    def save(self, record):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def start(self, cdn_port):
        if self.path.exists():
            raise ValueError("Restore the previous Mac forwarding session first")
        ports = port_pairs(cdn_port)
        existing = self.device.mappings()
        if any(f"tcp:{port}" in existing for port in ports):
            raise ValueError("A requested Android port is already forwarded")
        self.identity = self.device.identity()
        record = {
            "serial": self.device.serial,
            "device": self.identity,
            "cdn_port": cdn_port,
            "ports": [],
        }
        self.save(record)
        try:
            for source, target in ports.items():
                record["ports"].append(source)
                self.save(record)
                try:
                    self.device.call("reverse", "--no-rebind", f"tcp:{source}", f"tcp:{target}")
                except RuntimeError as error:
                    if "rebind" in str(error).lower() or "already" in str(error).lower():
                        record["ports"].pop()
                        self.save(record)
                    raise
            self.device.check_health()
        except BaseException:
            self.restore()
            raise

    def restore(self):
        if not self.path.exists():
            return
        record = json.loads(self.path.read_text(encoding="utf-8"))
        if record["serial"] != self.device.serial or record["device"] != self.device.identity():
            raise ValueError("This forwarding session belongs to a different Android installation")
        cdn = record["cdn_port"]
        if type(cdn) is not int or not 1 <= cdn <= 65535:
            raise ValueError("Invalid saved CDN port")
        ports = port_pairs(cdn)
        if not isinstance(record["ports"], list) or any(
            type(p) is not int or p not in ports for p in record["ports"]
        ):
            raise ValueError("Invalid saved Android ports")
        changed = []
        for port in reversed(record["ports"][:]):
            source = f"tcp:{port}"
            existing = self.device.mappings()
            if source in existing:
                if existing[source] != f"tcp:{ports[port]}":
                    changed.append(source)
                    continue
                self.device.call("reverse", "--remove", source)
            record["ports"].remove(port)
            self.save(record)
        if changed:
            raise ValueError(
                f"Forwarding targets changed for {', '.join(changed)}; record retained"
            )
        self.path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="guardian_tales android-bridge mac", description=__doc__)
    parser.add_argument("action", choices=("check", "run", "restore"))
    parser.add_argument("--serial", required=True, type=local_serial)
    parser.add_argument("--adb", type=Path, help="Path to the Mac adb executable")
    parser.add_argument("--session-dir", type=Path, default=Path("local/mac-android-bridge"))
    parser.add_argument("--cert-dir", type=Path, default=Path("local/client-tls"))
    parser.add_argument("--cdn-port", type=int, default=18081)
    parser.add_argument("--minutes", type=float, default=500)
    args = parser.parse_args(argv)
    if not 1 <= args.cdn_port <= 65535 or not 0 < args.minutes <= 500:
        parser.error("Use a valid CDN port and a duration greater than zero, up to 500 minutes")
    try:
        device = LocalDevice(adb_executable(args.adb), args.serial)
        if args.action == "check":
            device.identity()
            release = device.inspect()
            device.mappings()
            print(f"ADB CHECK PASSED: {args.serial}, Android {release}, ARM64, game 3.57.0/431.")
            return
        args.session_dir.mkdir(parents=True, exist_ok=True)
        with StateLock(args.session_dir):
            session = ForwardSession(args.session_dir, device)
            if args.action == "restore":
                session.restore()
            else:
                device.inspect()
                preflight(args.cert_dir, args.cdn_port)
                session.start(args.cdn_port)
                try:
                    print("LOCAL PORTS READY: Android verified the local backend.", flush=True)
                    deadline = time.monotonic() + args.minutes * 60
                    while time.monotonic() < deadline:
                        time.sleep(min(3, max(0, deadline - time.monotonic())))
                        if device.identity() != session.identity:
                            raise ValueError("The selected Android installation changed")
                except KeyboardInterrupt:
                    pass
                finally:
                    session.restore()
            print("LOCAL PORTS INACTIVE.")
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
