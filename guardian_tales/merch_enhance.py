# SPDX-License-Identifier: Apache-2.0
"""Apply the forge's XP and family evolution rules without consuming its materials."""

import json
from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
from itertools import accumulate

from .admin_test_items import save_profile
from .item_lock import INVENTORIES, MAX_BATCH
from .raid_static import decode, records
from .village import MAX_REVISION, integer
from .weapon_enhance import decimal_id

ROUTE = "/merch/enhance-merch/v2"


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS merch_enhance_requests "
        "(operation_id TEXT PRIMARY KEY, request TEXT NOT NULL)"
    )


@dataclass
class Forge:
    items: dict
    thresholds: list
    levels: list
    evolves: list
    duplicate_bonus: int

    def material_value(self, row, spec, target_group):
        if spec["Type"] == "merchenhance":
            return spec["ExpReward"], 0
        origin, rarity = spec["OriginRarity"], spec["Rarity"]
        level = bisect_right(self.thresholds[origin], row["Experience"]) - 1
        xp = self.levels[level]["ExpReward"][origin]
        if spec["GroupId"] == target_group:
            return xp + self.duplicate_bonus, self.evolves[rarity]["ProgressReward"][origin]
        return xp, 0

    def evolve(self, spec, current, gained):
        if not gained or not spec["EvolveTo"]:
            return spec["Id"], current
        origin = spec["OriginRarity"]
        # A directly granted high-rarity copy may have no recorded evolution progress.
        spent = sum(row["ProgressNeeded"][origin] for row in self.evolves[origin : spec["Rarity"]])
        total = max(current, spent) + gained
        while spec["EvolveTo"]:
            step = self.evolves[spec["Rarity"]]["ProgressNeeded"][origin]
            if not step:
                raise ValueError("Invalid merch evolution threshold")
            if total < spent + step:
                break
            next_spec = self.items.get(spec["EvolveTo"], {})
            if (
                next_spec.get("Type") != "merch"
                or next_spec.get("GroupId") != spec["GroupId"]
                or next_spec.get("OriginRarity") != origin
                or next_spec.get("Rarity") != spec["Rarity"] + 1
            ):
                raise ValueError("Invalid merch evolution chain")
            spent += step
            spec = next_spec
        return spec["Id"], total if spec["EvolveTo"] else spent


@lru_cache(maxsize=2)
def rules(body):
    tables = records(decode(body))[1]
    try:
        data = json.loads(tables["merch"][1])
        levels, evolves = data["MerchLevels"], data["MerchEvolves"]
        for rows, index, fields in (
            (levels, "Level", ("ExpNeeded", "ExpReward")),
            (evolves, "Rarity", ("ProgressNeeded", "ProgressReward")),
        ):
            if not rows or any(
                row[index] != i
                or any(len(row[k]) != 3 or not all(integer(v) for v in row[k]) for k in fields)
                for i, row in enumerate(rows)
            ):
                raise ValueError("Invalid merch forge progression table")
        thresholds = [
            list(accumulate((row["ExpNeeded"][origin] for row in levels[:-1]), initial=0))
            for origin in range(3)
        ]
        if any(any(a >= b for a, b in zip(curve, curve[1:])) for curve in thresholds):
            raise ValueError("Invalid merch XP thresholds")
        bonus = data["Constants"]["DuplicateExpBonus"]
        if not integer(bonus):
            raise ValueError("Invalid duplicate merch XP bonus")
        items = {}
        for spec in json.loads(tables["items"][1]):
            if spec["Type"] not in ("merch", "merchenhance"):
                continue
            if not integer(spec["Id"], minimum=1) or spec["Id"] in items:
                raise ValueError("Invalid merch item ID")
            if spec["Type"] == "merchenhance":
                if not integer(spec["ExpReward"], minimum=1):
                    raise ValueError("Invalid merch enhancer XP")
            elif not (
                integer(spec["OriginRarity"], 2)
                and integer(spec["Rarity"], len(evolves) - 1, spec["OriginRarity"])
                and integer(spec["GroupId"], minimum=1)
                and integer(spec["EvolveTo"])
            ):
                raise ValueError("Invalid merch family or rarity")
            items[spec["Id"]] = spec
    except (KeyError, TypeError) as exc:
        raise ValueError("Missing matching merch forge tables") from exc
    return Forge(items, thresholds, levels, evolves, bonus)


def improve(user, body, forge):
    owned = {}
    for kind in INVENTORIES:
        rows = user.get(kind)
        if not isinstance(rows, list):
            raise ValueError("Missing saved inventory")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not integer(row.get("Id"), minimum=1)
                or row["Id"] in owned
            ):
                raise ValueError("Invalid or ambiguous saved item ID")
            owned[row["Id"]] = (kind, row)

    def lookup(ident):
        kind, row = owned.get(ident, (None, {}))
        item_id = row.get("ItemId")
        spec = forge.items.get(item_id) if integer(item_id, minimum=1) else None
        if not spec or not integer(row.get("Amount"), minimum=1):
            raise ValueError("Select owned merch or enhancement material")
        if spec["Type"] == "merch":
            if kind != "ItemMiscs" or row["Amount"] != 1 or not integer(row.get("Experience")):
                raise ValueError("Invalid saved merch copy")
        elif kind != "ItemStackables":
            raise ValueError("Invalid saved merch enhancer stack")
        return row, spec

    target, spec = lookup(body["ItemId"])
    if spec["Type"] != "merch" or not integer(target.get("EvolveProgress")):
        raise ValueError("Select an owned merch copy to improve")
    xp = progress = 0
    for key, count in body["SourceItems"].items():
        material, material_spec = lookup(int(key))
        if material is target or material.get("Locked") is not False or count > material["Amount"]:
            raise ValueError("Select distinct, unlocked materials in owned quantities")
        exp, evolution = forge.material_value(material, material_spec, spec["GroupId"])
        xp += exp * count
        progress += evolution * count
    cap = forge.thresholds[spec["OriginRarity"]][-1]
    experience = target["Experience"]
    new_xp = max(experience, min(cap, experience + xp))
    new_spec, new_progress = forge.evolve(spec, target["EvolveProgress"], progress)
    if (new_xp, new_spec, new_progress) == (experience, spec["Id"], target["EvolveProgress"]):
        raise ValueError("These materials cannot improve this merch any further")
    target.update(Experience=new_xp, ItemId=new_spec, EvolveProgress=new_progress)


def enhance(account, body, operation_id):
    if (
        not isinstance(body, dict)
        or set(body) != {"ItemId", "SourceItems", "discountBuff"}
        or not integer(body["ItemId"], minimum=1)
        or type(body["discountBuff"]) is not bool
        or not isinstance(body["SourceItems"], dict)
        or not 1 <= len(body["SourceItems"]) <= MAX_BATCH
        or any(
            not decimal_id(k) or not integer(v, minimum=1) for k, v in body["SourceItems"].items()
        )
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
        or account.needs_prologue()
    ):
        raise ValueError("Invalid merch enhancement request")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user = profile["User"]
        previous = db.execute(
            "SELECT request FROM merch_enhance_requests WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if previous:
            if previous[0] != encoded:
                raise ValueError("Merch enhancement retry has different materials or target")
        else:
            if not integer(user.get("Cas"), MAX_REVISION - 1):
                raise ValueError("Invalid saved user revision")
            improve(user, body, rules(account.references.read_bytes("static_data_get.bin")))
            save_profile(db, profile)
            db.execute("INSERT INTO merch_enhance_requests VALUES(?,?)", (operation_id, encoded))
    return {"User": user}
