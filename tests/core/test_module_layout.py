# SPDX-License-Identifier: Apache-2.0
"""Compatibility of historical imports and module commands across the package layout."""

import subprocess
import sys
import textwrap
import unittest


class ModuleLayoutTests(unittest.TestCase):
    def fresh_python(self, *args):
        result = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_package_startup_is_lazy_and_aliases_survive_cache_invalidation(self):
        self.fresh_python(
            "-c",
            textwrap.dedent("""
                import importlib
                import importlib.util
                import sys
                from guardian_tales import _compat

                assert not set(_compat._TARGETS.values()).intersection(sys.modules)
                importlib.invalidate_caches()
                for historical, canonical in _compat._TARGETS.items():
                    assert importlib.import_module(historical) is importlib.import_module(canonical), historical
                assert importlib.util.find_spec("guardian_tales.missing_module") is None
                """),
        )

    def test_both_import_orders_share_patches_and_the_canonical_spec(self):
        self.fresh_python(
            "-c",
            textwrap.dedent("""
                from importlib import reload
                from unittest.mock import patch

                from guardian_tales.runtime import packet_reader as canonical
                from guardian_tales import packet_reader as historical
                import guardian_tales.state_lock as lock
                from guardian_tales.runtime import state_lock

                assert historical is canonical and lock is state_lock
                original = canonical.MAX_PACKET
                with patch("guardian_tales.packet_reader.MAX_PACKET", 7):
                    assert canonical.MAX_PACKET == 7
                assert canonical.MAX_PACKET == original
                assert reload(historical) is canonical
                assert historical.__spec__.name == "guardian_tales.runtime.packet_reader"
                """),
        )

    def test_documented_flat_module_command(self):
        help_text = self.fresh_python("-m", "guardian_tales.classic_coop_bundle", "--help")
        self.assertIn("source", help_text)
        self.assertIn("output", help_text)
