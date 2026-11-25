# SPDX-License-Identifier: Apache-2.0
"""Reuse rendered artwork across dashboard processes and local restarts."""

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path


def cached_art(source, variant, revision, render):
    """Keep one atomically replaced entry per source and output variant."""
    root = Path(
        os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    )
    identity = json.dumps([os.path.normcase(str(source.resolve())), variant]).encode()
    key = hashlib.sha256(identity).hexdigest()
    target = root / "guardian-tales-local" / "panel-art" / key[:2] / key[2:]
    # Bump the format revision when a renderer or its layout changes.
    stamp = hashlib.sha256(json.dumps([1, revision]).encode()).digest()
    try:
        with target.open("rb") as stream:
            if stream.read(len(stamp)) == stamp:
                checksum = stream.read(32)
                data = stream.read()
                if hashlib.sha256(data).digest() == checksum:
                    return data
    except OSError:
        pass

    data = render()
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(stamp)
            stream.write(hashlib.sha256(data).digest())
            stream.write(data)
        temporary.replace(target)
    except OSError:
        # Read-only or full cache directories still allow normal rendering.
        pass
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
    return data
