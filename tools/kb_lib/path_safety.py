"""Strict path resolution and containment checks."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .paths import inbox_dir


class PathSafetyError(ValueError):
    pass


def _is_contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def symlink_in_chain(path: Path, stop: Path) -> bool:
    """True if any component from path up to stop is a symlink (lstat-based)."""
    current = path
    stop = stop.resolve()
    while True:
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
        try:
            if current.resolve() == stop:
                break
        except OSError:
            return True
        if current == stop:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return False


def is_regular_file(path: Path) -> bool:
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode)


def is_safe_memory_path(root: Path, path: Path) -> bool:
    """True when path is a non-symlink regular file contained in the repo."""
    root = root.resolve()
    if path.is_symlink():
        return False
    if not is_regular_file(path):
        return False
    if symlink_in_chain(path, root):
        return False
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return _is_contained(resolved, root)


def assert_safe_memory_path(root: Path, path: Path) -> None:
    if path.is_symlink():
        raise PathSafetyError(f"symlink entry not allowed: {path}")
    if not is_regular_file(path):
        raise PathSafetyError(f"not a regular file: {path}")
    if symlink_in_chain(path, root.resolve()):
        raise PathSafetyError(f"symlink component in path: {path}")
    resolved = path.resolve()
    if not _is_contained(resolved, root.resolve()):
        raise PathSafetyError(f"path outside repository: {path}")


def _unresolved_inbox_child(root: Path, arg: str) -> Path:
    if not arg or not str(arg).strip():
        raise PathSafetyError("inbox path is required")

    raw = Path(arg)
    if ".." in raw.parts:
        raise PathSafetyError(f"path traversal rejected: {arg!r}")

    root = root.resolve()
    inbox = inbox_dir(root)

    if raw.is_absolute():
        try:
            rel = raw.relative_to(inbox)
        except ValueError:
            raise PathSafetyError(f"path outside inbox: {arg!r}") from None
        if len(rel.parts) != 1:
            raise PathSafetyError(f"inbox file must be direct child of inbox/: {arg!r}")
        return inbox / rel.parts[0]

    if "/" not in arg and "\\" not in arg:
        return inbox / raw.name

    candidate = root / raw
    try:
        rel = candidate.relative_to(inbox)
    except ValueError:
        raise PathSafetyError(f"not a direct inbox file: {arg!r}") from None
    if len(rel.parts) != 1:
        raise PathSafetyError(f"inbox file must be direct child of inbox/: {arg!r}")
    return candidate


def resolve_inbox_file(root: Path, arg: str) -> Path:
    """Resolve promote target to a direct inbox child without following symlinks."""
    root = root.resolve()
    inbox = inbox_dir(root)
    child = _unresolved_inbox_child(root, arg)

    # lstat / is_symlink on original direct inbox child BEFORE resolve()
    if symlink_in_chain(child, root):
        raise PathSafetyError(f"symlink rejected: {arg!r}")
    if child.is_symlink():
        raise PathSafetyError(f"symlink rejected: {arg!r}")

    if not child.exists():
        raise PathSafetyError(f"inbox file not found: {arg!r}")

    if not is_regular_file(child):
        raise PathSafetyError(f"not a regular file: {arg!r}")

    if child.suffix != ".md":
        raise PathSafetyError(f"inbox file must be .md: {arg!r}")

    if child.parent != inbox:
        raise PathSafetyError(f"inbox file must be direct child of inbox/: {arg!r}")

    resolved = child.resolve()
    if not _is_contained(resolved, inbox.resolve()):
        raise PathSafetyError(f"resolved path escapes inbox: {arg!r}")

    return child


def read_safe_text(root: Path, path: Path) -> str:
    assert_safe_memory_path(root, path)
    return path.read_text(encoding="utf-8")
