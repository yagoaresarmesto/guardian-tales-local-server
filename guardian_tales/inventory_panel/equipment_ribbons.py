# SPDX-License-Identifier: Apache-2.0
"""Knowledge and exclusive weapon markers shown on inventory slots."""

import json
from datetime import datetime, timezone

from guardian_tales.accounts.snapshots import CLIENT, preserved_read


def available_in_client(row, version, now):
    # This panel serves the supported EU (KakaoGlobal) client.
    start_version = row.get("VersionFrom", {}).get("KakaoGlobal")
    if start_version and tuple(map(int, start_version.lstrip("v").split("."))) > version:
        return False
    start_date = row.get("DateFrom", {}).get("KakaoGlobal")
    if start_date:
        start = datetime.fromisoformat(start_date)
        return (start if start.tzinfo else start.replace(tzinfo=timezone.utc)) <= now
    return True


def completed_weapon_books(specs, knowledge, saved):
    """Mark a family only once every tracked evolution and linked collection is recorded."""
    acquired = {int(key) for key, level in saved.get("ItemCollections", {}).items() if level >= 0}
    if not acquired:
        return set()
    version = tuple(map(int, CLIENT["version"].split(".")))
    now = datetime.now(timezone.utc)
    claimed = set(saved.get("CustomCollections", []))
    missing_sets = {
        item
        for entry in knowledge.get("Collection", [])
        if entry["Id"] not in claimed and available_in_client(entry, version, now)
        for item in entry["ItemId"]
    }
    categories = {key.lower() for key in knowledge.get("ItemMastery", {})}
    weapons = {
        ident: spec
        for ident, spec in specs.items()
        if spec.get("Type") == "weapon"
        and spec.get("WeaponType") in categories
        and available_in_client(spec, version, now)
    }
    origins = {
        ident - spec["Rarity"] + spec["OriginRarity"]
        for ident, spec in weapons.items()
        if "OriginRarity" in spec and "Rarity" in spec
    }
    completed = set()
    for ident in origins:
        family = set()
        while ident in weapons and ident not in family:
            family.add(ident)
            next_ids = weapons[ident].get("EvolveTo", {})
            ident = next_ids.get("KakaoGlobal", next_ids.get("Default"))
        tracked = {i for i in family if weapons[i].get("SortingNumber") != -1}
        if tracked and tracked <= acquired and family.isdisjoint(missing_sets):
            completed.update(family)
    return completed


def read_completed_books(db, specs, tables):
    if (
        "knowledgecollection" not in tables
        or not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='imported_account'"
        ).fetchone()
    ):
        return set()
    saved = preserved_read(db, "/collection/list-all")
    if not saved:
        return set()
    return completed_weapon_books(specs, json.loads(tables["knowledgecollection"][1]), saved)


def equipment_ribbons(item, spec, completed):
    marks = ["book-complete"] if spec.get("Id") in completed else []
    if not spec.get("ExclusiveCharacterId"):
        return marks
    collab = bool(spec.get("CollaborationId"))
    choices = item.get("EngraveOptions")
    if not isinstance(choices, list) or not choices:
        marks.append("exclusive-collab" if collab else "exclusive")
        return marks
    # The client compares the first selected roll against the first template tier.
    tiers = spec.get("EngraveRandomOptions") or []
    highest = tiers[0].get("Level") if tiers and isinstance(tiers[0], dict) else None
    rolled = choices[0].get("Level") if isinstance(choices[0], dict) else None
    if isinstance(rolled, int) and isinstance(highest, int) and rolled >= highest:
        marks.append("engraved-max")
    else:
        marks.append("engraved-collab" if collab else "engraved")
    return marks
