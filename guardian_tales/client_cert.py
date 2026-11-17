# SPDX-License-Identifier: Apache-2.0
"""Generate a private development CA and a certificate for the pinned client."""

import argparse
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

HOSTS = ("localhost", "eu-api.live.guardiantales.com", "eu-auth.live.guardiantales.com")


def openssl_path(override=None):
    executable = override or shutil.which("openssl")
    bundled = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/openssl.exe"
    if not executable and bundled.is_file():
        executable = str(bundled)
    if not executable:
        raise ValueError("OpenSSL is required; install it or pass --openssl PATH")
    return executable


def generate(directory, executable=None):
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(
            "Use a new or empty certificate directory; existing keys are never replaced"
        )
    executable = openssl_path(executable)
    directory.mkdir(parents=True, exist_ok=True)

    def run(*args):
        result = subprocess.run(
            [executable, *args], cwd=directory, capture_output=True, timeout=30, check=True
        )
        return result.stdout.decode().strip()

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
    run(
        "x509",
        "-req",
        "-in",
        "server.csr",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca-key.pem",
        "-CAcreateserial",
        "-days",
        "7",
        "-sha256",
        "-extfile",
        "server.ext",
        "-out",
        "localhost-cert.pem",
    )
    ca = (directory / "ca.pem").read_bytes()
    with (directory / "localhost-cert.pem").open("ab") as output:
        output.write(ca)
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
