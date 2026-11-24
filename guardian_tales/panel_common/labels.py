# SPDX-License-Identifier: Apache-2.0
"""Look up selected keys in the optional decoded English client table."""

import base64

from guardian_tales.andras_trial_static import binary_rows
from guardian_tales.raid_custom import binary_name_hash


def english_labels(references, catalog_hash, keys):
    path = references.directory / f"andras-trial-strings-{catalog_hash}.bin"
    if not path.is_file():
        path = references.directory / "strings-bin-enUS"
    if not path.is_file():
        return {}
    try:
        wanted = {binary_name_hash(key): key for key in keys}
        entries = binary_rows(
            base64.b64encode(path.read_bytes()).decode(), require_id=False, max_count=500000
        )
        return {wanted[key]: raw.decode("utf-8") for _, key, raw in entries if key in wanted}
    except (OSError, ValueError):
        return {}
