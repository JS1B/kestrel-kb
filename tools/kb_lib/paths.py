"""Repository path resolution."""

from __future__ import annotations

from pathlib import Path

MARKER = "schemas/memory.schema.json"

TYPES = ("preference", "decision", "capability", "runbook", "constraint")

TYPE_TO_CATEGORY = {
    "preference": "preferences",
    "decision": "decisions",
    "capability": "capabilities",
    "runbook": "runbooks",
    "constraint": "constraints",
}

CATEGORY_TO_TYPE = {v: k for k, v in TYPE_TO_CATEGORY.items()}

STATUSES = ("candidate", "active", "superseded")
CONFIDENCE_LEVELS = ("high", "medium", "low")
SENSITIVITY_LEVELS = ("public", "internal", "restricted")

CANONICAL_STATUSES = ("active", "superseded")
INBOX_STATUS = "candidate"


def find_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / MARKER).is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not locate repo root (missing {MARKER}) from {current}"
    )


def memory_dir(root: Path) -> Path:
    return root / "memory"


def inbox_dir(root: Path) -> Path:
    return root / "inbox"


def category_dir(root: Path, category: str) -> Path:
    return memory_dir(root) / category


def index_path(root: Path) -> Path:
    return root / "INDEX.md"


def schema_path(root: Path) -> Path:
    return root / MARKER


def lock_dir(root: Path) -> Path:
    path = root / ".lock"
    path.mkdir(exist_ok=True)
    return path


def _iter_dir_markdown(directory: Path):
    if not directory.is_dir() or directory.is_symlink():
        return
    for entry in sorted(directory.iterdir()):
        if entry.suffix == ".md":
            yield entry


def iter_memory_paths(root: Path, *, include_inbox: bool = True):
    """Yield every memory .md path (including symlinks) without following symlink dirs."""
    root = root.resolve()
    memory = memory_dir(root)
    if memory.is_symlink():
        yield memory
    else:
        for category in sorted(TYPE_TO_CATEGORY.values()):
            directory = category_dir(root, category)
            if directory.is_symlink():
                yield directory
                continue
            yield from _iter_dir_markdown(directory)
    if include_inbox:
        inbox = inbox_dir(root)
        if inbox.is_symlink():
            yield inbox
        else:
            yield from _iter_dir_markdown(inbox)


def iter_safe_memory_files(root: Path, *, include_inbox: bool = True):
    """Yield only safe non-symlink regular files for read/index/search."""
    from .path_safety import is_safe_memory_path

    for path in iter_memory_paths(root, include_inbox=include_inbox):
        if is_safe_memory_path(root, path):
            yield path


def iter_memory_files(root: Path, *, include_inbox: bool = True):
    """Backward-compatible alias: safe files only (never follows symlinks)."""
    yield from iter_safe_memory_files(root, include_inbox=include_inbox)
