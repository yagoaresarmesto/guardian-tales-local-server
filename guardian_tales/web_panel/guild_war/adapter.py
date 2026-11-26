# SPDX-License-Identifier: Apache-2.0
"""Present the native Guild War season and forward edits to its CLI operations."""

from io import BytesIO

from guardian_tales.modes.guild import guild_war_static as war
from guardian_tales.modes.guild.guild_war import selection_status

from ..artwork import WAR


def illustration(references, *, frame):
    """Encode the opaque Guild Wars card illustration for the panel banner."""
    pixels = WAR.read(references, frame=frame)
    from PIL import Image

    with Image.open(BytesIO(pixels)) as image:
        output = BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=85)
        return output.getvalue()


def state(references):
    selection = war.load_selection(references)
    # Raid and DKA do not change deployment. Inspect the stock table without
    # refreshing either parent calendar when a user opens the panel.
    try:
        rows = war.deployment_castles(references.read_bytes("static_data_get.bin"), 1)
        castles = [{"id": key, "grade": rows[key]["Grade"]} for key in sorted(rows)]
        catalog_error = None
    except (ValueError, KeyError, OSError) as error:
        castles = []
        catalog_error = f"Could not load the castle deployment: {error}"
    return {
        "selection": selection_status(selection),
        "revision": war.selection_revision(selection),
        "phases": list(war.PHASES),
        "rounds": list(war.ROUND_MODES),
        "castles": castles,
        "catalogError": catalog_error,
        "hasArt": WAR.available(references),
    }


def apply(references, body):
    if not isinstance(body, dict) or not isinstance(body.get("revision"), str):
        raise ValueError("Reload Guild Wars settings before applying.")
    revision = body["revision"]
    if body.get("action") == "disable" and body.keys() == {"action", "revision"}:
        war.disable(references, expected_revision=revision)
        return
    if (
        body.keys() != {"action", "revision", "phase", "round", "castle", "skipBasic"}
        or body["action"] != "enable"
    ):
        raise ValueError("Choose a Guild Wars configuration to apply.")
    phase = war.PHASES.get(body["phase"]) if isinstance(body["phase"], str) else None
    castle = body["castle"]
    if phase is None or not isinstance(body["round"], str) or body["round"] not in war.ROUND_MODES:
        raise ValueError("Choose a Guild Wars phase and round.")
    if (
        type(body["skipBasic"]) is not bool
        or type(castle) is not int
        or castle < 0
        or (castle and phase not in (3, 4))
    ):
        raise ValueError("Choose a valid basic-course setting and castle for this phase.")
    war.enable(
        references,
        phase=phase,
        round_mode=body["round"],
        skip_basic=body["skipBasic"],
        attack_castle=castle if phase == 3 else 0,
        defend_castle=castle if phase == 4 else 0,
        expected_revision=revision,
    )
