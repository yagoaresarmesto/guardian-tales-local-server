# SPDX-License-Identifier: Apache-2.0
"""Generate a new local-only TLS certificate using an installed OpenSSL CLI."""

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("local/tls"))
    parser.add_argument("--openssl", help="Path to an OpenSSL executable")
    args = parser.parse_args()
    executable = args.openssl or shutil.which("openssl")
    git_openssl = (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/openssl.exe"
    )
    if not executable and git_openssl.is_file():
        executable = str(git_openssl)
    if not executable:
        parser.error(
            "OpenSSL is required for certificate generation. Install it or pass --openssl PATH."
        )
    output = args.output.resolve()
    cert, key = output / "localhost-cert.pem", output / "localhost-key.pem"
    if cert.exists() or key.exists():
        parser.error(
            "Certificate files already exist. Use another --output directory to generate a replacement."
        )
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gt-cert-", dir=output) as temporary:
        temporary = Path(temporary)
        command = [
            executable,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-days",
            "30",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout",
            str(temporary / key.name),
            "-out",
            str(temporary / cert.name),
        ]
        subprocess.run(
            command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30
        )
        with key.open("xb") as target:
            target.write((temporary / key.name).read_bytes())
        key.chmod(0o600)
        with cert.open("xb") as target:
            target.write((temporary / cert.name).read_bytes())
    print(f"Created development TLS files in {output}")
    print("No certificate was installed in the operating system or an emulator.")


if __name__ == "__main__":
    main()
