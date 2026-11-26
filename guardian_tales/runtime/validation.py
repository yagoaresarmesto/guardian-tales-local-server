# SPDX-License-Identifier: Apache-2.0
"""Run tests from a repository checkout and emit a concise JSON result."""

import argparse
import json
import os
import socket
import sys
import unittest
from collections import Counter
from pathlib import Path


def load_groups(path):
    groups = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(groups, dict) or not groups:
        raise ValueError("Test groups must be a nonempty object")
    seen = set()
    for name, group in groups.items():
        if (
            not isinstance(name, str)
            or not name.isidentifier()
            or name == "all"
            or not isinstance(group, dict)
            or set(group) != {"description", "modules"}
            or not isinstance(group["description"], str)
            or not group["description"].strip()
            or not isinstance(group["modules"], list)
            or not group["modules"]
        ):
            raise ValueError("Invalid test group definition")
        for module in group["modules"]:
            if (
                not isinstance(module, str)
                or not all(part.isidentifier() for part in module.split("."))
                or not module.split(".")[-1].startswith("test_")
                or module in seen
            ):
                raise ValueError("Every test module must be assigned to exactly one group")
            seen.add(module)
    return groups


def test_cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_cases(item)
        else:
            yield item


def case_module(test):
    return type(test).__module__.removeprefix("tests.")


def catalog_suite(suite, groups, directory):
    owners = {module: name for name, group in groups.items() for module in group["modules"]}
    files = {
        ".".join(p.relative_to(directory).with_suffix("").parts)
        for p in directory.rglob("test_*.py")
    }
    if files != set(owners):
        missing, stale = sorted(files - owners.keys()), sorted(owners.keys() - files)
        raise ValueError(
            f"Test group catalog mismatch: unassigned={missing}, missing_files={stale}"
        )
    cases = list(test_cases(suite))
    modules = {case_module(test) for test in cases}
    if modules != files:
        raise ValueError("Test discovery must cover every catalog module with at least one test")
    ids = [test.id().removeprefix("tests.") for test in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate test identities found during discovery")
    return cases, owners


def selected_groups(groups, requested):
    unknown = set(requested) - groups.keys() - {"all"}
    if unknown:
        raise ValueError(f"Unknown test groups: {', '.join(sorted(unknown))}")
    if not requested or "all" in requested:
        return list(groups)
    return list(dict.fromkeys(requested))


def select_suite(suite, cases, owners, selected):
    if set(selected) == set(owners.values()):
        return suite
    chosen = set(selected)
    # Retain discovery order even when groups overlap in a command. Existing
    # module/class fixtures run under the same sequential unittest semantics.
    return unittest.TestSuite(test for test in cases if owners[case_module(test)] in chosen)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        metavar="NAME",
        help="Run a group; repeat to combine groups. Default: all",
    )
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="List available groups and discovered counts without running tests",
    )
    args = parser.parse_args(argv)
    directory = Path.cwd() / "tests"
    if not directory.is_dir():
        parser.error(
            "Run validation from the repository root; tests are not installed with the package."
        )
    try:
        groups = load_groups(directory / "groups.json")
        selected = selected_groups(groups, args.group)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    interfaces = [name for _, name in socket.if_nameindex()]
    isolated = os.environ.get("GT_EXPECT_NO_NETWORK") == "1"
    if isolated and interfaces != ["lo"]:
        parser.error("Expected an environment started with --network none")
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    if loader.errors:
        parser.error("Test discovery failed:\n" + "\n".join(loader.errors))
    try:
        cases, owners = catalog_suite(suite, groups, directory)
    except ValueError as error:
        parser.error(str(error))
    if args.list_groups:
        counts = Counter(owners[case_module(test)] for test in cases)
        print(
            json.dumps(
                {
                    "groups": [
                        {
                            "name": name,
                            "description": groups[name]["description"],
                            "modules": len(groups[name]["modules"]),
                            "tests": counts[name],
                        }
                        for name in selected
                    ],
                    "tests_total": sum(counts[name] for name in selected),
                },
                indent=2,
            )
        )
        raise SystemExit(0)
    suite = select_suite(suite, cases, owners, selected)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(
        json.dumps(
            dict(
                result="PASS" if result.wasSuccessful() else "FAIL",
                tests_run=result.testsRun,
                groups_run=selected,
                failures=len(result.failures),
                errors=len(result.errors),
                external_network_disabled=isolated,
                network_interfaces=interfaces,
                python=sys.version.split()[0],
                scope="Protocol, platform HTTPS, local account persistence, reward retries and read-only CDN. APK verification is documented separately.",
            ),
            indent=2,
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
