# SPDX-License-Identifier: Apache-2.0
"""Separate reconstructed templates from optional external client data."""

import json
import os
import struct
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"


def default_cert_dir():
    return Path(os.environ.get("GT_CERT_DIR", "local/tls"))


def compressed_empty_list():
    """Literal-only raw LZ4 block containing [], followed by decoded length."""
    return b"\x20[]" + struct.pack("<I", 2)


class ReferenceData:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get("GT_REFERENCE_DIR", "local/reference"))

    def read_bytes(self, name):
        if Path(name).name != name:
            raise ValueError("Reference files must have a simple filename")
        external = self.directory / name
        if external.is_file():
            return external.read_bytes()
        builtin = TEMPLATES / name
        if builtin.is_file():
            return builtin.read_bytes()
        raise ValueError(
            f"Missing reference file: {name}. Configure --reference-dir; see docs/reference-data.md."
        )

    def json(self, name):
        return json.loads(self.read_bytes(name).decode("utf-8"))
