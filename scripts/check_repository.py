# SPDX-License-Identifier: Apache-2.0
"""Check indexed source paths, obvious private artifacts and local doc links."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".apk",
    ".so",
    ".pyc",
    ".zip",
}
FORBIDDEN_PARTS = {
    "local",
    "work",
    "outputs",
    "__pycache__",
    ".venv",
    "dist",
    "build",
    "routing_private",
    "lab_tls",
}
PRIVATE_KEY = re.compile(rb"-----BEGIN (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----")
PERSONAL_PATH = re.compile(rb"(?:[A-Za-z]:[\\/]Users[\\/]|/Users/|/home/)[A-Za-z0-9_.-]+[\\/]")


def check_repository():
    raw = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=REPO)
    paths = sorted(set(x.decode("utf-8") for x in raw.split(b"\0") if x))
    if not paths:
        raise RuntimeError("No indexed files. Run git add . before checking or packaging.")
    problems = []
    for relative in paths:
        path = REPO / relative
        if path.is_symlink() or not path.resolve().is_relative_to(REPO):
            problems.append(f"Non-local source path: {relative}")
            continue
        if not path.is_file():
            problems.append(f"Indexed file is missing: {relative}")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or FORBIDDEN_PARTS.intersection(
            Path(relative).parts
        ):
            problems.append(f"Private or generated artifact path: {relative}")
        if path.suffix == ".bin" and relative != "tests/fixtures/pong_real.bin":
            problems.append(f"Unexpected binary response/capture: {relative}")
        if path.name.startswith(("KpUser", ".env")) or path.name == "global-metadata.dat":
            problems.append(f"Local-only input path: {relative}")
        data = path.read_bytes()
        if PRIVATE_KEY.search(data) or PERSONAL_PATH.search(data):
            problems.append(f"Private key or personal absolute path in: {relative}")
        if path.suffix == ".md":
            for link in re.findall(r"(?<!!)\[[^\]]*\]\(([^\s)]+)\)", data.decode("utf-8")):
                if link.startswith(("https://", "http://", "mailto:", "#")):
                    continue
                target = path.parent / unquote(link.split("#", 1)[0])
                if not target.exists():
                    problems.append(f"Broken local link in {relative}: {link}")
    if problems:
        raise RuntimeError("\n".join(problems))
    return paths


def main():
    paths = check_repository()
    print(
        json.dumps(
            dict(
                result="PASS",
                indexed_source_files=len(paths),
                scope="Indexed artifact paths, private-key/personal-path patterns and local Markdown links",
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
