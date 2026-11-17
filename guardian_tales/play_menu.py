# SPDX-License-Identifier: Apache-2.0
"""Read-only Play menu prerequisites and saved mode entry; battles unsupported."""

from .snapshots import preserved_read

PLAY_MENU_ROUTES = ("/coop-expedition/enter", "/rift/enter", "/tower-infinity/enter")


def read(store, route, body):
    if route == "/tower-infinity/enter":
        if body not in (None, {}):
            raise ValueError("Infinite tower entry accepts no parameters")
        tower = store.account.profile()["UserProgress"].get("TowerInfinity")
        if (
            not isinstance(tower, dict)
            or type(tower.get("Floor")) is not int
            or not -0x7FFFFFFF <= tower["Floor"] <= 0x7FFFFFFF
        ):
            raise ValueError("Invalid saved infinite tower progress")
        # The entry callback reads this top-level object directly. Returning
        # only UserProgress would not satisfy it. Retain legacy Formation and
        # signed floors without migrating presets or saving any state.
        return {"TowerInfinity": tower}
    if route == "/rift/enter":
        if body not in (None, {}):
            raise ValueError("Rift entry accepts no parameters")
        # Return the saved selections, including imported evolution-stone
        # rewards. Entry does not reset them or refresh daily bonuses.
        return {"UserProgress": store.account.profile()["UserProgress"]}
    if route != "/coop-expedition/enter":
        raise ValueError("Unsupported contents-book read")
    if (
        not isinstance(body, dict)
        or set(body) != {"IsPartial"}
        or type(body["IsPartial"]) is not bool
    ):
        raise ValueError("Cooperative expedition entry requires a Boolean IsPartial")
    presets = preserved_read(store.db, "/preset/get-presets")
    slots = {} if presets is None else presets.get("CoopExpeditionSlots", {})
    if not isinstance(slots, dict):
        raise ValueError("Invalid preserved cooperative expedition slots")
    # The snapshot does not include UserCoopExpedition. This is an explicit
    # empty local view, not recovered official progress or a saved reset.
    # Always provide a full object, even when the client has an older cache.
    return {
        "IsPartial": False,
        "UserCoopExpedition": {
            "Slots": slots,
            "StageStates": {},
            "Narratives": [],
            "LikeCount": 0,
            "DailyRandomMatchRewardCount": 0,
            "WeeklyRandomMatchRewardCount": 0,
            "WeeklyHelpRewardCount": 0,
            "WeeklyClearRewardCount": {},
            "LastUpdated": "2000-01-01T00:00:00+00:00",
            "BonusTreasureCount": 0,
        },
    }
