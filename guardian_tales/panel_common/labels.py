# SPDX-License-Identifier: Apache-2.0
"""Look up selected keys in the optional decoded English client table."""

import hashlib
from collections import OrderedDict
from threading import Lock

from guardian_tales.andras_trial_static import read_binary_rows
from guardian_tales.raid_custom import binary_name_hash

_lookups = OrderedDict()
_lock = Lock()


def _lookup(data, hashes):
    key = (hashlib.sha256(data).digest(), hashes)
    with _lock:
        if key in _lookups:
            _lookups.move_to_end(key)
            return _lookups[key]
        entries = read_binary_rows(data, require_id=False, max_count=500000)
        labels = {h: raw.decode("utf-8") for _, h, raw in entries if h in hashes}
        # Retain just the requested translations, never the entire unpacked client table.
        _lookups[key] = labels
        if len(_lookups) > 8:
            _lookups.popitem(last=False)
        return labels


def english_labels(references, catalog_hash, keys):
    path = references.directory / f"andras-trial-strings-{catalog_hash}.bin"
    if not path.is_file():
        path = references.directory / "strings-bin-enUS"
    if not path.is_file():
        return {}
    try:
        wanted = {binary_name_hash(key): key for key in keys}
        if not wanted:
            return {}
        labels = _lookup(path.read_bytes(), frozenset(wanted))
        return {wanted[key]: label for key, label in labels.items()}
    except (OSError, ValueError):
        return {}
