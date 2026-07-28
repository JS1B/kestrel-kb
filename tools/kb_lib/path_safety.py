"""Strict path resolution and containment checks."""

from __future__ import annotations

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


def _has_symlink_in_chain(path: Path, stop: Path) -> bool:
    current = path
    stop = stop.resolve()
    while True:
        if current.is_symlink():
            return True
        if current == stop:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return False


def resolve_inbox_file(root: Path, arg: str) -> Path:
    """Resolve a promote target to a direct inbox/*.md regular file inside the repo."""
    if not arg or not str(arg).strip():
        raise PathSafetyError("inbox path is required")

    root = root.resolve()
    inbox = inbox_dir(root).resolve()

    raw = Path(arg)
    if ".." in raw.parts:
        raise PathSafetyError(f"path traversal rejected: {arg!r}")

    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        from_root = (root / raw).resolve()
        if _is_contained(from_root, inbox) and from_root.parent == inbox:
            candidate = from_root
        elif "/" not in arg and "\\" not in arg:
            candidate = (inbox / raw.name).resolve()
        else:
            raise PathSafetyError(f"not a direct inbox file: {arg!r}")

    if not _is_contained(candidate, inbox):
        raise PathSafetyError(f"path outside inbox: {arg!r}")

    if candidate.parent != inbox:
        raise PathSafetyError(f"inbox file must be direct child of inbox/: {arg!r}")

    if not candidate.exists():
        raise PathSafetyError(f"inbox file not found: {arg!r}")

    if not candidate.is_file():
        raise PathSafetyError(f"not a regular file: {arg!r}")

    if candidate.suffix != ".md":
        raise PathSafetyError(f"inbox file must be .md: {arg!r}")

    if candidate.is_symlink() or _has_symlink_in_chain(candidate, inbox):
        raise PathSafetyError(f"symlink rejected: {arg!r}")

    if not _is_contained(candidate.resolve(), inbox):
        raise PathSafetyError(f"resolved path escapes inbox: {arg!r}")

    return candidate


def resolve_repo_file(root: Path, path: Path) -> Path:
    """Ensure a path is a regular file inside the repo (no symlink escape)."""
    root = root.resolve()
    resolved = path.resolve()
    if not _is_contained(resolved, root):
        raise PathSafetyError(f"path outside repository: {path}")
    if not resolved.is_file():
        raise PathSafetyError(f"not a file: {path}")
    if resolved.is_symlink() or _has_symlink_in_chain(resolved, root):
        raise PathSafetyError(f"symlink rejected: {path}")
    return resolved
