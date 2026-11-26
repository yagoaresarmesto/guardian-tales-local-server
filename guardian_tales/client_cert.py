# SPDX-License-Identifier: Apache-2.0
"""Generate a private development CA and a certificate for the pinned client."""

import argparse
import os
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .state_lock import StateLock

HOSTS = ("localhost", "eu-api.live.guardiantales.com", "eu-auth.live.guardiantales.com")
RENEW_BEFORE = 48 * 60 * 60
LEAF_DAYS = 7


def openssl_path(override=None):
    executable = override or shutil.which("openssl")
    bundled = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/openssl.exe"
    if not executable and bundled.is_file():
        executable = str(bundled)
    if not executable:
        raise ValueError("OpenSSL is required; install it or pass --openssl PATH")
    return executable


def _openssl(executable, directory, *args):
    result = subprocess.run(
        [executable, *args],
        cwd=directory,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "OpenSSL failed")
    return result.stdout.decode().strip()


def _issue_leaf(directory, executable, target):
    _openssl(
        executable,
        directory,
        "x509",
        "-req",
        "-in",
        "server.csr",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca-key.pem",
        "-set_serial",
        "0x" + secrets.token_hex(16),
        "-days",
        str(LEAF_DAYS),
        "-sha256",
        "-extfile",
        "server.ext",
        "-out",
        str(target),
    )
    with target.open("ab") as output:
        output.write((directory / "ca.pem").read_bytes())


def _expires_at(path):
    # CPython's OpenSSL decoder reads the first certificate of a PEM chain.
    return ssl.cert_time_to_seconds(ssl._ssl._test_decode_cert(str(path))["notAfter"])


def _server_context(leaf, key):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(leaf, key)
    return context


@contextmanager
def _renewal_lock(directory):
    # Independent game instances can share one TLS directory.
    lock = StateLock(directory, filename=".leaf-renewal.lock")
    deadline = time.monotonic() + 10
    while True:
        try:
            lock.acquire()
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Another backend is renewing the TLS certificate.") from None
            time.sleep(0.1)
    try:
        yield
    finally:
        lock.release()


def _renew_leaf(directory, leaf, key):
    executable = openssl_path()
    verify = ("verify", "-CAfile", "ca.pem", "-purpose", "sslserver")
    _openssl(executable, directory, *verify, "-no_check_time", str(leaf))
    with tempfile.TemporaryDirectory(prefix=".renew-", dir=directory) as tmp:
        candidate = Path(tmp) / leaf.name
        _issue_leaf(directory, executable, candidate)
        for host in HOSTS:
            _openssl(executable, directory, *verify, "-verify_hostname", host, str(candidate))
        _openssl(executable, directory, *verify, "-verify_ip", "127.0.0.1", str(candidate))
        _server_context(candidate, key)
        candidate.replace(leaf)


def prepare_server_tls(directory):
    """Load the configured chain; only a locally provisioned client CA can renew it."""
    directory = Path(directory).resolve()
    leaf, key = directory / "localhost-cert.pem", directory / "localhost-key.pem"
    ca = directory / "ca.pem"
    if not leaf.is_file():
        raise FileNotFoundError(leaf)
    expiry = _expires_at(leaf)
    try:
        ca_expiry = _expires_at(ca) if ca.is_file() else None
    except OSError as error:
        print(f"Could not read the TLS authority expiry: {error}", file=sys.stderr)
        ca_expiry = None

    def due(leaf_expiry):
        now = time.time()
        return (
            leaf_expiry - now < RENEW_BEFORE
            and ca_expiry is not None
            and ca_expiry > max(now, leaf_expiry)
        )

    if due(expiry) and all(
        (directory / f).is_file() for f in ("ca-key.pem", "server.csr", "server.ext")
    ):
        try:
            with _renewal_lock(directory):
                if due(_expires_at(leaf)):
                    _renew_leaf(directory, leaf, key)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            print(f"TLS certificate renewal failed: {error}", file=sys.stderr)
        expiry = _expires_at(leaf)

    return _server_context(leaf, key), {
        "server": datetime.fromtimestamp(expiry, timezone.utc).isoformat(),
        "authority": (
            datetime.fromtimestamp(ca_expiry, timezone.utc).isoformat()
            if ca_expiry is not None
            else None
        ),
    }


def generate(directory, executable=None):
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(
            "Use a new or empty certificate directory; existing keys are never replaced"
        )
    executable = openssl_path(executable)
    directory.mkdir(parents=True, exist_ok=True)

    def run(*args):
        return _openssl(executable, directory, *args)

    run(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-nodes",
        "-days",
        "30",
        "-subj",
        "/CN=Guardian Tales local CA " + uuid.uuid4().hex[:12],
        "-addext",
        "basicConstraints=critical,CA:TRUE,pathlen:0",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout",
        "ca-key.pem",
        "-out",
        "ca.pem",
    )
    run(
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-nodes",
        "-subj",
        "/CN=Guardian Tales local server",
        "-keyout",
        "localhost-key.pem",
        "-out",
        "server.csr",
    )
    (directory / "server.ext").write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=" + ",".join("DNS:" + host for host in HOSTS) + ",IP:127.0.0.1\n",
        encoding="ascii",
    )
    _issue_leaf(directory, executable, directory / "localhost-cert.pem")
    ca = (directory / "ca.pem").read_bytes()
    subject_hash = run("x509", "-in", "ca.pem", "-subject_hash_old", "-noout")
    if not re.fullmatch(r"[0-9a-f]{8}", subject_hash):
        raise ValueError("OpenSSL returned an invalid Android CA hash")
    (directory / (subject_hash + ".0")).write_bytes(ca)
    for name in ("ca-key.pem", "localhost-key.pem"):
        (directory / name).chmod(0o600)
    run("verify", "-CAfile", "ca.pem", "-purpose", "sslserver", "localhost-cert.pem")
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("local/client-tls"))
    parser.add_argument("--openssl")
    args = parser.parse_args(argv)
    try:
        directory = generate(args.output, args.openssl)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"Created client TLS files in {directory}")
    print("Leaf valid for seven days; CA valid for thirty days. No trust store was changed.")


if __name__ == "__main__":
    main()
