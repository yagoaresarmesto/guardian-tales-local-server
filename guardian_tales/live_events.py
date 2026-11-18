# SPDX-License-Identifier: Apache-2.0
"""Read preserved temporal-event progress without initializing seasons or rewards."""

from .village import MAX_REVISION, integer
from .weapon_enhance import decimal_id

ROUTE = "/live-event/enter"
EVENT_MAPS = (
    "LiveEvents",
    "RoadmapEvents",
    "AttendanceEvents",
    "GiantGachaMachineEvents",
    "BingoEvents",
    "TurntableEvents",
    "MarbleEvents",
    "WebEvents",
    "VisitorEvents",
    "QuizEvents",
    "HeroGrowthEvents",
    "SlimeJuiceEvents",
    "SummonFestivalEvents",
)


def enter(account, body):
    if body is not None and (not isinstance(body, dict) or body):
        raise ValueError("Live-event entry accepts no parameters")
    profile = account.profile()
    events = profile.get("UserEvent")
    if (
        not isinstance(events, dict)
        or not integer(events.get("UserId"), minimum=1)
        or events["UserId"] != profile["User"]["Id"]
        or not integer(events.get("Cas"), MAX_REVISION)
    ):
        raise ValueError("Invalid saved event ownership or revision")
    for name in EVENT_MAPS:
        if name not in events:
            continue
        rows = events[name]
        if not isinstance(rows, dict) or any(
            not decimal_id(key)
            or not isinstance(row, dict)
            or not integer(row.get("Id"), minimum=1)
            or str(row["Id"]) != key
            for key, row in rows.items()
        ):
            raise ValueError("Invalid saved event collection or record identity")
    returning = events.get("ReturnEvent")
    if returning is not None and not isinstance(returning, dict):
        raise ValueError("Invalid saved return-event record")
    # Scene loaders await this read and use the globally applied UserEvent.
    # Missing seasons remain missing; entry cannot grant or reset progression.
    return {"UserEvent": events}
