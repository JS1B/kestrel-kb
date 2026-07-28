"""File locking, atomic writes, and rollback helpers."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
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


def kb_lock_path(root: Path) -> Path:
    return root / ".lock" / "kb.lock"


@contextmanager
def repo_lock(root: Path, *, timeout: float = 30.0):
    """Single repo-wide lock for all mutating commands."""
    kb_lock_path(root).parent.mkdir(parents=True, exist_ok=True)
    with file_lock(kb_lock_path(root), timeout=timeout):
        yield


def atomic_write(path: Path, content: str | bytes, *, encoding: str = "utf-8") -> None:
    """Write via temp file, fsync, and atomic replace; preserve mode when replacing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o644
    if path.exists():
        mode = path.stat().st_mode & 0o777

    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = content.encode(encoding) if isinstance(content, str) else content

    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)

    dir_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    os.replace(tmp, path)


@dataclass
class FileBackup:
    path: Path
    existed: bool
    content: bytes | None


def backup_file(path: Path) -> FileBackup:
    if path.is_file():
        return FileBackup(path=path, existed=True, content=path.read_bytes())
    return FileBackup(path=path, existed=False, content=None)


def restore_backup(backup: FileBackup) -> None:
    if backup.existed:
        if backup.content is None:
            raise RuntimeError(f"missing backup content for {backup.path}")
        atomic_write(backup.path, backup.content)
    elif backup.path.exists():
        backup.path.unlink()


def restore_backups(backups: list[FileBackup]) -> None:
    for backup in backups:
        restore_backup(backup)
