# SPDX-License-Identifier: Apache-2.0
"""Synthetic complete-content releases import safely without touching a save."""

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from guardian_tales.content_pack import CORE_REFERENCES, INITIAL_ZIP, build, check, import_pack


class ContentPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.reference = self.folder / "reference"
        self.reference.mkdir()
        for name in CORE_REFERENCES:
            (self.reference / name).write_bytes(b"synthetic reference " + name.encode())
        # An externally overridden player template must not enter a content release.
        (self.reference / "new_guest_profile.json").write_text('{"private": true}')
        self.root = self.folder / "preserved/resources/files"
        self.root.mkdir(parents=True)
        rows = []
        files = {
            "Android.index": b"synthetic index",
            "GameScript/demo.encrypted": b"script",
            "AssetBundles/Android/ondemand/demo/tiles": b"bundle",
            "media/demo.png": b"image",
            "KpUser.dat": b"excluded account",
            "il2cpp/global-metadata.dat": b"excluded metadata",
        }
        for name, data in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with zipfile.ZipFile(self.root / INITIAL_ZIP, "w") as archive:
            for name in ("Android.index", "GameScript/demo.encrypted"):
                archive.writestr(name, files[name])
        archive_path = self.root / "AssetBundles/Android/ondemand/demo.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("demo/tiles", files["AssetBundles/Android/ondemand/demo/tiles"])
        for path in self.root.rglob("*"):
            if path.is_file():
                rows.append(
                    {
                        "path": "resources/files/" + path.relative_to(self.root).as_posix(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        (self.root.parent.parent / "manifest.json").write_text(json.dumps({"files": rows}))
        self.release = self.folder / "release"

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        return build(self.reference, [self.root], self.release, "synthetic-content")

    def test_build_import_and_check_expand_archives_without_private_state(self):
        with patch("guardian_tales.content_pack.MAX_PART_BYTES", 1600):
            manifest = self.prepare()
        self.assertGreater(len(manifest["parts"]), 1)
        self.assertNotIn("reference/new_guest_profile.json", manifest["payload"])
        self.assertNotIn("KpUser.dat", manifest["resources"])
        self.assertNotIn("il2cpp/global-metadata.dat", manifest["resources"])
        self.assertNotIn("resources/files/GameScript/demo.encrypted", manifest["payload"])
        output = self.folder / "installed"
        report = import_pack(self.release / "content-manifest.json", output)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(check(output), report)
        self.assertEqual(
            (output / "resources/files/GameScript/demo.encrypted").read_bytes(), b"script"
        )
        self.assertEqual(
            (output / "resources/files/AssetBundles/Android/ondemand/demo/tiles").read_bytes(),
            b"bundle",
        )
        self.assertFalse((output / "state").exists())
        self.assertEqual(
            json.loads((output / "manifest.json").read_text())["files"][0]["path"].split("/")[:2],
            ["resources", "files"],
        )

    def test_part_tampering_is_detected_before_destination_is_created(self):
        manifest = self.prepare()
        part = self.release / manifest["parts"][0]["name"]
        part.write_bytes(part.read_bytes() + b"changed")
        output = self.folder / "installed"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            import_pack(self.release / "content-manifest.json", output)
        self.assertFalse(output.exists())

    def test_unsafe_manifest_paths_and_account_reference_are_rejected(self):
        self.prepare()
        path = self.release / "content-manifest.json"
        original = json.loads(path.read_text())
        for name in (
            "resources/files/../../escape",
            "reference/private.key",
            "reference/new_guest_profile.json",
            "resources/files/media/KpUser.dat",
            "resources/files/media/kpuser.dat",
            "resources/files/media/server.sqlite3-wal",
            "resources/files/media/private.p12",
        ):
            manifest = json.loads(json.dumps(original))
            manifest["payload"][name] = {"bytes": 0, "sha256": "0" * 64}
            path.write_text(json.dumps(manifest))
            with self.subTest(name=name), self.assertRaises(ValueError):
                import_pack(path, self.folder / "installed")

    def test_existing_data_or_save_is_never_overwritten(self):
        self.prepare()
        output = self.folder / "existing"
        output.mkdir()
        save = output / "save.txt"
        save.write_text("keep")
        with self.assertRaises(ValueError):
            import_pack(self.release / "content-manifest.json", output)
        self.assertEqual(save.read_text(), "keep")
        with self.assertRaises(ValueError):
            self.prepare()

    def test_duplicate_release_part_names_are_rejected_before_import(self):
        self.prepare()
        path = self.release / "content-manifest.json"
        manifest = json.loads(path.read_text())
        manifest["parts"].append(dict(manifest["parts"][0]))
        path.write_text(json.dumps(manifest))
        output = self.folder / "installed"
        with self.assertRaisesRegex(ValueError, "duplicate release part"):
            import_pack(path, output)
        self.assertFalse(output.exists())

    def test_check_detects_later_resource_change(self):
        self.prepare()
        output = self.folder / "installed"
        import_pack(self.release / "content-manifest.json", output)
        (output / "resources/files/media/demo.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "differs"):
            check(output)

    def test_missing_core_references_or_unsafe_archive_members_fail(self):
        missing = self.reference / "product_ids.bin"
        original = missing.read_bytes()
        missing.unlink()
        with self.assertRaises(ValueError):
            self.prepare()
        missing.write_bytes(original)
        with zipfile.ZipFile(self.root / INITIAL_ZIP, "w") as archive:
            archive.writestr("../escape", b"bad")
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.release.exists())
