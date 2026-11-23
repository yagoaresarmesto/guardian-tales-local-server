# SPDX-License-Identifier: Apache-2.0
"""Run-local artifact retention and starting benefits for Kama-ZONE challenges."""

from . import kamazone, kamazone_practice, kamazone_silver
from . import kamazone_event_effects as effects
from .village import integer

PICK = "/kamazonland/pick-aids"
AIDS = {"ArtifactId": "ArtifactAid", "CurseId": "CurseAid"}


def selected(references, source, season_id):
    practice = kamazone_practice.effective(references, source, season_id)
    if not practice:
        return {}
    specs, _ = kamazone_practice.catalog(source, season_id)
    bonuses = {}
    for key, level in practice["benefits"].items():
        spec = specs[int(key)]
        kind = spec.get("EffectType")
        if kind in ("ArtifactKeep", *AIDS.values()):
            bonuses[kind] = True
        elif kind == "CoinBonusBattle":
            amounts = spec.get(f"EffectValue{level}")
            if not isinstance(amounts, list) or len(amounts) != 3 or not all(map(integer, amounts)):
                raise ValueError("Invalid Kama-ZONE battle silver benefit")
            for tier, amount in zip(("Normal", "Elite", "Boss"), amounts):
                bonuses[tier] = bonuses.get(tier, 0) + amount
        elif kind == "SilverCoinAid":
            amount = spec.get(f"EffectValue{level}")
            if not isinstance(amount, list) or len(amount) != 1 or not integer(amount[0]):
                raise ValueError("Invalid starting silver benefit")
            bonuses[kind] = bonuses.get(kind, 0) + amount[0]
    return bonuses


def valid(value):
    keeping = value["keeping_artifact_id"]
    aids = value["opening_aids"]
    return (
        (
            keeping is None
            or integer(keeping, minimum=1)
            and not value["active"]
            and keeping in effects.ids(value)
        )
        and isinstance(aids, dict)
        and aids.keys() <= AIDS.keys()
        and all(integer(choice) for choice in aids.values())
    )


def keep(value, ident, source, bonuses):
    if ident is not None:
        if "ArtifactKeep" not in bonuses or ident not in effects.ids(value):
            raise ValueError("Select an owned artifact with the artifact keep benefit")
        spec = kamazone.artifact_specs(source)[ident]
        if not integer(spec.get("Rarity")) or spec["Rarity"] in (4, 5):
            raise ValueError("This artifact rarity cannot be retained")
    value["keeping_artifact_id"] = ident


def start(value, bonuses, source):
    kept = value["keeping_artifact_id"]
    if kept is not None and "ArtifactKeep" in bonuses:
        effects.add_reward(value["artifacts"], kept, None, artifact=True)
    value.update(
        keeping_artifact_id=None,
        opening_aids={field: 0 for field, benefit in AIDS.items() if benefit in bonuses},
    )
    specs = kamazone.artifact_specs(source) if value["artifacts"] else {}
    kamazone_silver.collect(value, bonuses.get("SilverCoinAid", 0), specs)


def validate_pick(request):
    if (
        not isinstance(request, dict)
        or request.keys() != AIDS.keys()
        or all(i is None for i in request.values())
        or any(i is not None and not integer(i, minimum=1) for i in request.values())
    ):
        raise ValueError("Select a starting artifact or curse with a seasonal ID")


def pick(value, source, season_id, request, starting):
    if not value["active"] or value["floor"] != 1 or value["current_node_id"] != starting:
        raise ValueError("Starting aids are available only at the beginning of a challenge")
    season = kamazone.one(kamazone.mode_data(source)["Seasons"], "Id", season_id)
    specs = kamazone.artifact_specs(source)
    for field, ident in request.items():
        if ident is None:
            continue
        previous = value["opening_aids"].get(field)
        if previous == ident:
            continue
        artifact = field == "ArtifactId"
        pool = season.get("Artifacts" if artifact else "ArtifactsCurse", [])
        spec = specs.get(ident, {})
        if (
            previous != 0
            or ident not in pool
            or ident in season.get("ArtifactsException", [])
            or spec.get("Kind") != ("Normal" if artifact else "Curse")
            or artifact
            and (spec.get("Lootable") is not True or not integer(spec.get("Rarity"), maximum=2))
        ):
            raise ValueError("This aid is unavailable or has already been chosen")
        effects.add_reward(
            value["artifacts" if artifact else "curses"], ident, None, artifact=artifact
        )
        value["opening_aids"][field] = ident


def progress(value):
    aids = value["opening_aids"]
    return dict(
        KeepingArtifactId=value["keeping_artifact_id"],
        CanPickArtifactAid=value["active"] and aids.get("ArtifactId") == 0,
        CanPickCurseAid=value["active"] and aids.get("CurseId") == 0,
    )
