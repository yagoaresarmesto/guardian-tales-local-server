# SPDX-License-Identifier: Apache-2.0
"""Synthetic packs preserve bundle paths and never import account files."""

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from guardian_tales.assets import ResourceLibrary
from scripts.build_ondemand_archives import build_archives


class OndemandArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, label, files):
        package = self.folder / label
        root = package / "resources/files"
        rows = []
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            rows.append(
                {"path": "resources/files/" + name, "sha256": hashlib.sha256(content).hexdigest()}
            )
        (package / "manifest.json").write_text(json.dumps({"files": rows}))
        return root

    def test_groups_merge_overrides_and_create_a_servable_manifest(self):
        root = self.source(
            "base",
            {
                "AssetBundles/Android/ondemand/demo/tiles": b"old",
                "AssetBundles/Android/ondemand/demo/tiles.etag": b'"etag"',
                "AssetBundles/Android/ondemand/second/ui": b"second",
                "private-account.txt": b"excluded",
            },
        )
        supplement = self.source("extra", {"AssetBundles/Android/ondemand/demo/tiles": b"new"})
        output = self.folder / "pack"
        report = build_archives([root, supplement], output)
        self.assertEqual([r["group"] for r in report["archives"]], ["demo", "second"])
        library = ResourceLibrary([output / "resources/files"])
        for group, expected in (
            ("demo", {"demo/tiles": b"new"}),
            ("second", {"second/ui": b"second"}),
        ):
            path, digest = library.lookup(
                "/live/global/0491/AssetBundles/Android/ondemand/" + group + ".zip"
            )
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(
                    {name: archive.read(name) for name in archive.namelist()}, expected
                )
        self.assertEqual((root / "AssetBundles/Android/ondemand/demo/tiles").read_bytes(), b"old")

    def test_group_selection_and_unknown_groups(self):
        root = self.source("base", {"AssetBundles/Android/ondemand/demo/a": b"x"})
        with self.assertRaises(ValueError):
            build_archives([root], self.folder / "missing", ["unknown"])
        self.assertFalse((self.folder / "missing").exists())
        report = build_archives([root], self.folder / "selected", ["demo", "demo"])
        self.assertEqual(len(report["archives"]), 1)

    def test_source_and_existing_output_cannot_be_overwritten(self):
        root = self.source("base", {"AssetBundles/Android/ondemand/demo/a": b"x"})
        with self.assertRaises(ValueError):
            build_archives([root], root / "generated")
        output = self.folder / "pack"
        build_archives([root], output)
        before = (output / "manifest.json").read_bytes()
        with self.assertRaises(ValueError):
            build_archives([root], output)
        self.assertEqual((output / "manifest.json").read_bytes(), before)

    def test_parent_traversal_is_rejected_before_writing(self):
        root = self.source("base", {"AssetBundles/Android/ondemand/demo/a": b"x"})
        manifest = root.parent.parent / "manifest.json"
        rows = json.loads(manifest.read_text())
        rows["files"].append(
            {
                "path": "resources/files/AssetBundles/Android/ondemand/demo/../demo/a",
                "sha256": "0" * 64,
            }
        )
        manifest.write_text(json.dumps(rows))
        with self.assertRaises(ValueError):
            build_archives([root], self.folder / "unsafe")
        self.assertFalse((self.folder / "unsafe").exists())
