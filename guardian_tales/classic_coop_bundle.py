# SPDX-License-Identifier: Apache-2.0
"""Build the local Challenge card from an externally supplied 3.57.0 bundle."""

import argparse
from copy import copy
from pathlib import Path

PREFAB = "assets/ui s3/prefabs/lobby/contentsbook.prefab"
CARD_ID = 7456028189047330380
EXPEDITION_LABEL_ID = -6839748398387429269
CONTROLLER_ID = 284637481322918840
HERO_TOWER_ART_ID = 7936583553878559809
DEFENSE_RESULT = "assets/ui s3/prefabs/stage/coop/coopdefence result.prefab"
COOP_RESULT = "assets/ui s3/prefabs/stage/base/coopresult.prefab"


def pointer(path_id):
    return {"m_FileID": 0, "m_PathID": path_id}


def components(game_object):
    return [value["component"] for value in game_object["m_Component"]]


def child_objects(objects, game_object):
    transform = objects[components(game_object)[0]["m_PathID"]].read_typetree()
    children = {}
    for child in transform["m_Children"]:
        child_transform = objects[child["m_PathID"]].read_typetree()
        obj = objects[child_transform["m_GameObject"]["m_PathID"]]
        children[obj.read_typetree()["m_Name"]] = obj
    return children


def clone(objects, original, path_id, tree):
    if path_id in objects:
        raise ValueError("Classic Co-op object ID already in use")
    cloned = copy(original)
    cloned.path_id = path_id
    cloned.save_typetree(tree)
    objects[path_id] = cloned


def build(source, output):
    import UnityPy

    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("Use a new output path. The original bundle must be kept.")
    env = UnityPy.load(str(source))
    prefab = env.container[PREFAB].deref()
    objects = prefab.assets_file.objects
    card = objects[CARD_ID].read_typetree()
    donor = objects[CONTROLLER_ID]
    controller = donor.read_typetree()
    if (
        card["m_Name"] != "EmptyItem"
        or controller["luaControllerName"] != "Frontend/BingoMachineControl"
    ):
        raise ValueError("Expected the unmodified 3.57.0 Challenge prefab")
    new_controller_id, new_label_id = 303050001, 303050002
    controller["m_GameObject"] = pointer(CARD_ID)
    controller["luaControllerName"] = "Frontend/LocalClassicCoop"
    for field, value in controller.items():
        if field.startswith("m_"):
            continue
        if isinstance(value, dict) and "m_PathID" in value:
            controller[field] = pointer(0)
        elif isinstance(value, list):
            controller[field] = []
    children = child_objects(objects, card)
    # Awake gathers line renderers and mirrors the ball root in RTL. Both
    # references can use the card's existing decorative stripe.
    stripe_transform = components(children["BottomBox"].read_typetree())[0]
    controller["linesTransform"] = stripe_transform
    controller["ballRootTransform"] = stripe_transform
    clone(objects, donor, new_controller_id, controller)
    card["m_Component"].append({"component": pointer(new_controller_id)})
    objects[CARD_ID].save_typetree(card)

    deco_object = children["EmptyDeco"]
    deco = deco_object.read_typetree()
    label_object = objects[EXPEDITION_LABEL_ID].read_typetree()
    label_donor = next(
        objects[ref["m_PathID"]]
        for ref in components(label_object)
        if objects[ref["m_PathID"]].type.name == "MonoBehaviour"
        and "mFontSize" in objects[ref["m_PathID"]].read_typetree()
    )
    label = label_donor.read_typetree()
    label.update(
        m_GameObject=pointer(deco_object.path_id),
        mText="Classic Co-op\nFire Defense (Easy)\nSolo practice",
        mPivot=4,
        mWidth=216,
        mHeight=106,
        mDepth=50,
        mAlignment=2,
        mFontSize=19,
    )
    clone(objects, label_donor, new_label_id, label)
    deco["m_Component"] = [deco["m_Component"][0], {"component": pointer(new_label_id)}]
    deco_object.save_typetree(deco)
    label_transform = objects[components(deco)[0]["m_PathID"]]
    positioned = label_transform.read_typetree()
    positioned["m_LocalPosition"]["y"] = -195.0
    label_transform.save_typetree(positioned)

    def sprite(name):
        return objects[components(children[name].read_typetree())[1]["m_PathID"]]

    background = sprite("Box")
    original_background = background.read_typetree()
    art = objects[HERO_TOWER_ART_ID].read_typetree()
    art["m_GameObject"] = original_background["m_GameObject"]
    background.save_typetree(art)
    stripe = sprite("BottomBox")
    stripe_data = stripe.read_typetree()
    stripe_data["mColor"] = {"r": 0.34, "g": 0.67, "b": 0.96, "a": 1.0}
    stripe.save_typetree(stripe_data)

    bundle_object = next(obj for obj in objects.values() if obj.type.name == "AssetBundle")
    bundle = bundle_object.read_typetree()
    entry = next(value for name, value in bundle["m_Container"] if name == PREFAB)
    preorder = bundle["m_PreloadTable"]
    start, end = entry["preloadIndex"], entry["preloadIndex"] + entry["preloadSize"]
    additional = [
        pointer(new_controller_id),
        pointer(new_label_id),
        controller["m_Script"],
        art["mAtlas"],
    ]
    entry["preloadIndex"] = len(preorder)
    entry["preloadSize"] += len(additional)
    preorder.extend(preorder[start:end] + additional)
    bundle_object.save_typetree(bundle)
    output.write_bytes(env.file.save(packer="lz4"))


def add_defense_result(source, base, output):
    import UnityPy

    if output.exists():
        raise ValueError("Use a new output path. Keep the preserved stage bundles.")
    env = UnityPy.load(str(source))
    base_env = UnityPy.load(str(base))
    base_obj = next(obj for obj in base_env.objects if obj.type.name == "AssetBundle")
    coop_obj = next(obj for obj in env.objects if obj.type.name == "AssetBundle")
    base_data = base_obj.read_typetree()
    coop_data = coop_obj.read_typetree()
    if (
        base_data["m_AssetBundleName"] != "ui/stage/base"
        or coop_data["m_AssetBundleName"] != "ui/stage/coop"
        or any(name == DEFENSE_RESULT for name, _ in coop_data["m_Container"])
    ):
        raise ValueError("Expected the matching unmodified stage bundles")
    result = next(entry for name, entry in base_data["m_Container"] if name == COOP_RESULT)

    base_file = base_obj.assets_file
    base_link = copy(base_file.externals[0])
    base_link.path = f"archive:/{base_file.name}/{base_file.name}"
    externals = coop_obj.assets_file.externals
    file_ids = {entry.path: index for index, entry in enumerate(externals, start=1)}

    def remap(ref):
        file_id = ref["m_FileID"]
        external = base_file.externals[file_id - 1] if file_id else base_link
        if external.path not in file_ids:
            externals.append(copy(external))
            file_ids[external.path] = len(externals)
        return {"m_FileID": file_ids[external.path], "m_PathID": ref["m_PathID"]}

    preload = coop_data["m_PreloadTable"]
    at = result["preloadIndex"]
    size = result["preloadSize"]
    alias = {
        "preloadIndex": len(preload),
        "preloadSize": size,
        "asset": remap(result["asset"]),
    }
    preload.extend(remap(ref) for ref in base_data["m_PreloadTable"][at : at + size])
    coop_data["m_Container"].append((DEFENSE_RESULT, alias))
    coop_data["m_Dependencies"].append("ui/stage/base")
    coop_obj.save_typetree(coop_data)
    output.write_bytes(env.file.save(packer="lz4"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--result-from",
        type=Path,
        help="Alias the base result panel. SOURCE must then be the preserved ui/stage/coop bundle.",
    )
    args = parser.parse_args()
    if args.result_from:
        add_defense_result(args.source, args.result_from, args.output)
    else:
        build(args.source, args.output)
