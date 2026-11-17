# SPDX-License-Identifier: Apache-2.0
"""Build locally served on-demand ZIPs from external preservation manifests."""

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

PREFIX = "AssetBundles/Android/ondemand/"


def build_archives(resource_roots, output, groups=None):
    from guardian_tales.assets import ResourceLibrary

    roots = [Path(root).resolve() for root in resource_roots]
    output = Path(output).resolve()
    if any(output.is_relative_to(root) for root in roots):
        raise ValueError("Output must be outside the source resource directories")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be a new or empty directory")
    library = ResourceLibrary(roots)
    members = {}
    for name, (path, _) in library.files.items():
        if not name.startswith(PREFIX) or name.endswith(".etag"):
            continue
        relative = name[len(PREFIX) :]
        group, separator, _ = relative.partition("/")
        if not separator:
            continue
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,100}", group)
            or "\\" in relative
            or any(part in (".", "..", "") for part in relative.split("/"))
            or PurePosixPath(relative).is_absolute()
        ):
            raise ValueError("Unsafe on-demand archive member path")
        members.setdefault(group, {})[relative] = path
    selected = sorted(members if groups is None else set(groups))
    if not selected or any(group not in members for group in selected):
        raise ValueError("Every requested group must have preserved files")
    rows = []
    report = []
    for group in selected:
        relative = PREFIX + group + ".zip"
        target = output / "resources/files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # The native extractor uses the on-demand directory as its destination.
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED) as archive:
            for name, source in sorted(members[group].items()):
                archive.write(source, name)
        with target.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        rows.append(
            {
                "path": "resources/files/" + relative,
                "bytes": target.stat().st_size,
                "sha256": checksum,
            }
        )
        report.append(
            {"group": group, "members": len(members[group]), "bytes": target.stat().st_size}
        )
    with (output / "manifest.json").open("x", encoding="utf-8") as target:
        json.dump({"files": rows}, target, indent=2)
        target.write("\n")
    return {
        "archives": report,
        "scope": "Available preserved files only; completeness is not inferred",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-root", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New or empty package directory")
    parser.add_argument(
        "--group", action="append", help="Group to package; default: all available groups"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        report = build_archives(args.resource_root, args.output, args.group)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
