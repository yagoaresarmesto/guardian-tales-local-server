# SPDX-License-Identifier: Apache-2.0
"""External hero candidates and persistent wishlist selection, without summons."""

import hashlib
import json


def load_selection_catalog(references):
    if references is None or not (references.directory / "summon_selection_catalog.json").is_file():
        return None
    value = references.json("summon_selection_catalog.json")
    rows = value.get("characters") if isinstance(value, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError("Invalid external summon-selection catalog")
    ids, origins = set(), set()
    required = {"Id", "CharacterOriginId", "SummonCategory", "SummonEventType", "IsNew"}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not required <= set(row)
            or set(row) - required - {"VersionFrom", "SelectableFrom"}
            or any(
                type(row[k]) is not int or not 1 <= row[k] <= 0x7FFFFFFF
                for k in ("Id", "CharacterOriginId")
            )
            or row["Id"] in ids
            or row["CharacterOriginId"] in origins
            or row["SummonCategory"] != "Unique"
            or row["SummonEventType"] != "Character"
            or type(row["IsNew"]) is not bool
        ):
            raise ValueError("Invalid or duplicate summon-selection hero")
        for name in ("VersionFrom", "SelectableFrom"):
            if name not in row:
                continue
            values = row[name]
            if (
                not isinstance(values, dict)
                or len(values) > 20
                or any(
                    not isinstance(k, str)
                    or not 1 <= len(k) <= 40
                    or not isinstance(v, str)
                    or not 1 <= len(v) <= 100
                    or any(ord(c) < 32 for c in k + v)
                    for k, v in values.items()
                )
            ):
                raise ValueError("Invalid summon-selection service dates or versions")
        ids.add(row["Id"])
        origins.add(row["CharacterOriginId"])
    checksum = (
        "local-selection-"
        + hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
    )
    return rows, checksum


def select_characters(account, request):
    catalog = load_selection_catalog(account.references)
    if catalog is None:
        raise ValueError("A matching summon-selection catalog is required")
    allowed = {row["CharacterOriginId"] for row in catalog[0]}
    if (
        not isinstance(request, dict)
        or set(request) != {"RequestOriginIds"}
        or not isinstance(request["RequestOriginIds"], list)
        or len(request["RequestOriginIds"]) > 5
        or any(type(i) is not int or i not in allowed for i in request["RequestOriginIds"])
        or len(set(request["RequestOriginIds"])) != len(request["RequestOriginIds"])
        or account.needs_prologue()
    ):
        raise ValueError(
            "Select up to five distinct known hero origins after completing the prologue"
        )
    profile = account.profile()
    shop = profile["UserShop"]
    selected = request["RequestOriginIds"]
    if shop["SelectedSummonCharacters"] != selected:
        shop["SelectedSummonCharacters"] = list(selected)
        shop["Cas"] += 1
        with account.db:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"UserShop": shop}
