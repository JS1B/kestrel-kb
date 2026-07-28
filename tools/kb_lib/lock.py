"""File locking helpers (fcntl on Unix)."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path


class LockTimeout(TimeoutError):
    pass


@contextmanager
def file_lock(lock_path: Path, *, timeout: float = 30.0, poll: float = 0.05):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    start = time.monotonic()
    try:
        import fcntl

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start >= timeout:
                    raise LockTimeout(f"Could not acquire lock: {lock_path}")
                time.sleep(poll)
        yield
    finally:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
