# SPDX-License-Identifier: Apache-2.0
"""Reuse byte-identical static overlays between local backend processes."""

import hashlib
import json
import os
import sys
import tempfile
from contextlib import suppress
from functools import lru_cache
from pathlib import Path

from guardian_tales.runtime.packet_reader import MAX_PACKET

from .reference import PACKAGE_ROOT


@lru_cache(maxsize=1)
def _implementation():
    # Builders also use rules from other game modules. Invalidate their output together.
    version = hashlib.sha256(sys.implementation.cache_tag.encode())
    for path in sorted(PACKAGE_ROOT.rglob("*.py"), key=Path.as_posix):
        version.update(path.relative_to(PACKAGE_ROOT).as_posix().encode() + b"\0")
        version.update(hashlib.sha256(path.read_bytes()).digest())
    return version.digest()


def _integrity(key, header, body):
    digest = hashlib.sha256(key + header)
    digest.update(body)
    return digest.digest()


class StaticCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.latest = {}

    def prepare(self, transform, source, *args, **kwargs):
        name = f"{transform.__module__}.{transform.__name__}"
        try:
            version = _implementation()
        except OSError:
            return transform(source, *args, **kwargs)
        settings = json.dumps([name, args, kwargs], sort_keys=True, separators=(",", ":")).encode()
        key = hashlib.sha256(version + hashlib.sha256(source).digest() + settings).digest()
        last = self.latest.get(name)
        if last is not None and last[0] == key:
            return last[1]
        path = self.directory / (name + ".bin")
        result = self._read(path, key)
        if result is None:
            result = transform(source, *args, **kwargs)
            if result is not None:
                self._store(path, key, *result)
        self.latest[name] = (key, result)
        return result

    @staticmethod
    def _read(path, key):
        try:
            with path.open("rb") as stream:
                if stream.read(32) != key:
                    return None
                expected = stream.read(32)
                header = stream.readline(257)
                if len(header) > 256 or not header.endswith(b"\n"):
                    return None
                body = stream.read(MAX_PACKET + 1)
            if 0 < len(body) <= MAX_PACKET and expected == _integrity(key, header, body):
                return body, header[:-1].decode("utf-8")
        except (OSError, UnicodeError):
            pass
        return None

    @staticmethod
    def _store(path, key, body, checksum):
        header = checksum.encode("utf-8") + b"\n"
        if len(header) > 256 or b"\n" in header[:-1] or not 0 < len(body) <= MAX_PACKET:
            return
        temp = None
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temp = Path(stream.name)
                stream.write(key + _integrity(key, header, body) + header)
                stream.write(body)
            os.replace(temp, path)
        except OSError:
            pass  # Cache availability must never prevent delivery of a freshly prepared result.
        finally:
            if temp is not None:
                with suppress(OSError):
                    temp.unlink(missing_ok=True)


def prepare_static(references, transform, source, *args, **kwargs):
    cache = getattr(references, "static_cache", None)
    if cache is None:
        return transform(source, *args, **kwargs)
    return cache.prepare(transform, source, *args, **kwargs)
