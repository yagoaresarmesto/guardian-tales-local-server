# SPDX-License-Identifier: Apache-2.0
"""Manual and automatic equipment synthesis using the installed forge catalog."""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from random import SystemRandom

from .admin_test_items import save_profile
from .inventory_panel.equipment_options import roll_new_options, rules_for
from .inventory_panel.equipment_ribbons import available_in_client
from .inventory_panel.owned_copies import detach_presets, detach_selected
from .inventory_panel.weapon_progression import LIMIT_BREAK_TYPES
from .jewel_upgrade import owned_inventory
from .raid_static import decode, records
from .snapshots import CLIENT
from .test_item_static import item_definitions
from .village import MAX_REVISION, integer

MANUAL = "/item/compose-weapon"
AUTO = "/item/compose-gears"
ROUTES = (MANUAL, AUTO)
RANDOM = SystemRandom()


def create_tables(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS mystery_evolution_requests "
        "(operation_id TEXT PRIMARY KEY, route TEXT NOT NULL, request TEXT NOT NULL, "
        "succeeded INTEGER NOT NULL)"
    )


def groups_for(route, body):
    if not isinstance(body, dict):
        raise ValueError("Invalid mystery evolution request")
    if route == MANUAL and set(body) == {"TargetWeaponId", "SourceWeaponIds"}:
        sources = body["SourceWeaponIds"]
        groups = [[body["TargetWeaponId"], *sources]] if isinstance(sources, list) else None
    elif route == AUTO and set(body) == {"ComposeRequests"}:
        groups = body["ComposeRequests"]
    else:
        raise ValueError("Invalid mystery evolution selection")
    if not isinstance(groups, list) or not groups:
        raise ValueError("Select at least one mystery evolution group")
    seen = set()
    for group in groups:
        if not isinstance(group, list) or len(group) < 2:
            raise ValueError("Each evolution requires a target and materials")
        for ident in group:
            if not integer(ident, minimum=1) or ident in seen:
                raise ValueError("Select distinct owned equipment copies")
            seen.add(ident)
    return groups


@dataclass
class Catalog:
    steps: dict
    rarities: dict
    pools: dict
    options: dict

    def roll(self, rarity):
        exclusive = RANDOM.random() < self.steps[rarity]["ExclusiveProbability"]
        choices = self.pools.get((rarity + 1, exclusive))
        if not choices:
            raise ValueError("Missing eligible mystery evolution results")
        return RANDOM.choice(choices)


@lru_cache(maxsize=2)
def catalog(body, day):
    tables = records(decode(body))[1]
    try:
        rows = json.loads(tables["weaponenhance"][1])["WeaponCompose"]
        effects = {row["Id"] for row in json.loads(tables["options"][1])}
        steps = {}
        for row in rows:
            rarity, rates = row["Rarity"], row["Probability"]
            if rates is None:
                continue
            exclusive = row["ExclusiveProbability"]
            if (
                not integer(rarity, 3)
                or rarity in steps
                or not isinstance(rates, list)
                or not rates
                or not all(type(n) in (int, float) and 0 <= n <= 1 for n in rates)
                or rates != sorted(rates)
                or type(exclusive) not in (int, float)
                or not (exclusive == -1 or 0 <= exclusive <= 1)
            ):
                raise ValueError("Invalid mystery evolution probability table")
            steps[rarity] = row
        rarities, options, pools = {}, {}, defaultdict(list)
        version = tuple(map(int, CLIENT["version"].split(".")))
        for spec in item_definitions(body):
            if (
                spec.get("Type") != "weapon"
                or spec.get("WeaponType") not in LIMIT_BREAK_TYPES
                or not integer(spec.get("Rarity"), 4)
                or spec.get("SortingNumber") == -1
                or not available_in_client(spec, version, day)
            ):
                continue
            ident, rarity = spec["Id"], spec["Rarity"]
            rarities[ident] = rarity
            if (
                rarity == 0
                or spec.get("Composable") is not True
                or spec.get("Limited") is not False
            ):
                continue
            rules = rules_for(spec, effects)
            if rules is None and not (
                spec.get("MinOptions") == spec.get("MaxOptions") == 0 and not spec.get("Options")
            ):
                continue
            options[ident] = rules
            pools[rarity, bool(spec.get("ExclusiveCharacterId"))].append(ident)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Missing matching mystery evolution tables") from exc
    return Catalog(steps, rarities, dict(pools), options)


def apply_groups(db, profile, groups, forge):
    user = profile["User"]
    inventory = owned_inventory(user)
    all_ids = [row.get("Id") for row in inventory]
    if not all(integer(i, minimum=1) for i in all_ids) or len(set(all_ids)) != len(all_ids):
        raise ValueError("Ambiguous inventory IDs")
    equipment = {row["Id"]: row for row in user["ItemWeapons"]}
    training = user.get("TrainingSlots", {})
    if not isinstance(training, dict) or not all(
        isinstance(slot, dict) and integer(slot.get("ItemId", 0)) for slot in training.values()
    ):
        raise ValueError("Invalid saved training assignments")
    in_training = {slot.get("ItemId") for slot in training.values()}
    evolved = set()
    ranks = Counter()
    for group in groups:
        copies = [equipment.get(i, {}) for i in group]
        if not all(integer(row.get("ItemId"), minimum=1) for row in copies):
            raise ValueError("Select equipment copies from this inventory")
        target = copies[0]
        rarity = forge.rarities.get(target.get("ItemId"))
        step = forge.steps.get(rarity)
        if not step or len(group) - 1 > len(step["Probability"]):
            raise ValueError("Choose a 1 to 4 star target and a supported material count")
        if any(
            row.get("Locked") is not False
            or not integer(row.get("Amount"), 1, 1)
            or forge.rarities.get(row.get("ItemId")) != rarity
            or row["Id"] in in_training
            or any(row.get("JewelSlots") or [])
            for row in copies
        ):
            raise ValueError("Select unlocked equipment of the same star rank outside training")
        if RANDOM.random() >= step["Probability"][len(group) - 2]:
            continue
        spec_id = forge.roll(rarity)
        rules = forge.options[spec_id]
        target.update(
            ItemId=spec_id,
            Options=roll_new_options(rules) if rules else None,
            LimitBreaks=0,
            EngraveOptions=None,
            EngraveCeiling=0,
            JewelSlots=None,
        )
        evolved.add(target["Id"])
        ranks[str(rarity + 1)] += 1
    if evolved:
        # The random result can have a different equipment type.
        detach_selected(user["Characters"], evolved)
        detach_presets(db, evolved)
        db.executemany(
            "DELETE FROM weapon_option_proposals WHERE item_id=?", ((i,) for i in evolved)
        )
        record = profile["UserRecord"]
        counts = record.setdefault("ComposeWeaponCount", {})
        if not isinstance(counts, dict) or not integer(record.get("Cas"), MAX_REVISION - 1):
            raise ValueError("Invalid saved mystery evolution record")
        for rank, gain in ranks.items():
            if not integer(counts.get(rank, 0), MAX_REVISION - gain):
                raise ValueError("Invalid saved mystery evolution count")
            counts[rank] = counts.get(rank, 0) + gain
        record["Cas"] += 1
    return len(evolved)


def compose(account, route, body, operation_id):
    groups = groups_for(route, body)
    if (
        account.needs_prologue()
        or not isinstance(operation_id, str)
        or not 1 <= len(operation_id) <= 200
    ):
        raise ValueError("Invalid mystery evolution session")
    encoded = json.dumps(sorted([g[0], *sorted(g[1:])] for g in groups), separators=(",", ":"))
    db = account.db
    with db:
        db.execute("BEGIN IMMEDIATE")
        profile = account.profile()
        user = profile["User"]
        previous = db.execute(
            "SELECT route,request,succeeded FROM mystery_evolution_requests WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if previous:
            if previous[:2] != (route, encoded):
                raise ValueError("Mystery evolution request identity has a different selection")
            succeeded = previous[2]
        else:
            if not integer(user.get("Cas"), MAX_REVISION - 1):
                raise ValueError("Invalid saved user revision")
            day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            forge = catalog(account.references.read_bytes("static_data_get.bin"), day)
            succeeded = apply_groups(db, profile, groups, forge)
            save_profile(db, profile)
            db.execute(
                "INSERT INTO mystery_evolution_requests VALUES(?,?,?,?)",
                (operation_id, route, encoded, succeeded),
            )
    result = {"User": user, "UserRecord": profile["UserRecord"]}
    if route == MANUAL:
        result["Succeeded"] = bool(succeeded)
    return result
