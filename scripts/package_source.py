# SPDX-License-Identifier: Apache-2.0
"""Create and verify a source ZIP from the repository's indexed file list."""

import argparse
import hashlib
import zipfile
from pathlib import Path

from check_repository import REPO, check_repository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=REPO / "dist/guardian-tales-local-server.zip"
    )
    args = parser.parse_args()
    files = check_repository()
    archive = args.output.resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for relative in files:
            output.write(REPO / relative, "guardian-tales-local-server/" + relative)
    with zipfile.ZipFile(archive) as output:
        assert output.testzip() is None
        for relative in files:
            assert (
                output.read("guardian-tales-local-server/" + relative)
                == (REPO / relative).read_bytes()
            )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_name(archive.name + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Created and verified {archive} ({len(files)} source files)")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
