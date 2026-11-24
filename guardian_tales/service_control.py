# SPDX-License-Identifier: Apache-2.0
"""Cooperative restarts for the local game, inventory and content services."""

import hashlib
import os
import re
import subprocess
import sys
import uuid
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path
from threading import Event, Thread

from .state_lock import StateLock

NAMES = {"game": "Game backend", "cdn": "Content CDN", "inventory": "Inventory server"}


def directory(scope):
    # Keep control files outside game saves and read-only asset packs.
    cache = (
        os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    )
    key = hashlib.sha256(os.fsencode(os.path.normcase(str(Path(scope).resolve())))).hexdigest()
    return Path(cache) / "guardian-tales-local" / "services" / key


def active_services(kind, scope):
    if scope is None:
        return []
    running = []
    for marker in directory(scope).glob(f"{kind}-*.ready"):
        match = re.fullmatch(r"(?:game|cdn|inventory)-(\d{1,5})-([a-f0-9]{32})", marker.stem)
        if not match or not marker.with_suffix(".lock").is_file():
            continue
        lock = StateLock(marker.parent, filename=marker.with_suffix(".lock").name)
        try:
            lock.acquire()
        except RuntimeError:
            running.append((int(match[1]), match[2], marker))
        else:
            # The unique marker was published after acquiring the lease. A free
            # lease here means that worker exited without finishing its cleanup.
            lock.release()
            for suffix in (".ready", ".restart", ".lock"):
                with suppress(PermissionError):
                    marker.with_suffix(suffix).unlink(missing_ok=True)
    return sorted(running)


@contextmanager
def register(kind, scope, port, request_restart):
    folder = directory(scope)
    marker = folder / f"{kind}-{port}-{uuid.uuid4().hex}.ready"
    signal = marker.with_suffix(".restart")
    done = Event()

    def watch():
        while not done.wait(0.3):
            if signal.exists():
                request_restart()
                return

    lock_path = marker.with_suffix(".lock")
    with ExitStack() as resources:
        try:
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            resources.enter_context(StateLock(folder, filename=lock_path.name))
            marker.touch(exist_ok=False)
        except (OSError, RuntimeError) as error:
            print(f"{NAMES[kind]} dashboard restart unavailable: {error}", file=sys.stderr)
            yield
            return
        thread = Thread(target=watch, name=f"{kind} restart control", daemon=True)
        thread.start()
        try:
            yield
        finally:
            marker.unlink(missing_ok=True)
            done.set()
            thread.join()
            signal.unlink(missing_ok=True)
    with suppress(PermissionError):
        lock_path.unlink(missing_ok=True)


def restart_worker(command, argv, ports, is_worker):
    """Restart with the same interpreter, foreground terminal and listening ports."""
    again = 75
    if is_worker:
        raise SystemExit(again)
    args = [sys.executable, "-m", "guardian_tales", command, *argv, "--restart-worker"]
    for flag, port in ports.items():
        args.extend([flag, str(port)])
    while True:
        worker = subprocess.Popen(args)
        try:
            code = worker.wait()
        except KeyboardInterrupt:
            # The foreground console sends Ctrl+C to both processes on Windows.
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.terminate()
                worker.wait()
            raise
        if code != again:
            if code:
                raise SystemExit(code)
            return
