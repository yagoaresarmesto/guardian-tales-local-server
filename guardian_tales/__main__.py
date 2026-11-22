# SPDX-License-Identifier: Apache-2.0
"""Command-line entry point, also usable without installing the package."""

import argparse
import importlib
import sys

COMMANDS = {
    "serve": ("server", "Run the local game and platform server"),
    "admin": ("admin", "Manage audited local currency grants and optional test pins"),
    "raid-season": ("guild_raid", "List, select or customize local Raid seasons"),
    "dka-season": ("punchking", "List/select Dungeon Kingdom Arena variants and days"),
    "guild-war": ("guild_war", "Enable/disable an experimental local Guild War season"),
    "expedition": ("expedition_levels", "List, set or restore per-stage Expedition enemy levels"),
    "andras-trial": ("andras_trial", "Toggle the response-only experimental Andras Myth variant"),
    "head-hunter": (
        "head_hunter",
        "Grant, list or retire additional level-150 Head Hunter Myth copies",
    ),
    "assets": ("assets", "Serve manifest-listed local resources"),
    "content": (
        "content_pack",
        "Import/check versioned offline content releases or build release parts",
    ),
    "probe": ("probe", "Check an already running local transport"),
    "client-cert": ("client_cert", "Generate local certificates for the pinned APK hostnames"),
    "android-bridge": ("android_bridge", "Connect a dedicated MuMu Android 12 test instance"),
    "demo": ("demo", "Run a temporary synthetic loopback demonstration"),
    "validate": ("validation", "Run the repository regression suite"),
    "read-packet": ("packet_reader", "Decode a local packet file"),
    "campaign": ("campaign_cli", "Prepare or preview a fully completed local story test save"),
    "snapshot": ("snapshots", "Inspect/import a private experimental account snapshot"),
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
