"""Repository path resolution."""

from __future__ import annotations

import os
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


def iter_memory_files(root: Path, *, include_inbox: bool = True):
    """Yield memory markdown files in deterministic order."""
    for category in sorted(TYPE_TO_CATEGORY.values()):
        directory = category_dir(root, category)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            yield path
    if include_inbox:
        inbox = inbox_dir(root)
        if inbox.is_dir():
            for path in sorted(inbox.glob("*.md")):
                yield path
