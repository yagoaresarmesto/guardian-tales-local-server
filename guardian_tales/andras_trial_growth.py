# SPDX-License-Identifier: Apache-2.0
"""Experimental awakening and Eunha leader effects with Bianca's cut-in."""

import base64
import copy
import json
import math
import struct

ORIGIN = 488
EUNHA_LEADER = 20500542
LEADER = 20500488
LEADER_ACTION = "MythDokkaebi:AndrasTrial"
LEADER_CAST_ANIMATION = "weapon/twohand_role_cast"
BASE_NODES = 248
TOTAL_NODES = 300
TREE = "layout_snowflake_01_myth_local_andras"
SPECIALS = (995, 996, 997, 998, 999, 989)
MARKERS = (20350488, 20360488, 20370488, 20300488, 20320488)
TABLES = (
    "charactertreeconfig",
    "awakeningtreenodes",
    "awakeningnodedata",
    "options",
    "battleactions",
    "battleactions-bin",
    "buffs",
)


def one(rows, key, value):
    matches = [row for row in rows if isinstance(row, dict) and row.get(key) == value]
    if len(matches) != 1:
        raise ValueError(f"Andras growth requires one {key}={value}")
    return matches[0]


def activated_tree(encoded):
    """Retain every original bit and prefix, activating only the appended branch."""
    if encoded is None or encoded == "":
        prefix, data = struct.pack("<I", 490), b""
    else:
        if not isinstance(encoded, str) or len(encoded) > 2048 or encoded.count("|") != 1:
            raise ValueError("Invalid original Andras awakening tree")
        try:
            prefix, data = (base64.b64decode(part, validate=True) for part in encoded.split("|"))
        except ValueError as error:
            raise ValueError("Invalid original Andras awakening encoding") from error
        if len(prefix) != 4 or len(data) > 125:
            raise ValueError("Invalid original Andras awakening mask")
    flags = bytearray(data.ljust((TOTAL_NODES + 7) // 8, b"\0"))
    for index in range(BASE_NODES, TOTAL_NODES):
        flags[index // 8] |= 1 << (index % 8)
    return base64.b64encode(prefix).decode() + "|" + base64.b64encode(flags).decode()


def scale(row, fields, factor):
    for field in fields:
        value = row.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid Andras growth coefficient: {row.get('Name')}.{field}")
        row[field] = round(value * factor, 9)


def marker(ident, suffix, title, description, parameters, values, types):
    return dict(
        Id=ident,
        Name="local_andras_myth_" + suffix,
        Class="BattleActionParameter",
        IsVisible=False,
        AwakenTitle=title,
        AwakenDescription=description,
        DescKey=description,
        DescParam=parameters,
        DescParamType=types,
        **values,
    )


def overlay(tables):
    try:
        return _overlay(tables)
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError("Invalid Andras growth static-data contract") from error


def _overlay(tables):
    from .andras_trial_static import binary_name_hash, binary_rows, pack_rows, same_definition

    required = {*TABLES, "awakeningnodelayout", "awakeningnodelayout_client"}
    if not required <= tables.keys():
        raise ValueError("Andras growth requires the matching awakening and combat tables")
    values = {name: json.loads(tables[name][1]) for name in required - {"battleactions-bin"}}
    configs, trees = values["charactertreeconfig"], values["awakeningtreenodes"]
    config = one(configs, "OriginId", ORIGIN)
    template = one(configs, "OriginId", 350)
    layouts = values["awakeningnodelayout"]
    clients = values["awakeningnodelayout_client"]
    original_name, myth_name = "layout_snowflake_01", "layout_snowflake_01_myth"
    if (
        config.get("TreeLayoutName") != original_name
        or template.get("TreeLayoutName") != myth_name
        or len(config.get("SpecialNodes", [])) != 30
        or template.get("SpecialNodes", [])[-6:] != list(SPECIALS)
        or len(layouts.get(original_name, [])) != BASE_NODES
        or len(layouts.get(myth_name, [])) != TOTAL_NODES
        or clients[original_name]["Circles"] != clients[myth_name]["Circles"][:30]
        or TREE in trees
    ):
        raise ValueError("Andras growth requires the compatible original and Myth snowflake trees")
    original = trees[config["AwakeningTreeName"]]
    template_nodes = trees[template["AwakeningTreeName"]]
    if (
        len(original) != BASE_NODES
        or len(template_nodes) != TOTAL_NODES
        or any(type(n) is not int or n % 1000 != i for i, n in enumerate(template_nodes))
        or any(type(n) is not int or n % 1000 != i for i, n in enumerate(original))
    ):
        raise ValueError("Invalid Andras growth node indices")
    trees[TREE] = original + template_nodes[BASE_NODES:]
    config.update(
        TreeLayoutName=myth_name,
        AwakeningTreeName=TREE,
        SpecialNodes=config["SpecialNodes"] + list(SPECIALS),
    )

    options = values["options"]
    leader = one(options, "Id", EUNHA_LEADER)
    if (
        leader.get("Class") != "MythBattleAction"
        or leader.get("BattleActionName") != "MythDokkaebi"
    ):
        raise ValueError("Andras growth requires the stock Eunha Myth leader skill")
    if any(row.get("Id") == LEADER for row in options):
        raise ValueError("Andras leader option identifier collides with the content")
    local_leader = copy.deepcopy(leader)
    local_leader.update(Id=LEADER, BattleActionName=LEADER_ACTION)
    options.append(local_leader)
    names = {
        "local_andras_myth_" + suffix for suffix in ("manual", "role", "weapon", "chain", "special")
    }
    if any(row.get("Id") in MARKERS or row.get("Name") in names for row in options):
        raise ValueError("Andras growth option identifiers collide with the content")
    party = one(options, "Id", 10820)
    party_buff = one(values["buffs"], "Id", 10820)
    if (
        party.get("Class") != "Buff"
        or party.get("BuffId") != 10820
        or party_buff.get("ClassName") != "ProjectileAttackScale"
        or party_buff.get("AttackScaleAdd") != 0.001
    ):
        raise ValueError("Andras growth requires Eunha's per-mille ranged party buff")
    nodes = values["awakeningnodedata"]["NodeOptions"]
    if any(row.get("OriginId") == ORIGIN and row.get("Id") in SPECIALS for row in nodes):
        raise ValueError("Andras already has experimental Myth awakening options")
    for ident, option in zip(SPECIALS, (10820, *MARKERS)):
        nodes.append(
            dict(
                Id=ident,
                IsSuper=True,
                OptionId=option,
                OriginId=ORIGIN,
                OptionLevel=50 if ident == 995 else 0,
            )
        )

    # Inspecting an open center can still request its stock cost definition.
    costs = values["awakeningnodedata"]["ResourcesToOpenNode"]
    source_costs = [row for row in costs if row.get("OriginId") == 542]
    for ident in SPECIALS:
        cost_id = 20000 + ident
        if any(row.get("OriginId") == ORIGIN and row.get("Id") == cost_id for row in costs):
            raise ValueError("Andras growth awakening costs collide with existing content")
        costs.append(dict(one(source_costs, "Id", cost_id), OriginId=ORIGIN))

    actions = values["battleactions"]
    eunha = one(actions, "Name", "MythDokkaebi")
    bianca = one(actions, "Name", "GraphMyth:SuccubusNoble")
    if (
        eunha.get("UseScript") is not True
        or eunha.get("ScriptName") != "Myth"
        or eunha.get("MediaName") != {"Default": "dokkaebi_myth"}
        or bianca.get("MediaName") != {"Default": "succubus_noble_myth"}
        or bianca.get("GraphName") != "graph_hero/succubus_noble:MythSuccubusNoble"
        or eunha.get("CutInDuration") != bianca.get("CutInDuration")
        or any(row.get("Name") == LEADER_ACTION for row in actions)
    ):
        raise ValueError("Andras leader requires compatible stock Eunha/Bianca cut-ins")
    local_action = copy.deepcopy(eunha)
    local_action.update(Name=LEADER_ACTION, MediaName=copy.deepcopy(bianca["MediaName"]))
    # The matching preserved Bianca graph's anim_cast resource uses this shared
    # weapon animation. Retain Eunha's controller, track and gameplay timings;
    # importing Bianca's entire graph would also change the damage execution.
    one(local_action.get("AnimationInfo", []), "Name", "cast")["Animation"] = LEADER_CAST_ANIMATION
    changed = {}
    for name in (
        "ManualDemonSlayer:First",
        "ManualDemonSlayer:Second",
        "ManualDemonSlayer:Third",
        "RoleDemonSlayer",
    ):
        row = one(actions, "Name", name)
        scale(row, ("ModifierBase",), 1.1)
        changed[name] = row
    weapon = one(actions, "Name", "CwpDemonSlayer")
    scale(weapon, ("ModifierBase", "ModifierAdd"), 1.1)
    changed[weapon["Name"]] = weapon
    chain = one(actions, "Name", "BasicSupport:DemonSlayer")
    hits = chain.get("HitDpsMultipliers")
    if hits != [0.3, 0.3, 0.3, 0.3, 1.8]:
        raise ValueError("Andras growth requires the original five-hit chain")
    chain["HitDpsMultipliers"] = [round(value * 1.2, 9) for value in hits]
    changed[chain["Name"]] = chain
    chain_option = one(options, "Id", 300488)
    if (
        chain_option.get("Class") != "BattleAction"
        or chain_option.get("BattleActionName") != chain["Name"]
    ):
        raise ValueError("Andras growth requires the original chain option")
    # The ability UI hides a base chain for Myth heroes without this link,
    # independently of the battle action's actual damage implementation.
    chain_option["MythOptionId"] = MARKERS[3]
    special = one(options, "Id", 320488)
    if special.get("OverrideModifier") != 2.8:
        raise ValueError("Andras growth requires the original last-hit enhancement")
    scale(special, ("OverrideModifier",), 1.1)
    buffs = values["buffs"]
    for ident, field in ((3204880, "AttackScaleBase"), (3204881, "DefenseScaleBase")):
        row = one(buffs, "Id", ident)
        if row.get(field) != 0.3 or row.get("Duration") != 5:
            raise ValueError("Andras growth requires the original Bitter Cold buffs")
        row.update({field: 0.35, "Duration": 6})

    # These options describe the active static changes. All new nodes are open;
    # they do not claim an unsupported runtime Myth-parameter hook in Andras.
    for ident, suffix, title in zip(
        MARKERS[:3], ("manual", "role", "weapon"), ("manual_option", "role_option", "cwp")
    ):
        options.append(
            marker(
                ident,
                suffix,
                "dokkaebi_myth_" + title + "_awaken",
                "option_atk_scale" if suffix != "weapon" else "option_super_skill_scale",
                ["Increase"],
                {"Increase": 10},
                ["int"],
            )
        )
    options.append(
        marker(
            MARKERS[3],
            "chain",
            "dokkaebi_myth_support_skill_awaken",
            "demon_slayer_support_skill_desc",
            ["HitDpsMultipliers"],
            {"HitDpsMultipliers": chain["HitDpsMultipliers"]},
            ["sumPercent"],
        )
    )
    options.append(
        marker(
            MARKERS[4],
            "special",
            "dokkaebi_myth_special_option_awaken",
            "demon_slayer_special_option_desc_v2.53",
            ["UseLeftCondition", "0:buffDuration", "0:buffAtkScale"],
            {"UseLeftCondition": 3, "BuffName": "buff_demon_slayer_special_option"},
            ["int", "multiple", "multiple"],
        )
    )

    binary = binary_rows(tables["battleactions-bin"][1], require_id=False)
    original_actions = json.loads(tables["battleactions"][1])
    indexed = {json.loads(raw)["Name"]: json.loads(raw) for _, _, raw in binary}
    if (
        len(indexed) != len(binary)
        or indexed.keys() != {row["Name"] for row in original_actions}
        or any(not same_definition(row, indexed[row["Name"]]) for row in original_actions)
    ):
        raise ValueError("Andras growth combat JSON and binary definitions disagree")
    updated_rows = [
        (
            ident,
            name_hash,
            (
                json.dumps(
                    changed[json.loads(raw)["Name"]], ensure_ascii=False, separators=(",", ":")
                ).encode()
                if json.loads(raw)["Name"] in changed
                else raw
            ),
        )
        for ident, name_hash, raw in binary
    ]
    # The native dictionary looks up the full alias through its index hash.
    # LuaMythActionAddOn separately opens the script named by payload["Name"],
    # without stripping alias suffixes. Keep that dispatch name stock, while
    # the JSON catalog exposes the alias used by the private leader option.
    script_action = dict(local_action, Name=eunha["Name"])
    alias_hash = binary_name_hash(LEADER_ACTION)
    if alias_hash in {row[1] for row in binary}:
        raise ValueError("Andras leader alias collides with the native action index")
    updated_rows.append(
        (
            max(r[0] for r in binary) + 1,
            alias_hash,
            json.dumps(script_action, ensure_ascii=False, separators=(",", ":")).encode(),
        )
    )
    updated_binary = pack_rows(updated_rows)
    actions.append(local_action)
    result = {
        name: json.dumps(values[name], ensure_ascii=False, separators=(",", ":"))
        for name in TABLES
        if name != "battleactions-bin"
    }
    result["battleactions-bin"] = updated_binary
    return result
