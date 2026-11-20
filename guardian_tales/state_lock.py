# SPDX-License-Identifier: Apache-2.0
"""Hold one local state directory for a backend or administrative operation."""

import os
from pathlib import Path


class StateLock:
    def __init__(self, data_dir, *, filename=".state.lock"):
        self.path = Path(data_dir).resolve() / filename
        self.file = None

    def acquire(self):
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if handle.seek(0, 2) == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise RuntimeError(
                "State directory is in use. Stop its backend or other administrator first."
            ) from error
        self.file = handle
        return self

    def release(self):
        if self.file is not None:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.release()
