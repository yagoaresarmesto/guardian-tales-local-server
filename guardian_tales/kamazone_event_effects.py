# SPDX-License-Identifier: Apache-2.0
"""Local special-event effects and native nullable artifact replacement lists."""

from . import kamazone_silver
from .village import integer

HP_SCALE = 10000
LIMIT = 8
SUPPORTED = frozenset(
    (
        "None",
        "GetCoin",
        "LoseCoin",
        "HealAll",
        "HealRandomOne",
        "Revive",
        "DamageAll",
        "DamageRandomOne",
        "LoseArtifact",
        "LoseRandomArtifact",
        "LoseArtifactByIdAll",
        "GetArtifactByRarity",
        "GetArtifactById",
        "GetArtifactByIdAll",
        "GetCurse",
        "GetCurseById",
        "ProgressInSeason",
        "ProgressInChallenge",
        "ConcludeByWeight",
    )
)


def result(kind, targets=(), values=()):
    return dict(Type=kind, Targets=list(targets), Values=list(values))


def ids(value):
    return [row["Id"] for row in value["artifacts"]]


def remove_artifacts(value, indices):
    indices = set(indices)
    value["artifacts"] = [row for i, row in enumerate(value["artifacts"]) if i not in indices]
    for row in value["artifacts"]:
        row["EliminateArtifact"] += len(indices)


def tick(value, field, count=1):
    for row in value["artifacts"]:
        row[field] = min(0x7FFFFFFF, row[field] + count)


def apply(value, data, kind, args, owned, rng, visit):
    args = args or []
    if kind == "None":
        return result(kind)
    if kind == "GetCoin":
        return result(kind, values=[kamazone_silver.collect(value, args[0], data["artifacts"])])
    if kind == "LoseCoin":
        amount = args[0]
        if not integer(amount) or amount > value["silver_coin"]:
            raise ValueError("Not enough local Kama-ZONE silver coins")
        value["silver_coin"] -= amount
        return result(kind, values=[amount])
    if kind.startswith(("Heal", "Damage")) or kind == "Revive":
        hps = {str(i): value["hps"].get(str(i), HP_SCALE) for i in sorted(owned)}
        targets = [i for i, hp in hps.items() if (hp == 0 if kind == "Revive" else hp > 0)]
        if kind == "Revive":
            targets = rng.sample(targets, min(args[0], len(targets)))
        elif kind.endswith("RandomOne"):
            targets = rng.sample(targets, min(1, len(targets)))
        values = []
        for ident in targets:
            before = hps[ident]
            # The retained text specifies a count, not revived HP. Match the
            # shelter trial's explicit full-HP revival policy. Damage may defeat.
            after = (
                HP_SCALE
                if kind == "Revive"
                else max(
                    0,
                    min(
                        HP_SCALE, before + (-1 if kind.startswith("Damage") else 1) * args[0] * 100
                    ),
                )
            )
            value["hps"][ident] = after
            values.append(abs(after - before))
        # Native All effects render one description, while RandomOne/Revive
        # render individual character rows on the 10,000-unit HP scale.
        if kind.endswith("All"):
            return result(kind, values=[args[0] * 100])
        return result(kind, map(int, targets), values)
    if kind.startswith("Lose"):
        inventory = ids(value)
        if kind == "LoseRandomArtifact":
            removed = rng.sample(range(len(inventory)), min(args[0], len(inventory)))
        elif kind == "LoseArtifactByIdAll":
            removed = [i for i, ident in enumerate(inventory) if ident in args]
        else:
            removed = []
            for ident in args:
                match = next(
                    (i for i, item in enumerate(inventory) if item == ident and i not in removed),
                    None,
                )
                if match is not None:
                    removed.append(match)
        targets = [inventory[i] for i in removed]
        remove_artifacts(value, removed)
        return result(kind, targets)
    if kind.startswith("GetArtifact") or kind.startswith("GetCurse"):
        if kind == "GetArtifactByRarity":
            pool = [i for i in data["lootable"] if data["artifacts"][i].get("Rarity") in args]
        elif kind == "GetCurse":
            pool = list(data["curses"])
        else:
            pool = args
        if not pool:
            raise ValueError("No preserved seasonal artifact/curse matches this event")
        if kind.endswith("All"):
            targets = list(pool)
        elif kind == "GetCurse":
            targets = [rng.choice(pool) for _ in range(args[0])]
        else:
            targets = [rng.choice(pool)]
        key = "pending_curses" if kind.startswith("GetCurse") else "pending_artifacts"
        visit[key].extend(targets)
        return result(kind, targets)
    raise ValueError("Unsupported local Kama-ZONE event effect: " + kind)


def nullable_list(value):
    return value is None or (
        isinstance(value, list) and len(value) <= 24 and all(i is None or integer(i) for i in value)
    )


def grant(value, visit, request):
    for suffix, pending, inventory in (
        ("Artifact", visit["pending_artifacts"], value["artifacts"]),
        ("Curse", visit["pending_curses"], value["curses"]),
    ):
        offered = request.get("Loot" + suffix + "Ids")
        discard = request.get("Discard" + suffix + "Indices")
        offered = [None] * len(pending) if offered is None else offered
        discard = [None] * len(pending) if discard is None else discard
        if len(offered) != len(pending) or len(discard) != len(pending):
            raise ValueError("Event loot/replacement lists must match the offered rewards")
        for expected, ident, index in zip(pending, offered, discard):
            if ident is None:
                if index is not None:
                    raise ValueError("Declining a reward cannot discard an existing artifact/curse")
                continue
            if ident != expected:
                raise ValueError("Event loot contains an unoffered artifact/curse")
            add_reward(inventory, ident, index, artifact=suffix == "Artifact")


def add_reward(inventory, ident, index, *, artifact):
    if index is not None and not 0 <= index < len(inventory):
        raise ValueError("Invalid artifact/curse replacement index")
    if index is None and len(inventory) >= LIMIT:
        raise ValueError("Replace or decline the new artifact/curse at the native limit")
    row = dict(Id=ident, Shelter=0, Battle=0, EliminateArtifact=0) if artifact else ident
    if index is None:
        inventory.append(row)
    else:
        inventory[index] = row
        if artifact:
            for i, other in enumerate(inventory):
                if i != index:
                    other["EliminateArtifact"] = min(0x7FFFFFFF, other["EliminateArtifact"] + 1)
