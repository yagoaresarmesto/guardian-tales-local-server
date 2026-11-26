# SPDX-License-Identifier: Apache-2.0
"""Destinations selected by campaign scripts outside the static tile exit data."""


def scripted_target(stage_name, exit_name, *, clear=True):
    # Demonshire's Section27 routes three exits from the same room through
    # TeleportPartyStageLogic. The ordinary tile exit records omit those links.
    if stage_name == "demonshire_4_1" and exit_name in (
        "exit_demonshire_4_2",
        "exit_demonshire_4_4",
        "exit_demonshire_4_5",
    ):
        return exit_name.removeprefix("exit_")
    # The Hell subsystem sends its own clear event. The three stages each
    # declare exactly one exit handle, named for the next stage.
    hell_exits = {
        "hell_forest_1": "exit_hell_forest_2",
        "hell_forest_2": "exit_hell_forest_3",
        "hell_forest_3": "exit_hell_forest_4",
    }
    if clear and exit_name and hell_exits.get(stage_name) == exit_name:
        return exit_name.removeprefix("exit_")
    return None
