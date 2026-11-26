# SPDX-License-Identifier: Apache-2.0
"""Append an isolated Head Hunter Myth definition over effective server tables."""

import copy
import hashlib
import json
from functools import lru_cache

from guardian_tales.content.static_cache import prepare_static
from guardian_tales.modes.guild.raid_custom import binary_name_hash
from guardian_tales.modes.guild.raid_static import compress, decode, digest, records
from guardian_tales.settlement.village import integer

from .andras_trial_static import binary_rows, pack_rows, same_definition

SOURCE = 9060604
VARIANT = 9060605
OPTION = 9310488
CLASS = "demon_slayer_hh_trial"
ACTION = "RoleDemonSlayer:HeadHunterTrial"
TABLE = "head_hunter_trial_grants"
MAX_GRANTS = 32


def one(rows, key, value):
    found = [r for r in rows if isinstance(r, dict) and r.get(key) == value]
    if len(found) != 1:
        raise ValueError(f"Head Hunter requires one {key}={value}")
    return found[0]


@lru_cache(maxsize=2)
def weapon_spec(body):
    items = json.loads(records(decode(body))[1]["items"][1])
    return weapon_spec_from_items(items)


def weapon_spec_from_items(items):
    original = one(items, "Id", SOURCE)
    if any(
        original.get(k) != v
        for k, v in {
            "Name": "cwp_demonslayer_epic",
            "Type": "weapon",
            "WeaponType": "staff",
            "Rarity": 4,
            "OriginRarity": 4,
            "ExclusiveCharacterId": 488,
            "NameWithoutRarity": "cwp_demonslayer",
            "SuperBattleAction": "CwpDemonSlayer",
        }.items()
    ) or any(r.get("Id") == VARIANT or r.get("Name") == "local_head_hunter_myth" for r in items):
        raise ValueError("The original matching Head Hunter and an unused trial ID are required")
    result = copy.deepcopy(original)
    result.update(
        Id=VARIANT,
        Name="local_head_hunter_myth",
        Rarity=5,
        ExclusiveNumber=2,
        Limited=True,
        Summonable=False,
        Composable=False,
    )
    result.pop("EvolveTo", None)
    selected = [r for r in result["StaticOptions"] if r.get("OptionId") == 310488]
    if len(selected) != 1:
        raise ValueError("Head Hunter requires its original exclusive option")
    selected[0]["OptionId"] = OPTION
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def active_spec(db, references, *, body=None, items=None):
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone():
        return None
    grants = db.execute(
        f"SELECT inventory_id,owner_id,source_sha256 FROM {TABLE} WHERE removed_at IS NULL"
    ).fetchall()
    if len(grants) > MAX_GRANTS:
        raise ValueError("Too many Head Hunter trial grants")
    saved = db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()
    if not saved:
        return None
    user = json.loads(saved[0])["User"]
    owned = {r["Id"]: r for r in user["ItemWeapons"]}
    present = []
    for ident, owner, source_sha in grants:
        if ident not in owned:
            continue
        if (
            owner != user["Id"]
            or owned[ident].get("ItemId") != VARIANT
            or owned[ident].get("Amount") != 1
        ):
            raise ValueError("Head Hunter grant does not match the saved owner/item")
        present.append(source_sha)
    if not present:
        return None
    if body is None:
        body = references.read_bytes("static_data_get.bin")
    source_hash = hashlib.sha256(body).hexdigest()
    if any(sha != source_hash for sha in present):
        raise ValueError("Head Hunter trial belongs to another content pack")
    return weapon_spec(body) if items is None else weapon_spec_from_items(items)


@lru_cache(maxsize=2)
def prepare(body, encoded_spec):
    lines, tables = records(decode(body))
    names = ("items", "options", "heroes", "heroes2", "battleactions", "battlestyles")
    if not {*names, "battleactions-bin", "__checksum__"} <= tables.keys():
        raise ValueError("Head Hunter requires matching hero/option/combat/style tables")
    values = {name: json.loads(tables[name][1]) for name in names}
    spec = json.loads(encoded_spec)
    if spec != json.loads(weapon_spec(body)):
        # The effective parent may already contain the Andras hero trial, but
        # the original weapon itself must still be identical.
        raise ValueError("Head Hunter trial definition differs from the effective source")
    values["items"].append(spec)
    original_option = one(values["options"], "Id", 310488)
    if any(
        original_option.get(k) != v
        for k, v in {
            "Name": "demon_slayer_cwp_option",
            "Class": "BattleActionParameter",
            "ConditionType": "CharacterOriginType",
            "CharacterOriginIds": [488],
            "AddModifierMultiplier": 0.2,
            "ReinforceCondition": 4,
        }.items()
    ):
        raise ValueError("Head Hunter requires the original four-crystal 20% bonus")
    if any(r.get("Id") == OPTION for r in values["options"]):
        raise ValueError("Head Hunter option ID is already used")
    option = copy.deepcopy(original_option)
    # OptionData is indexed by ID. Reusing the existing localization name lets
    # its parameterized description display 25% without adding language files.
    option.update(Id=OPTION, AddModifierMultiplier=0.25)
    values["options"].append(option)
    role = one(values["battleactions"], "Name", "RoleDemonSlayer")
    if role.get("CwpOptionId") != 310488 or role.get("UseScript") is not True:
        raise ValueError("Unsupported Andras role action")
    if any(r.get("Name") == ACTION for r in values["battleactions"]):
        raise ValueError("Head Hunter role alias already exists")
    modified = copy.deepcopy(role)
    modified.update(Name=ACTION, CwpOptionId=OPTION)
    values["battleactions"].append(modified)
    styles = values["battlestyles"]["BattleStyles"]
    style = copy.deepcopy(one(styles, "Name", "staff_demon_slayer"))
    if any(r.get("Class") == CLASS for r in styles):
        raise ValueError("Head Hunter battle class already exists")
    style.update(Name="staff_" + CLASS, Class=CLASS, ExclusiveNumber=2)
    for field in ("BattleActions", "ManualBattleActions", "ClassBattleActions"):
        style[field] = [ACTION if name == "RoleDemonSlayer" else name for name in style[field]]
    styles.append(style)
    heroes = [r for r in values["heroes"] if r.get("OriginId") == 488]
    if not heroes or any(r.get("Class") != "demon_slayer" for r in heroes):
        raise ValueError("Head Hunter requires the original Andras class")
    if any(r.get("Id") in {h["Id"] for h in heroes} for r in values["heroes2"]):
        raise ValueError("Andras already has an exclusive-weapon override")
    for hero in heroes:
        options = copy.deepcopy(hero["Options"])
        if not any(r.get("OptionId") == 310488 for r in options):
            options.append({"OptionId": 310488})
        values["heroes2"].append(
            {"Id": hero["Id"], "Class": CLASS, "ExclusiveNumber": 2, "Options": options}
        )
    rows = binary_rows(tables["battleactions-bin"][1], require_id=False)
    by_name = {json.loads(raw)["Name"]: json.loads(raw) for _, _, raw in rows}
    if "RoleDemonSlayer" not in by_name or not same_definition(role, by_name["RoleDemonSlayer"]):
        raise ValueError("Andras role JSON/binary definitions disagree")
    ident = max(r[0] for r in rows) + 1
    if not integer(ident):
        raise ValueError("Head Hunter role binary ID overflow")
    rows.append(
        (ident, binary_name_hash(ACTION), json.dumps(modified, separators=(",", ":")).encode())
    )
    updates = {
        name: json.dumps(values[name], ensure_ascii=False, separators=(",", ":"))
        for name in names
        if name != "heroes"
    }
    updates["battleactions-bin"] = pack_rows(rows)
    checksum = digest(
        b"local-head-hunter-v1\n"
        + tables["__checksum__"][1].encode()
        + json.dumps(updates, sort_keys=True).encode()
    )
    updates["__checksum__"] = checksum
    revision = max(r[2] for r in tables.values()) + 1
    if revision > 0x7FFFFFFF:
        raise ValueError("Head Hunter static revision overflow")
    from guardian_tales.modes.guild.raid_static import record_bytes

    for name, content in updates.items():
        at = tables[name][0]
        lines[at : at + 4] = [
            name + "\n",
            content + "\n",
            str(revision) + "\n",
            digest(record_bytes(name, content)) + "\n",
        ]
    return compress("".join(lines).encode()), checksum


def bootstrap_seed(db, references, filename, request, parent):
    if filename not in ("static_data_get.bin", "static_data_check.bin"):
        return parent(references, filename, request)
    spec = active_spec(db, references)
    if spec is None:
        return parent(references, filename, request)
    source = parent(references, "static_data_get.bin", request)
    body, checksum = prepare_static(references, prepare, source, spec)
    if filename == "static_data_get.bin":
        return body
    return json.dumps(
        {
            "UpToDate": isinstance(request, dict) and request.get("Checksum") == checksum,
            "Checksum": checksum,
            "QuitGameWhenStaticDataUpdateNeeded": False,
        }
    ).encode()
