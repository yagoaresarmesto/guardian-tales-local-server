# SPDX-License-Identifier: Apache-2.0
"""Seeded seasonal special events, persistent story threads and local choices."""

import copy
import hashlib
import json
import random
from functools import lru_cache

from . import kamazone, kamazone_silver
from . import kamazone_event_effects as effects
from .village import integer

CHOOSE = "/kamazonland/choice-special-event"
CLOSE = "/kamazonland/close-special-event"
ROUTES = (CHOOSE, CLOSE)


def defaults():
    return dict(
        events={},
        event_progress=dict(season={}, challenge={}),
        artifacts=[],
        silver_coin=0,
        known_events=[],
        known_choices=[],
        known_random=[],
    )


def upgrade(value):
    return dict(defaults(), **value) if isinstance(value, dict) else value


def reset(value):
    # Story memories and season threads survive a new challenge. Equipment, HP,
    # coins and challenge threads belong only to the explicitly replaced run.
    value.update(events={}, artifacts=[], silver_coin=0)
    value["event_progress"]["challenge"] = {}


def sequence(items, maximum=1024, nullable=False):
    return (
        isinstance(items, list)
        and len(items) <= maximum
        and all(
            (nullable and i is None) or integer(i, minimum=1, maximum=0x7FFFFFFF) for i in items
        )
    )


def valid_targets(ids):
    return sequence(ids, 128) and bool(ids) and len(ids) == len(set(ids))


def continuations(row, data, scope):
    target = row["next"]
    if isinstance(target, list):
        return target
    if not target:
        return []
    # Older files stored only the first target. Recover the other targets if
    # the last recorded choice directly identifies the same transition.
    if row["choices"]:
        choice = data["choices"].get(row["choices"][-1], {})
        effect = "ProgressInSeason" if scope == "season" else "ProgressInChallenge"
        for i in range(3, 0, -1):
            args = choice.get(f"EffectValue{i}")
            if choice.get(f"EffectType{i}") == effect and valid_targets(args) and args[0] == target:
                return args
    return [target]


def identifier(key):
    return (
        key.isascii() and key.isdecimal() and str(int(key)) == key and integer(int(key), minimum=1)
    )


def valid(value):
    if (
        not integer(value["silver_coin"], maximum=0x7FFFFFFF)
        or not isinstance(value["artifacts"], list)
        or len(value["artifacts"]) > effects.LIMIT
        or any(
            not isinstance(r, dict)
            or set(r) != {"Id", "Shelter", "Battle", "EliminateArtifact"}
            or not integer(r["Id"], minimum=1)
            or any(
                not integer(r[k], maximum=0x7FFFFFFF)
                for k in ("Shelter", "Battle", "EliminateArtifact")
            )
            for r in value["artifacts"]
        )
        or any(
            not sequence(value[k]) or len(set(value[k])) != len(value[k])
            for k in ("known_events", "known_choices", "known_random")
        )
        or not isinstance(value["event_progress"], dict)
        or set(value["event_progress"]) != {"season", "challenge"}
        or not isinstance(value["events"], dict)
        or len(value["events"]) > 128
    ):
        return False
    for progress in value["event_progress"].values():
        if not isinstance(progress, dict) or len(progress) > 128:
            return False
        for key, row in progress.items():
            if (
                not identifier(key)
                or not isinstance(row, dict)
                or set(row) != {"next", "choices"}
                or (not integer(row["next"]) and not valid_targets(row["next"]))
                or not sequence(row["choices"], 512)
            ):
                return False
    for key, row in value["events"].items():
        if (
            not identifier(key)
            or not isinstance(row, dict)
            or set(row)
            != {
                "event_id",
                "root",
                "choices",
                "choice_id",
                "random_id",
                "results",
                "pending_artifacts",
                "pending_curses",
                "closed",
                "close_hash",
            }
            or any(not integer(row[k], minimum=1) for k in ("event_id", "root"))
            or not sequence(row["choices"], 32)
            or not row["choices"]
            or len(set(row["choices"])) != len(row["choices"])
            or row["choice_id"] is not None
            and (not integer(row["choice_id"], minimum=1) or row["choice_id"] not in row["choices"])
            or row["random_id"] is not None
            and not integer(row["random_id"], minimum=1)
            or not sequence(row["pending_artifacts"], 24)
            or not sequence(row["pending_curses"], 24)
            or type(row["closed"]) is not bool
            or row["closed"]
            and row["choice_id"] is None
            or row["close_hash"] is not None
            and (
                not isinstance(row["close_hash"], str)
                or len(row["close_hash"]) != 64
                or any(c not in "0123456789abcdef" for c in row["close_hash"])
            )
            or not isinstance(row["results"], list)
            or len(row["results"]) > 8
        ):
            return False
        for r in row["results"]:
            if (
                not isinstance(r, dict)
                or set(r) != {"Type", "Targets", "Values"}
                or not isinstance(r["Type"], str)
                or r["Type"] not in effects.SUPPORTED
                or not sequence(r["Targets"], 1024)
                or not isinstance(r["Values"], list)
                or len(r["Values"]) > 1024
                or any(not integer(i, maximum=0x7FFFFFFF) for i in r["Values"])
            ):
                return False
    return True


@lru_cache(maxsize=2)
def catalog(source, season_id):
    mode = kamazone.mode_data(source)
    if any(
        not isinstance(mode.get(k), list)
        for k in ("SpecialEvents", "SpecialEventChoices", "Artifacts")
    ):
        raise ValueError("Missing preserved Kama-ZONE special-event definitions")
    season = kamazone.one(mode["Seasons"], "Id", season_id)
    if not isinstance(season.get("SpecialEvents"), list):
        raise ValueError("Missing seasonal Kama-ZONE special-event identities")
    events = {r["Id"]: r for r in mode["SpecialEvents"] if r["Id"] in season["SpecialEvents"]}
    choices = {r["Id"]: r for r in mode["SpecialEventChoices"] if r["EventId"] in events}
    randoms = {r["Id"]: r for r in mode.get("RandomConclusions", [])}
    artifacts = kamazone.artifact_specs(source)
    if len(events) != len(season["SpecialEvents"]) or any(
        not any(c["EventId"] == i for c in choices.values()) for i in events
    ):
        raise ValueError("Incomplete preserved Kama-ZONE event/choice catalog")
    excluded = set(season.get("ArtifactsException", []))
    return dict(
        events=events,
        choices=choices,
        randoms=randoms,
        artifacts=artifacts,
        curses=tuple(season.get("ArtifactsCurse", [])),
        lootable=tuple(
            i
            for i in season["Artifacts"]
            if i not in excluded
            and artifacts[i].get("Kind") == "Normal"
            and artifacts[i].get("Lootable") is True
        ),
    )


def matches(value, source, season_id, nodes):
    if value["artifacts"] and not set(effects.ids(value)) <= kamazone.artifact_specs(source).keys():
        return False
    if not any(
        value[k] for k in ("events", "known_events", "known_choices", "known_random")
    ) and not any(value["event_progress"].values()):
        return True
    data = catalog(source, season_id)
    by_id = {n["Id"]: n for n in nodes}
    if (
        not set(value["known_events"]) <= data["events"].keys()
        or not set(value["known_choices"]) <= data["choices"].keys()
        or not set(value["known_random"]) <= data["randoms"].keys()
    ):
        return False
    for scope, progress in value["event_progress"].items():
        if any(
            int(k) not in data["events"]
            or not set(continuations(r, data, scope)) <= data["events"].keys()
            or not set(r["choices"]) <= data["choices"].keys()
            for k, r in progress.items()
        ):
            return False
    for key, row in value["events"].items():
        if (
            int(key) not in by_id
            or by_id[int(key)]["Type"] != "Special"
            or row["event_id"] not in data["events"]
            or row["root"] not in data["events"]
            or any(
                i not in data["choices"] or data["choices"][i]["EventId"] != row["event_id"]
                for i in row["choices"]
            )
            or not set(row["pending_artifacts"]) <= data["artifacts"].keys()
            or not set(row["pending_curses"]) <= set(data["curses"])
            or row["random_id"] is not None
            and row["random_id"] not in data["randoms"]
        ):
            return False
    return True


def condition(kind, args, value, owned):
    args = args or []
    inventory = effects.ids(value)
    if kind == "None":
        return True
    if kind == "Coin":
        return bool(args) and value["silver_coin"] >= args[0]
    if kind in ("ArtifactCount", "CurseCount"):
        return (
            bool(args) and len(inventory if kind == "ArtifactCount" else value["curses"]) >= args[0]
        )
    histories = {
        "Artifact": inventory,
        "Curse": value["curses"],
        "EventChoiceProgress": value["known_choices"],
        "EventProgress": value["known_events"],
        "RandomConclusion": value["known_random"],
    }
    if kind in histories:
        return bool(args) and set(args) <= set(histories[kind])
    if kind in ("ArtifactAny", "EventChoiceProgressAny", "EventProgressAny"):
        return bool(set(args).intersection(histories[kind.removesuffix("Any")]))
    return False


def random_candidates(row, data, value, owned):
    group = row["EffectValue1"]
    # Original random conclusions carry their own group/priority/conditions.
    candidates = [
        r
        for r in data["randoms"].values()
        if r["ConclusionId"] in group
        and condition(r["ConditionType"], r["ConditionValue"], value, owned)
    ]
    priority = max((r["Priority"] for r in candidates), default=None)
    return [r for r in candidates if r["Priority"] == priority and r["Weight"] > 0]


def supported(row, data, value, owned, depth=0):
    if depth > 1 or not condition(row["ConditionType"], row["ConditionValue"], value, owned):
        return False
    cost = 0
    for i in (1, 2, 3):
        kind, args = row["EffectType" + str(i)], row.get("EffectValue" + str(i)) or []
        if kind not in effects.SUPPORTED:
            return False
        if kind != "None" and not args:
            return False
        if kind == "ConcludeByWeight":
            candidates = random_candidates(dict(EffectValue1=args), data, value, owned)
            if not candidates or not all(
                supported(r, data, value, owned, depth + 1) for r in candidates
            ):
                return False
        if kind == "LoseCoin":
            cost += args[0]
        if kind == "GetArtifactByRarity" and not any(
            data["artifacts"][i].get("Rarity") in args for i in data["lootable"]
        ):
            return False
        if kind.startswith("GetArtifactById") and not set(args) <= data["artifacts"].keys():
            return False
        if kind == "GetCurseById" and not set(args) <= set(data["curses"]):
            return False
        if kind == "GetCurse" and not data["curses"]:
            return False
        if (
            kind.startswith("Progress")
            and args != [0]
            and (not valid_targets(args) or not set(args) <= data["events"].keys())
        ):
            return False
    return cost <= value["silver_coin"]


def rng_for(value, ident, purpose):
    return random.Random(
        hashlib.sha256(
            f"local-kamazone-event-v1:{value['season_id']}:{value['seed']}:{ident}:{purpose}".encode()
        ).digest()
    )


def available(data, value, owned):
    next_ids = {
        target: int(k)
        for scope, progress in value["event_progress"].items()
        for k, r in progress.items()
        for target in continuations(r, data, scope)
    }
    active = {
        int(k)
        for progress in value["event_progress"].values()
        for k, r in progress.items()
        if r["next"]
    }
    result = []
    for ident, event in sorted(data["events"].items()):
        floor = event["AppearFloor"]
        if (
            event["Hidden"]
            and ident not in next_ids
            or ident in active
            and ident not in next_ids
            or floor > value["floor"]
            or floor < 0
            and value["floor"] > -floor
            or event.get("Difficulty") is not None
            and value["difficulty"] not in event["Difficulty"]
        ):
            continue
        choices = [
            i
            for i, c in data["choices"].items()
            if c["EventId"] == ident and supported(c, data, value, owned)
        ]
        weight = event["WeightBase"] + (
            event["WeightAdd"]
            if condition(event["WeightConditionType"], event["WeightConditionValue"], value, owned)
            else 0
        )
        if choices and weight > 0:
            result.append((ident, next_ids.get(ident, ident), choices, weight))
    return result


def open_event(value, source, season_id, node, owned):
    key = str(node["Id"])
    if key not in value["events"]:
        data = catalog(source, season_id)
        pool = available(data, value, owned)
        if not pool:
            raise ValueError("No supported seasonal special event is currently eligible")
        ident, root, choices, _ = rng_for(value, node["Id"], "event").choices(
            pool, [r[3] for r in pool]
        )[0]
        value["events"][key] = dict(
            event_id=ident,
            root=root,
            choices=choices,
            choice_id=None,
            random_id=None,
            results=[],
            pending_artifacts=[],
            pending_curses=[],
            closed=False,
            close_hash=None,
        )
        value["known_events"] = sorted(set(value["known_events"]) | {ident})
    visit = value["events"][key]
    value["states"][key] = 11 if visit["closed"] else 9 if visit["choice_id"] is not None else 1
    value["stage_started"] = not visit["closed"]


def validate(route, request):
    fields = (
        {"NodeId", "ChoiceId"}
        if route == CHOOSE
        else {
            "NodeId",
            "LootArtifactIds",
            "DiscardArtifactIndices",
            "LootCurseIds",
            "DiscardCurseIndices",
        }
    )
    if (
        not isinstance(request, dict)
        or "NodeId" not in request
        or not set(request) <= fields
        or not integer(request["NodeId"], minimum=1)
        or route == CHOOSE
        and (set(request) != fields or not integer(request["ChoiceId"], minimum=1))
        or route == CLOSE
        and any(not effects.nullable_list(v) for k, v in request.items() if k != "NodeId")
    ):
        raise ValueError("Invalid native Kama-ZONE special-event choice/closing request")


def handle(value, source, season_id, route, request, owned):
    ident = request["NodeId"]
    visit = value["events"].get(str(ident))
    if (
        not value["active"]
        or value["current_node_id"] != ident
        or visit is None
        or value["battle_started"]
        or value["pending_result"] is not None
    ):
        raise ValueError("Open the current Kama-ZONE special event before choosing/closing it")
    if route == CLOSE:
        if visit["choice_id"] is None:
            raise ValueError("Choose a special-event option before confirming its result")
        normalized = {"NodeId": ident}
        for suffix, count in (
            ("Artifact", len(visit["pending_artifacts"])),
            ("Curse", len(visit["pending_curses"])),
        ):
            for field in ("Loot" + suffix + "Ids", "Discard" + suffix + "Indices"):
                normalized[field] = [None] * count if request.get(field) is None else request[field]
        fingerprint = hashlib.sha256(
            json.dumps(
                normalized,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if visit["closed"]:
            if visit["close_hash"] != fingerprint:
                raise ValueError("This special-event result was already closed differently")
            return
        kamazone_silver.charge_clear(value, source)
        effects.grant(value, visit, request)
        visit.update(closed=True, close_hash=fingerprint)
        value["states"][str(ident)] = 11
        value["stage_started"] = False
        return
    choice_id = request["ChoiceId"]
    if visit["choice_id"] is not None:
        if visit["choice_id"] != choice_id:
            raise ValueError("This special event already has a different chosen option")
        return
    data = catalog(source, season_id)
    row = data["choices"].get(choice_id)
    if choice_id not in visit["choices"] or row is None or not supported(row, data, value, owned):
        raise ValueError("This seasonal event choice is unavailable or not implemented")
    rng = rng_for(value, ident, "choice:" + str(choice_id))
    visit["choice_id"] = choice_id
    for scope in value["event_progress"].values():
        if str(visit["root"]) in scope:
            scope[str(visit["root"])]["choices"].append(choice_id)
    pending = [(row["EffectType" + str(i)], row.get("EffectValue" + str(i))) for i in (1, 2, 3)]
    while pending:
        kind, args = pending.pop(0)
        if kind == "ConcludeByWeight":
            rows = random_candidates(dict(EffectValue1=args), data, value, owned)
            chosen = rng.choices(rows, [r["Weight"] for r in rows])[0]
            visit["random_id"] = chosen["Id"]
            value["known_random"] = sorted(set(value["known_random"]) | {chosen["Id"]})
            visit["results"].append(effects.result(kind, values=[chosen["Id"]]))
            pending[0:0] = [
                (chosen["EffectType" + str(i)], chosen.get("EffectValue" + str(i)))
                for i in (1, 2, 3)
            ]
        elif kind.startswith("ProgressIn"):
            key = str(visit["root"])
            history = []
            for progress in value["event_progress"].values():
                history.extend(progress.pop(key, {}).get("choices", []))
            history = list(dict.fromkeys([*history, choice_id]))
            scope = "season" if kind == "ProgressInSeason" else "challenge"
            value["event_progress"][scope][key] = dict(
                next=args[0] if len(args) == 1 else list(args), choices=history
            )
        else:
            visit["results"].append(effects.apply(value, data, kind, args, owned, rng, visit))
    value["states"][str(ident)] = 9
    value["known_choices"] = sorted(set(value["known_choices"]) | {choice_id})


def project(value, user):
    user.update(
        SilverCoin=value["silver_coin"],
        Artifacts=copy.deepcopy(value["artifacts"]),
        KnownEvents=list(value["known_events"]),
        KnownChoices=list(value["known_choices"]),
        KnownRandomConclusions=list(value["known_random"]),
    )
    for scope, field in (("season", "ProgressInSeason"), ("challenge", "ProgressInChallenge")):
        user[field] = {
            key: list(row["choices"]) for key, row in value["event_progress"][scope].items()
        }
    for node in user["Nodes"]:
        row = value["events"].get(str(node["Id"]))
        if row is not None:
            # Native EnterNode selects the true entry to resume its conclusion.
            # False means unchosen, not an unavailable/disabled choice.
            node["SpecialEventChoices"] = {str(i): i == row["choice_id"] for i in row["choices"]}
            node["ChoiceEffectResults"] = copy.deepcopy(row["results"])


def response(route):
    return {"ChoiceEffectResults": [], "AddedItems": []} if route == CLOSE else {}
