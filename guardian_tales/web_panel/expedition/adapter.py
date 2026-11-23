# SPDX-License-Identifier: Apache-2.0
"""Expose the solo Expedition level commands to the local panel."""

from ...expedition_levels import level_settings
from ...village import integer
from ..artwork import EXPEDITION


def state(references):
    return {**level_settings(references), "hasArt": EXPEDITION.available(references)}


def apply(references, body):
    if not isinstance(body, dict) or not integer(body.get("revision")):
        raise ValueError("Reload the stage list before applying changes")
    action, scope = body.get("action"), body.get("scope")
    if action not in ("set-level", "restore-level") or scope not in ("stage", "all"):
        raise ValueError("Choose a level action and its stage scope")
    fields = {"action", "scope", "revision"}
    if scope == "stage":
        fields.add("stage")
        if not integer(body.get("stage"), minimum=1):
            raise ValueError("Choose an Expedition stage")
    if action == "set-level":
        fields.add("level")
    if body.keys() != fields:
        raise ValueError("Invalid fields for this Expedition level action")
    level_settings(
        references,
        action,
        stage=body.get("stage"),
        all_stages=scope == "all",
        level=body.get("level"),
        expected_revision=body["revision"],
    )
