# SPDX-License-Identifier: Apache-2.0
"""Open the local dashboard on the inventory page for offline save edits."""

import argparse
import site
import sqlite3
import subprocess
import sys
import webbrowser
from importlib import import_module, invalidate_caches
from pathlib import Path
from threading import Event

from guardian_tales.content.reference import ReferenceData
from guardian_tales.panel_common.artwork import decoder_available
from guardian_tales.runtime.service_control import active_services, register, restart_worker
from guardian_tales.web_panel.server import WebPanel

# Also declared by the panel-art extra. Bare checkouts lack installed package metadata.
PANEL_ART_REQUIREMENTS = ("UnityPy>=1.25.4,<2", "xxhash>=3.5,<5")


class InventoryServer(WebPanel):
    inventory_home = True

    def __init__(self, port, database, references, art_dir):
        super().__init__(references, port, database=database, art_dir=art_dir)
        try:
            self.inventory  # Validate the supplied catalog and save before opening the browser.
        except BaseException:
            self.server_close()
            raise


def display_readers_available():
    try:
        import_module("xxhash")
    except (ImportError, OSError):
        return False
    return decoder_available()


def ensure_display_readers():
    if display_readers_available():
        return
    print(
        "Installing the inventory artwork and name readers in this Python environment.",
        file=sys.stderr,
    )
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                "--no-input",
                *PANEL_ART_REQUIREMENTS,
            ],
            check=True,
        )
        # A first user-site install can create a directory missing from the startup path.
        if site.ENABLE_USER_SITE:
            user_site = site.getusersitepackages()
            if user_site not in sys.path and Path(user_site).is_dir():
                site.addsitedir(user_site)
        invalidate_caches()
        if display_readers_available():
            return
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Inventory display setup failed: {error}", file=sys.stderr)
    print(
        "Opening the inventory panel with placeholders. "
        "Run the same command again to retry inventory display setup.",
        file=sys.stderr,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("local/state"),
        help="Directory containing the working server.sqlite3",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("local/client-data/reference"),
        help="Imported reference directory",
    )
    parser.add_argument("--art-dir", type=Path, help="Directory containing an optional brand.png")
    parser.add_argument("--port", type=int, default=17661, help="Local HTTP port (default: 17661)")
    parser.add_argument(
        "--open", action="store_true", help="Open the inventory panel in your browser"
    )
    parser.add_argument("--restart-worker", action="store_true", help=argparse.SUPPRESS)
    launch_args = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(launch_args)
    if not 0 <= args.port <= 65535:
        parser.error("Choose a port between 0 and 65535.")
    database = args.data_dir / "server.sqlite3"
    if not database.is_file():
        parser.error(
            f"Working save not found: {database}. Set --data-dir to your existing save directory."
        )
    if args.port and any(
        port == args.port for port, _, _ in active_services("inventory", database)
    ):
        address = f"http://127.0.0.1:{args.port}/"
        print(f"Inventory server already running at {address}", flush=True)
        print("To load project updates, choose Services > Inventory server > Restart.")
        if args.open and not args.restart_worker:
            webbrowser.open(address)
        return
    ensure_display_readers()
    try:
        server = InventoryServer(
            args.port,
            database,
            ReferenceData(args.reference_dir),
            args.art_dir or args.data_dir.parent / "panel-art",
        )
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        parser.exit(1, f"Could not start the inventory panel: {error}\n")
    requested = Event()
    port = server.server_port

    def restart():
        requested.set()
        server.shutdown()

    with server, register("inventory", database, port, restart):
        address = f"http://127.0.0.1:{server.server_port}/"
        print(address, flush=True)
        if args.open and not args.restart_worker:
            webbrowser.open(address)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    if requested.is_set():
        restart_worker("inventory-panel", launch_args, {"--port": port}, args.restart_worker)
