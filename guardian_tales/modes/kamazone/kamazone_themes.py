# SPDX-License-Identifier: Apache-2.0
"""Display names for permanent Kama-ZONE rotations, which have no SeasonName field."""

# These recurring event IDs distinguish the themes in the original Global rotations.
# The first renewed season is identified by its Teatan Ranger event.
_THEME_EVENTS = {
    509: "Reopening",
    605: "Cooking",
    705: "Western",
    211: "Greenhouse",
    302: "Noir",
    405: "Dragon Hunter",
    905: "New Year",
    1105: "Necromancer",
}


def old_season_theme(season):
    events = set(season.get("SpecialEvents") or ())
    themes = [name for event, name in _THEME_EVENTS.items() if event in events]
    if 801 in events:  # Christmas gift event
        themes.append("Christmas")
    if 2001 in events:  # Final season farewell
        themes.append("Finale")
    return " + ".join(themes)


def old_season_label(season):
    label = f"Season {season['Id']}"
    theme = old_season_theme(season)
    return f"{label} · {theme}" if theme else label
