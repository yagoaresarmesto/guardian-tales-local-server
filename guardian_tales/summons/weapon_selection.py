# SPDX-License-Identifier: Apache-2.0
"""Expose eligible weapon candidates and persist the ordered summon wishlist."""

import hashlib
import json

from guardian_tales.settlement.village import MAX_REVISION, integer

from .weapon_summon import weapon_catalog

ROUTE = "/summon/set-select-weapon"


def load_selection_catalog(references):
    if references is None or not (references.directory / "static_data_get.bin").is_file():
        return None
    weapons = weapon_catalog(references.read_bytes("static_data_get.bin"))[0]
    # Local candidate IDs are stable design IDs. Requests and the saved wishlist
    # use ItemId, not an owned inventory row or a character origin.
    return [
        {
            "Id": spec,
            "ItemId": spec,
            # ItemSummonCategory is a different native enum from hero categories.
            "SummonCategory": "Exclusive",
            "SummonEventType": "Weapon",
            "IsNew": False,
        }
        for spec, rank in sorted(weapons.items())
        if rank == 4
    ]


def selection_checksum(characters, weapons):
    encoded = json.dumps(
        {"characters": characters or [], "weapons": weapons},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "local-selection-" + hashlib.sha256(encoded).hexdigest()[:24]


def select(account, request):
    candidates = load_selection_catalog(account.references)
    allowed = {row["ItemId"] for row in candidates} if candidates is not None else set()
    if (
        candidates is None
        or not isinstance(request, dict)
        or set(request) != {"RequestItemIds"}
        or not isinstance(request["RequestItemIds"], list)
        or len(request["RequestItemIds"]) > 5
        or any(not integer(i, minimum=1) or i not in allowed for i in request["RequestItemIds"])
        or len(set(request["RequestItemIds"])) != len(request["RequestItemIds"])
        or account.needs_prologue()
    ):
        raise ValueError(
            "Select up to five distinct eligible epic weapon designs after the prologue"
        )
    profile = account.profile()
    user, shop = profile["User"], profile["UserShop"]
    previous = shop.get("SelectedSummonWeapons")
    if (
        not integer(user.get("Id"), minimum=1)
        or not integer(shop.get("UserId"), minimum=1)
        or shop["UserId"] != user["Id"]
        or not integer(shop.get("Cas"), MAX_REVISION)
        or not isinstance(previous, list)
        or len(previous) > 5
        or any(not integer(i, minimum=1) for i in previous)
        or len(set(previous)) != len(previous)
    ):
        raise ValueError("Invalid saved weapon wishlist, shop owner or revision")
    selected = request["RequestItemIds"]
    if previous != selected:
        if shop["Cas"] == MAX_REVISION:
            raise ValueError("Weapon-wishlist revision overflow")
        shop["SelectedSummonWeapons"] = list(selected)
        shop["Cas"] += 1
        with account.db:
            account.db.execute(
                "UPDATE local_account SET profile=? WHERE id=1",
                (json.dumps(profile, separators=(",", ":")),),
            )
    return {"UserShop": shop}
