# SPDX-License-Identifier: Apache-2.0
"""Command-line entry point, also usable without installing the package."""

import argparse
import importlib
import sys

COMMANDS = {
    "inventory-panel": ("inventory_panel.server", "Open the local inventory editor"),
    "serve": ("runtime.server", "Run the local game and platform server"),
    "admin": (
        "administration.admin",
        "Manage audited local currency grants and optional test pins",
    ),
    "raid-season": ("modes.guild.guild_raid", "List, select or customize local Raid seasons"),
    "dka-season": ("modes.guild.punchking", "List/select Dungeon Kingdom Arena variants and days"),
    "guild-war": ("modes.guild.guild_war", "Enable/disable an experimental local Guild War season"),
    "expedition": (
        "modes.expedition.expedition_levels",
        "List, set or restore per-stage Expedition enemy levels",
    ),
    "tetis-map-trial": (
        "modes.tetis.tetis_map_trial",
        "Try or restore the preserved map on Tetis S1 floor 1",
    ),
    "kamazone": (
        "modes.kamazone.kamazone",
        "Select an optional Kama-ZONE season for Events menu visibility",
    ),
    "andras-trial": (
        "administration.andras_trial",
        "Toggle the response-only experimental Andras Myth variant",
    ),
    "head-hunter": (
        "administration.head_hunter",
        "Grant, list or retire additional level-150 Head Hunter Myth copies",
    ),
    "assets": ("content.assets", "Serve manifest-listed local resources"),
    "content": (
        "content.content_pack",
        "Import/check versioned offline content releases or build release parts",
    ),
    "probe": ("runtime.probe", "Check an already running local transport"),
    "client-cert": (
        "runtime.client_cert",
        "Generate local certificates for the pinned APK hostnames",
    ),
    "android-bridge": (
        "runtime.android_bridge",
        "Connect a dedicated MuMu Android 12 test instance",
    ),
    "demo": ("runtime.demo", "Run a temporary synthetic loopback demonstration"),
    "validate": ("runtime.validation", "Run the repository regression suite"),
    "read-packet": ("runtime.packet_reader", "Decode a local packet file"),
    "campaign": (
        "campaigns.campaign_cli",
        "Prepare or preview a fully completed local story test save",
    ),
    "snapshot": ("accounts.snapshots", "Inspect/import a private experimental account snapshot"),
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Guardian Tales 3.57.0 local server prototype")
    parser.add_argument(
        "command",
        choices=COMMANDS,
        help="; ".join(f"{name}: {item[1]}" for name, item in COMMANDS.items()),
    )
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return
    command = parser.parse_args(argv[:1]).command
    module = importlib.import_module(f".{COMMANDS[command][0]}", __package__)
    module.main(argv[1:])


if __name__ == "__main__":
    main()
