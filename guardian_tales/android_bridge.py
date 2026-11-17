# SPDX-License-Identifier: Apache-2.0
"""Reversible local routing for a dedicated MuMu 12 / Android 12 test instance."""

import argparse
import hashlib
import json
import os
import re
import shlex
import socket
import ssl
import subprocess
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from .client_cert import HOSTS
from .state_lock import StateLock

PACKAGE = "com.kakaogames.gdts"
CERTS = "/system/etc/security/cacerts"
HOSTS_FILE = "/system/etc/hosts"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(args, check=True):
    result = subprocess.run(args, capture_output=True, timeout=30)
    if check and result.returncode:
        raise RuntimeError(
            Path(str(args[0])).name + ": " + result.stderr.decode(errors="replace")[:300]
        )
    return result


def identity(info, index, name):
    if (
        index < 1
        or str(info.get("index")) != str(index)
        or info.get("name") != name
        or info.get("is_main")
        or type(info.get("created_timestamp")) is not int
    ):
        raise ValueError("Instance identity mismatch; use a dedicated non-main test instance")
    return (str(index), name, info["created_timestamp"])


def serial(info):
    port = info.get("adb_port")
    if not info.get("is_android_started") or info.get("adb_host_ip") != "127.0.0.1":
        raise ValueError("Start the selected Android instance first")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Invalid MuMu ADB port")
    return "127.0.0.1:" + str(port)


def staging_path(value):
    if not re.fullmatch(r"/data/local/tmp/gt357bridge_[0-9a-f]{16}", value):
        raise ValueError("Invalid bridge staging path")
    return value


def local_hosts(original):
    for row in original.decode("utf-8").splitlines():
        if set(row.split("#", 1)[0].split()[1:]).intersection(HOSTS[1:]):
            raise ValueError(
                "Hosts already contain a game hostname; restore the previous routing first"
            )
    return (
        original.rstrip(b"\n")
        + b"\n# Guardian Tales local development\n"
        + b"".join(b"127.0.0.1 " + host.encode() + b"\n" for host in HOSTS if host != "localhost")
    )


class Device:
    def __init__(self, cli, index, name):
        self.cli = str(Path(cli).resolve())
        self.adb_path = str(Path(self.cli).with_name("adb.exe"))
        self.index, self.name = index, name
        self.expected = identity(self.info(), index, name)

    def info(self):
        value = json.loads(command([self.cli, "info", "--vmindex", str(self.index)]).stdout)
        return value.get(str(self.index), value)

    def check(self):
        info = self.info()
        if identity(info, self.index, self.name) != self.expected:
            raise ValueError("The emulator was replaced; refusing to address it")
        return info

    def adb(self, *args, check=True):
        return command([self.adb_path, "-s", serial(self.check()), *args], check).stdout

    def root(self, value):
        return self.adb("exec-out", "su -c " + shlex.quote(value))

    def set_root(self, enabled):
        self.check()
        command(
            [
                self.cli,
                "setting",
                "--vmindex",
                str(self.index),
                "--key",
                "root_permission",
                "--value",
                "true" if enabled else "false",
            ]
        )


def preflight(directory, cdn_port):
    directory = Path(directory)
    ca_files = list(directory.glob("*.0"))
    if len(ca_files) != 1 or not re.fullmatch(r"[0-9a-f]{8}\.0", ca_files[0].name):
        raise ValueError("Generate client-cert files first; exactly one hashed CA is required")
    if ca_files[0].read_bytes() != (directory / "ca.pem").read_bytes():
        raise ValueError("Hashed Android CA differs from ca.pem")
    leaf = (directory / "localhost-cert.pem").read_text().split("-----END CERTIFICATE-----", 1)[0]
    expected = ssl.PEM_cert_to_DER_cert(leaf + "-----END CERTIFICATE-----\n")
    context = ssl.create_default_context(cafile=str(directory / "ca.pem"))
    for port, host in ((10100, HOSTS[1]), (10500, HOSTS[2])):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as transport:
            with context.wrap_socket(transport, server_hostname=host) as connection:
                if connection.getpeercert(binary_form=True) != expected:
                    raise ValueError(
                        "Received a substituted certificate; check local TLS inspection"
                    )
    with urlopen("http://127.0.0.1:17657/health", timeout=5) as response:
        if json.load(response).get("service") != "Guardian Tales 3.57.0 local":
            raise ValueError("The local backend is not ready")
    request = Request(
        f"http://127.0.0.1:{cdn_port}/master-global-v3.57.0/Android.index", method="HEAD"
    )
    with urlopen(request, timeout=5) as response:
        if response.status != 200 or int(response.headers["Content-Length"]) <= 0:
            raise ValueError("The resource CDN is not ready")
    return ca_files[0]


class Bridge:
    def __init__(self, device, directory, cert_dir, cdn_port):
        self.device = device
        self.directory = Path(directory).resolve()
        self.cert_dir = Path(cert_dir).resolve()
        self.cdn_port = cdn_port
        self.state = self.directory / "session.json"
        self.record = json.loads(self.state.read_text()) if self.state.exists() else {}

    def save(self):
        temporary = self.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.state)

    def root_listing(self):
        return digest(
            b"\n".join(
                sorted(
                    self.device.root("find " + CERTS + " -type f -exec sha256sum {} +").splitlines()
                )
            )
        )

    def start(self):
        if self.record.get("active"):
            raise ValueError("A previous bridge needs restoration; use android-bridge restore")
        ca = preflight(self.cert_dir, self.cdn_port)
        d = self.device
        d.check()
        command([d.adb_path, "connect", serial(d.info())])
        if d.adb("shell", "getprop", "ro.build.version.release").strip() != b"12":
            raise ValueError("This bridge currently supports Android 12 only")
        package = d.adb("shell", "dumpsys", "package", PACKAGE).decode(errors="replace")
        if not re.search(r"versionName=3\.57\.0\s", package):
            raise ValueError("Install the matching Guardian Tales 3.57.0 APK first")
        mappings = d.adb("reverse", "--list").decode().split()
        if any("tcp:" + str(port) in mappings for port in (10100, 10500, 17657, 18080)):
            raise ValueError("Required Android reverse ports are already in use")
        rooted = b"uid=0" in d.adb("exec-out", "su -c id", check=False)
        base = staging_path("/data/local/tmp/gt357bridge_" + uuid.uuid4().hex[:16])
        self.record = {
            "active": True,
            "identity": list(d.expected),
            "root_was_enabled": rooted,
            "base": base,
            "chain": "GT357_" + base.rsplit("_", 1)[1],
            "reverse_ports": [],
            "cdn_port": self.cdn_port,
        }
        self.save()
        d.set_root(True)
        if b"uid=0" not in d.root("id"):
            raise ValueError("MuMu did not enable root access")
        d.adb("shell", "am", "force-stop", PACKAGE)
        mounts = d.root("cat /proc/mounts").decode().splitlines()
        if any(row.split()[1] in (HOSTS_FILE, CERTS) for row in mounts):
            raise ValueError("Hosts/trust already have an overlay; restore the other lab first")
        original = d.root("cat " + HOSTS_FILE)
        self.record.update(hosts_sha256=digest(original), certs_sha256=self.root_listing())
        for program in ("iptables", "ip6tables"):
            self.record[program + "_output_sha256"] = digest(d.root(program + " -S OUTPUT"))
        self.save()
        d.root("mkdir -p " + base)
        (self.directory / "hosts.original").write_bytes(original)
        (self.directory / "hosts.local").write_bytes(local_hosts(original))
        d.adb("push", str(self.directory / "hosts.local"), base + "/hosts")
        d.adb("push", str(ca), base + "/ca.pem")
        d.root("cp -a " + CERTS + " " + base + "/cacerts")
        d.root("test ! -e " + base + "/cacerts/" + ca.name)
        d.root("cp " + base + "/ca.pem " + base + "/cacerts/" + ca.name)
        d.root("chmod 644 " + base + "/hosts " + base + "/cacerts/" + ca.name)
        d.root("chcon -R u:object_r:system_file:s0 " + base + "/cacerts")
        self.record["overlays_started"] = True
        self.save()
        d.root("mount --bind " + base + "/hosts " + HOSTS_FILE)
        d.root("mount --bind " + base + "/cacerts " + CERTS)
        if d.root("cat " + HOSTS_FILE) != local_hosts(original):
            raise ValueError("Hosts overlay did not take effect")
        for port, target in (
            (10100, 10100),
            (10500, 10500),
            (17657, 17657),
            (18080, self.cdn_port),
        ):
            self.record["reverse_ports"].append(port)
            self.save()
            d.adb("reverse", "tcp:" + str(port), "tcp:" + str(target))
        self.record["network_started"] = True
        self.save()
        chain = self.record["chain"]
        for program in ("iptables", "ip6tables"):
            d.root(program + " -N " + chain)
            d.root(program + " -A " + chain + " -o lo -j RETURN")
            if program == "iptables":
                d.root(program + " -A " + chain + " -p tcp --sport 5555 -d 10.0.2.2 -j RETURN")
            d.root(program + " -A " + chain + " -j REJECT")
            d.root(program + " -I OUTPUT 1 -j " + chain)
        self.record["ready"] = True
        self.save()

    def restore(self):
        if not self.record.get("active"):
            return
        d = self.device
        info = d.check()
        if list(d.expected) != self.record["identity"]:
            raise ValueError("Session belongs to a different emulator")
        base = staging_path(self.record["base"])
        chain = self.record["chain"]
        if chain != "GT357_" + base.rsplit("_", 1)[1]:
            raise ValueError("Invalid saved firewall chain")
        if any(
            type(port) is not int or port not in (10100, 10500, 17657, 18080)
            for port in self.record["reverse_ports"]
        ):
            raise ValueError("Invalid saved reverse port")
        if type(self.record["root_was_enabled"]) is not bool:
            raise ValueError("Invalid saved root setting")
        if not info.get("is_android_started"):
            d.set_root(self.record["root_was_enabled"])
            self.record.update(
                active=False,
                ready=False,
                restoration="Transient overlays ended with emulator shutdown",
            )
            self.save()
            return
        d.set_root(True)
        d.adb("shell", "am", "force-stop", PACKAGE)
        errors = []

        def attempt(function):
            try:
                function()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                errors.append(str(error))

        def firewall(program):
            rules = d.root(program + " -S").decode()
            if "-A OUTPUT -j " + chain in rules:
                d.root(program + " -D OUTPUT -j " + chain)
            if "-N " + chain in rules:
                d.root(program + " -F " + chain)
                d.root(program + " -X " + chain)
            expected = self.record.get(program + "_output_sha256")
            if expected and digest(d.root(program + " -S OUTPUT")) != expected:
                raise ValueError("OUTPUT rules differ from their initial state: " + program)

        if self.record.get("network_started"):
            for program in ("iptables", "ip6tables"):
                attempt(lambda program=program: firewall(program))
        if self.record.get("overlays_started"):
            for target in (HOSTS_FILE, CERTS):

                def unmount(target=target):
                    rows = d.root("cat /proc/mounts").decode().splitlines()
                    if any(row.split()[1] == target for row in rows):
                        d.root("umount " + target)

                attempt(unmount)

        def remove_reverse(port):
            source = "tcp:" + str(port)
            target = "tcp:" + str(self.record["cdn_port"] if port == 18080 else port)
            for row in d.adb("reverse", "--list").decode().splitlines():
                endpoints = [part for part in row.split() if part.startswith("tcp:")]
                if endpoints and endpoints[0] == source:
                    if endpoints != [source, target]:
                        raise ValueError("Reverse mapping changed independently: " + source)
                    d.adb("reverse", "--remove", source)

        for port in self.record["reverse_ports"]:
            attempt(lambda port=port: remove_reverse(port))
        if "hosts_sha256" in self.record:

            def check_originals():
                if digest(d.root("cat " + HOSTS_FILE)) != self.record["hosts_sha256"]:
                    raise ValueError("Original hosts hash differs")
                if self.root_listing() != self.record["certs_sha256"]:
                    raise ValueError("Original trust-store listing differs")

            attempt(check_originals)
        if not errors:
            # Only remove this generated, validated staging directory after unmounting.
            attempt(lambda: d.root("rm -rf " + staging_path(base)))
        attempt(lambda: d.set_root(self.record["root_was_enabled"]))
        self.record.update(active=bool(errors), ready=False, restoration_errors=errors)
        self.save()
        if errors:
            raise RuntimeError("Bridge restoration needs attention: " + "; ".join(errors))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "restore"))
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--mumu-cli",
        type=Path,
        default=Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Netease/MuMuPlayerGlobal-12.0/nx_main/mumu-cli.exe",
    )
    parser.add_argument("--cert-dir", type=Path, default=Path("local/client-tls"))
    parser.add_argument("--session-dir", type=Path, default=Path("local/android-bridge"))
    parser.add_argument("--cdn-port", type=int, default=18080)
    parser.add_argument("--minutes", type=float, default=500)
    args = parser.parse_args(argv)
    if not 1 <= args.cdn_port <= 65535 or not 0 < args.minutes <= 500:
        parser.error("Use a valid CDN port and a duration greater than zero, up to 500 minutes")
    directory = args.session_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    bridge = None
    try:
        with StateLock(directory):
            bridge = Bridge(
                Device(args.mumu_cli, args.index, args.name),
                directory,
                args.cert_dir,
                args.cdn_port,
            )
            if args.action == "restore":
                bridge.restore()
                print("Bridge restored; host backend/CDN and saved account retained.")
                return
            if bridge.record.get("active"):
                raise ValueError(
                    "A previous bridge needs restoration; use the restore action first"
                )
            try:
                bridge.start()
                print("BRIDGE READY: open the game and choose Login as Guest.", flush=True)
                print(
                    "External instance traffic is blocked. Ctrl+C restores routing/trust; closing MuMu also ends this bridge.",
                    flush=True,
                )
                deadline = time.monotonic() + args.minutes * 60
                while time.monotonic() < deadline and bridge.device.check().get(
                    "is_process_started"
                ):
                    time.sleep(3)
            finally:
                bridge.restore()
                print("BRIDGE INACTIVE: temporary routing and trust removed.", flush=True)
    except KeyboardInterrupt:
        print("Bridge stopped and restored.")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
