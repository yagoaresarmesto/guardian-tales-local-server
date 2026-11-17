# SPDX-License-Identifier: Apache-2.0
"""Build and import versioned content releases without player state or credentials."""

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

from .assets import ResourceLibrary

FORMAT = "guardian-tales-content-v1"
MAX_PART_BYTES = 1_900_000_000
MAX_EXPANDED_BYTES = 64 * 1024**3
INITIAL_ZIP = "master-global-v3.57.0.Android.zip"
REFERENCES = (
    "resource_urls.bin",
    "product_ids.bin",
    "static_data_get.bin",
    "static_data_check.bin",
    "attendance_catalog.json",
    "beginner_mission_catalog.json",
    "challenge_mission_catalog.json",
    "completion_catalog.json",
    "festival_shop_catalog.json",
    "hero_knowledge_catalog.json",
    "monster_catalog.json",
    "quest_catalog.json",
    "stamina_purchase_catalog.json",
    "story_catalog.json",
    "substage_catalog.json",
    "summon_draw_catalog.json",
    "summon_selection_catalog.json",
    "training_catalog.json",
    "tutorial_catalog.json",
)
CORE_REFERENCES = set(REFERENCES[:4])
RESOURCE_PREFIXES = (
    "AssetBundles/",
    "Assets/",
    "GameScript/",
    "Tilemaps/",
    "events/",
    "media/",
    "static_data/",
)


def safe_name(name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or ":" in name
        or any(part in ("", ".", "..") for part in name.split("/"))
        or any(
            part.lower().startswith(("kpuser", ".env")) or "playerprefs" in part.lower()
            for part in name.split("/")
        )
        or Path(name).suffix.lower()
        in (".sqlite", ".sqlite3", ".db", ".pem", ".key", ".apk", ".so", ".pfx", ".p12")
        or name.lower().endswith((".db-wal", ".db-shm", ".sqlite3-wal", ".sqlite3-shm"))
    ):
        raise ValueError("Unsafe or private content member")
    return name


def resource_name(name):
    safe_name(name)
    base = name.removesuffix(".etag")
    if not name.startswith(RESOURCE_PREFIXES) and base not in (
        "Android.index",
        "assetbundle-version",
        "patch-index",
        INITIAL_ZIP,
    ):
        raise ValueError("File is outside the distributable resource paths")
    return name


def payload_name(name):
    safe_name(name)
    if name.startswith("reference/") and name[10:] in REFERENCES:
        return name
    if name.startswith("resources/files/"):
        resource_name(name[16:])
        return name
    raise ValueError("Content payload must contain whitelisted reference/resource files only")


def metadata(path):
    with Path(path).open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"bytes": Path(path).stat().st_size, "sha256": digest}


def validate_metadata(value):
    if (
        not isinstance(value, dict)
        or type(value.get("bytes")) is not int
        or not 0 <= value["bytes"] <= MAX_EXPANDED_BYTES
        or not isinstance(value.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
    ):
        raise ValueError("Invalid content size or SHA-256 metadata")


def new_directory(path):
    path = Path(path).resolve()
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(
            "Use a new or empty output directory; existing saves/data are never overwritten"
        )
    return path


def zip_members(archive):
    seen = set()
    for member in archive.infolist():
        if member.is_dir():
            continue
        safe_name(member.filename)
        if (
            member.filename in seen
            or stat.S_ISLNK(member.external_attr >> 16)
            or member.flag_bits & 1
        ):
            raise ValueError("Duplicate, symbolic-link or encrypted ZIP member")
        seen.add(member.filename)
        yield member


def build(reference_dir, resource_roots, output, content_id):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,100}", content_id):
        raise ValueError("Invalid content identifier")
    output = new_directory(output)
    references = Path(reference_dir).resolve()
    roots = [Path(root).resolve() for root in resource_roots]
    if output.is_relative_to(references) or any(output.is_relative_to(root) for root in roots):
        raise ValueError("Build output must be outside its input directories")
    sources = {}
    ref_metadata = {}
    for name in REFERENCES:
        source = references / name
        if source.is_file():
            ref_metadata[name] = metadata(source)
            sources["reference/" + name] = source
    if not CORE_REFERENCES.issubset(ref_metadata):
        raise ValueError("All four core bootstrap reference bodies are required")
    library = ResourceLibrary(roots)
    resources = {}
    resource_sources = {}
    for name, (source, digest) in library.files.items():
        try:
            resource_name(name)
        except ValueError:
            continue
        record = {"bytes": source.stat().st_size, "sha256": digest}
        validate_metadata(record)
        resources[name] = record
        resource_sources[name] = source
    if INITIAL_ZIP not in resources:
        raise ValueError("The initial Android ZIP must be available in a resource root")
    expansions = []
    covered = set()
    for name, source in sorted(resource_sources.items()):
        prefix = None
        if name == INITIAL_ZIP:
            prefix = ""
        elif name.startswith("AssetBundles/Android/ondemand/") and name.endswith(".zip"):
            prefix = "AssetBundles/Android/ondemand/"
        if prefix is None:
            continue
        with zipfile.ZipFile(source) as archive:
            for member in zip_members(archive):
                target = resource_name(prefix + member.filename)
                if (
                    target in covered
                    or target not in resources
                    or resources[target]["bytes"] != member.file_size
                ):
                    raise ValueError("Expanded ZIP members must uniquely match preserved resources")
                covered.add(target)
        expansions.append({"path": "resources/files/" + name, "prefix": prefix})
    for name, source in resource_sources.items():
        if name not in covered:
            sources["resources/files/" + name] = source
    payload = {
        name: metadata(path) if name.startswith("reference/") else resources[name[16:]]
        for name, path in sources.items()
    }
    bins = []
    for name in sorted(payload, key=lambda key: payload[key]["bytes"], reverse=True):
        estimated = payload[name]["bytes"] + 512 + 2 * len(name.encode())
        if estimated + 22 > MAX_PART_BYTES:
            raise ValueError("A payload file exceeds the release part limit")
        for bucket in bins:
            if bucket[0] + estimated <= MAX_PART_BYTES:
                bucket[0] += estimated
                bucket[1].append(name)
                break
        else:
            bins.append([22 + estimated, [name]])
    output.mkdir(parents=True, exist_ok=True)
    parts = []
    for number, (_, names) in enumerate(bins, 1):
        name = f"{content_id}-part{number:02d}.zip"
        path = output / name
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_STORED) as archive:
            for member in sorted(names):
                archive.write(sources[member], member)
        record = metadata(path)
        if record["bytes"] >= 2 * 1024**3:
            raise ValueError("A generated part exceeds the GitHub Release asset limit")
        parts.append({"name": name, **record})
    manifest = {
        "format": FORMAT,
        "content_id": content_id,
        "client": {"version": "3.57.0", "market": "googleplay", "region": "Europe"},
        "parts": parts,
        "payload": payload,
        "resources": resources,
        "references": ref_metadata,
        "expand": expansions,
    }
    (output / "content-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def load_manifest(path):
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT or manifest.get("client", {}).get("version") != "3.57.0":
        raise ValueError("Unsupported content manifest or client version")
    for section in ("payload", "resources", "references"):
        if not isinstance(manifest.get(section), dict) or not manifest[section]:
            raise ValueError("Missing content manifest section")
        for name, record in manifest[section].items():
            if section == "payload":
                payload_name(name)
            elif section == "resources":
                resource_name(name)
            elif name not in REFERENCES:
                raise ValueError("Unexpected reference file")
            validate_metadata(record)
    if not CORE_REFERENCES.issubset(manifest["references"]):
        raise ValueError("Core bootstrap references are missing")
    if (
        sum(r["bytes"] for section in ("payload", "resources") for r in manifest[section].values())
        > MAX_EXPANDED_BYTES
    ):
        raise ValueError("Content exceeds the import size limit")
    return manifest


def copy_verified(source, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with target.open("xb") as output:
        while block := source.read(1024 * 1024):
            count += len(block)
            if count > expected["bytes"]:
                raise ValueError("Content member exceeds its declared size")
            digest.update(block)
            output.write(block)
    if count != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise ValueError("Content member failed its size/SHA-256 verification")


def import_pack(manifest_path, output):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_manifest(manifest_path)
    output = new_directory(output)
    seen = set()
    part_names = set()
    for part in manifest["parts"]:
        name = safe_name(part["name"])
        if "/" in name or name in part_names:
            raise ValueError("Unsafe or duplicate release part name")
        part_names.add(name)
        validate_metadata(part)
        path = manifest_path.parent / name
        if metadata(path) != {k: part[k] for k in ("bytes", "sha256")}:
            raise ValueError("A release part failed SHA-256 verification")
        with zipfile.ZipFile(path) as archive:
            for member in zip_members(archive):
                payload_name(member.filename)
                if (
                    member.filename in seen
                    or member.filename not in manifest["payload"]
                    or member.file_size != manifest["payload"][member.filename]["bytes"]
                ):
                    raise ValueError("Unexpected or duplicate content payload member")
                seen.add(member.filename)
    if seen != set(manifest["payload"]):
        raise ValueError("Release parts do not contain the complete payload")
    output.mkdir(parents=True, exist_ok=True)
    for part in manifest["parts"]:
        with zipfile.ZipFile(manifest_path.parent / part["name"]) as archive:
            for member in zip_members(archive):
                with archive.open(member) as source:
                    copy_verified(
                        source, output / member.filename, manifest["payload"][member.filename]
                    )
    for rule in manifest["expand"]:
        payload_name(rule["path"])
        if rule["path"] not in manifest["payload"] or rule["prefix"] not in (
            "",
            "AssetBundles/Android/ondemand/",
        ):
            raise ValueError("Invalid nested archive rule")
        with zipfile.ZipFile(output / rule["path"]) as archive:
            for member in zip_members(archive):
                name = resource_name(rule["prefix"] + member.filename)
                if name not in manifest["resources"]:
                    raise ValueError("Unexpected expanded resource")
                with archive.open(member) as source:
                    copy_verified(
                        source, output / "resources/files" / name, manifest["resources"][name]
                    )
    result = check(output, manifest)
    rows = [
        {"path": "resources/files/" + name, **record}
        for name, record in manifest["resources"].items()
    ]
    (output / "manifest.json").write_text(
        json.dumps({"files": rows}, indent=2) + "\n", encoding="utf-8"
    )
    (output / "content-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (output / "import-report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def check(output, manifest=None):
    output = Path(output).resolve()
    manifest = manifest or load_manifest(output / "content-manifest.json")
    for prefix, section in (("resources/files/", "resources"), ("reference/", "references")):
        for name, expected in manifest[section].items():
            path = output / (prefix + name)
            if (
                not path.is_file()
                or path.is_symlink()
                or not path.resolve().is_relative_to(output)
                or metadata(path) != expected
            ):
                raise ValueError(
                    "Imported content is missing or differs from its manifest: " + prefix + name
                )
    return {
        "result": "PASS",
        "content_id": manifest["content_id"],
        "resource_files": len(manifest["resources"]),
        "reference_files": len(manifest["references"]),
        "scope": "Imported data hashes; APK routing, TLS trust and gameplay are separate",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("build")
    prepare.add_argument("--reference-dir", type=Path, required=True)
    prepare.add_argument("--resource-root", type=Path, action="append", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--content-id", required=True)
    install = commands.add_parser("import")
    install.add_argument("--manifest", type=Path, required=True)
    install.add_argument("--output", type=Path, default=Path("local/client-data"))
    verify = commands.add_parser("check")
    verify.add_argument("--data-dir", type=Path, default=Path("local/client-data"))
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(args.reference_dir, args.resource_root, args.output, args.content_id)
            result = {
                "content_id": result["content_id"],
                "parts": result["parts"],
                "resource_files": len(result["resources"]),
            }
        elif args.command == "import":
            result = import_pack(args.manifest, args.output)
        else:
            result = check(args.data_dir)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(1, "Content preparation failed: " + str(error) + "\n")
    print(json.dumps(result, indent=2))
