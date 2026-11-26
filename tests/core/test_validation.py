# SPDX-License-Identifier: Apache-2.0
"""Test groups retain discovery order and cannot silently omit or duplicate cases."""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from guardian_tales.runtime.validation import (
    catalog_suite,
    load_groups,
    main,
    select_suite,
    selected_groups,
    test_cases,
)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "tests"
        self.directory.mkdir()
        self.groups = {
            "core": {"description": "Core", "modules": ["test_fast"]},
            "inventory": {"description": "Items", "modules": ["test_items"]},
            "integration": {"description": "Loopback", "modules": ["test_slow"]},
        }
        self.path = self.directory / "groups.json"
        self.path.write_text(json.dumps(self.groups))
        for name in ("test_fast", "test_items", "test_slow"):
            (self.directory / f"{name}.py").touch()
        self.events = []

    def example(self, module, name):
        events = self.events
        cls = type(
            name,
            (unittest.TestCase,),
            {"__module__": module, "test_run": lambda instance: events.append(name)},
        )
        return cls("test_run")

    def suite(self):
        return unittest.TestSuite(
            [
                unittest.TestSuite([self.example("test_fast", "Fast")]),
                unittest.TestSuite(
                    [self.example("test_items", "Items"), self.example("test_slow", "Slow")]
                ),
            ]
        )

    def test_default_suite_is_unchanged_and_filtering_retains_discovery_order(self):
        suite = self.suite()
        original = [test.id() for test in test_cases(suite)]
        cases, owners = catalog_suite(suite, self.groups, self.directory)
        self.assertIs(select_suite(suite, cases, owners, selected_groups(self.groups, [])), suite)
        self.assertEqual([test.id() for test in test_cases(suite)], original)
        selected = select_suite(suite, cases, owners, ["inventory", "core"])
        result = unittest.TextTestRunner(stream=io.StringIO()).run(selected)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.testsRun, 2)
        self.assertEqual(self.events, ["Fast", "Items"])

    def test_repeated_groups_are_a_union_and_unknown_names_never_fall_back_to_all(self):
        suite = self.suite()
        cases, owners = catalog_suite(suite, self.groups, self.directory)
        names = selected_groups(self.groups, ["inventory", "core", "inventory"])
        selected = select_suite(suite, cases, owners, names)
        self.assertEqual(selected.countTestCases(), 2)
        self.assertEqual(names, ["inventory", "core"])
        self.assertIs(
            select_suite(suite, cases, owners, selected_groups(self.groups, ["all"])), suite
        )
        with self.assertRaisesRegex(ValueError, "Unknown test groups"):
            selected_groups(self.groups, ["typo"])

    def test_missing_stale_repeated_and_undiscovered_modules_cannot_silently_lose_coverage(self):
        self.assertEqual(load_groups(self.path), self.groups)
        new_file = self.directory / "test_new.py"
        new_file.touch()
        with self.assertRaisesRegex(ValueError, "unassigned"):
            catalog_suite(self.suite(), self.groups, self.directory)
        new_file.unlink()
        slow = self.directory / "test_slow.py"
        slow.unlink()
        with self.assertRaisesRegex(ValueError, "missing_files"):
            catalog_suite(self.suite(), self.groups, self.directory)
        slow.touch()
        incomplete = unittest.TestSuite([self.example("test_fast", "Fast")])
        with self.assertRaisesRegex(ValueError, "discovery"):
            catalog_suite(incomplete, self.groups, self.directory)
        bad = copy.deepcopy(self.groups)
        bad["inventory"]["modules"].append("test_fast")
        self.path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            load_groups(self.path)

    def test_duplicate_case_ids_are_detected_even_with_package_aliases(self):
        suite = self.suite()
        suite.addTest(self.example("tests.test_fast", "Fast"))
        with self.assertRaisesRegex(ValueError, "Duplicate test identities"):
            catalog_suite(suite, self.groups, self.directory)

    def test_cli_lists_counts_without_running_tests(self):
        output = io.StringIO()
        with (
            patch("guardian_tales.runtime.validation.Path.cwd", return_value=self.root),
            patch(
                "guardian_tales.runtime.validation.unittest.TestLoader.discover",
                return_value=self.suite(),
            ),
            patch("guardian_tales.runtime.validation.unittest.TextTestRunner") as runner,
            patch.dict(os.environ, {"GT_EXPECT_NO_NETWORK": "0"}),
            redirect_stdout(output),
            self.assertRaises(SystemExit) as stopped,
        ):
            main(["--list-groups"])
        self.assertEqual(stopped.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue())["tests_total"], 3)
        self.assertEqual(self.events, [])
        runner.assert_not_called()

    def test_cli_rejects_unknown_group_before_discovery_or_execution(self):
        with (
            patch("guardian_tales.runtime.validation.Path.cwd", return_value=self.root),
            patch("guardian_tales.runtime.validation.unittest.TestLoader.discover") as discover,
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as stopped,
        ):
            main(["--group", "typo"])
        self.assertEqual(stopped.exception.code, 2)
        discover.assert_not_called()
