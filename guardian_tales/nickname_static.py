# SPDX-License-Identifier: Apache-2.0
"""Compose a free-nickname client cost over the effective local static tables."""

import json
from functools import lru_cache

from .raid_static import compress, decode, digest, records


@lru_cache(maxsize=2)
def prepare(body):
    # The built-in bootstrap has no captured static tables or nickname constant.
    raw = decode(body)
    if raw.strip() == b"[]":
        return None
    lines, items = records(raw)
    if "constants" not in items:
        return None
    constants = json.loads(items["constants"][1])
    if not isinstance(constants, dict):
        raise ValueError("Invalid nickname constants table")
    if "ChangeNickCost" not in constants:
        return None
    cost = constants["ChangeNickCost"]
    if type(cost) is not int or not 0 <= cost <= 0x7FFFFFFF or "__checksum__" not in items:
        raise ValueError("Invalid nickname cost or static checksum")
    if cost == 0:
        return body, items["__checksum__"][1]
    constants["ChangeNickCost"] = 0
    content = json.dumps(constants, ensure_ascii=False, separators=(",", ":"))
    revision = max(items["constants"][2], items["__checksum__"][2]) + 1
    if revision > 0x7FFFFFFF:
        raise ValueError("Nickname static revision exceeds the native integer range")
    checksum = digest(
        b"local-free-nickname-v1\n" + items["__checksum__"][1].encode() + b"\n" + content.encode()
    )
    for name, value in (("constants", content), ("__checksum__", checksum)):
        at = items[name][0]
        lines[at : at + 4] = [
            name + "\n",
            value + "\n",
            str(revision) + "\n",
            digest(value.encode()) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(references, filename, request, parent):
    if filename in ("static_data_get.bin", "static_data_check.bin"):
        prepared = prepare(parent(references, "static_data_get.bin", request))
        if prepared is not None:
            body, checksum = prepared
            if filename == "static_data_get.bin":
                return body
            return json.dumps(
                {
                    "UpToDate": isinstance(request, dict) and request.get("Checksum") == checksum,
                    "Checksum": checksum,
                    "QuitGameWhenStaticDataUpdateNeeded": False,
                }
            ).encode()
    return parent(references, filename, request)
