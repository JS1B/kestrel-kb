"""Memory record parsing and serialization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lock import atomic_write
from .yaml_subset import YAMLParseError, dump_yaml_subset, parse_yaml_subset

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

REQUIRED_FIELDS = (
    "id",
    "type",
    "status",
    "confidence",
    "source",
    "sensitivity",
    "created",
    "updated",
    "review_after",
    "supersedes",
    "tags",
)


@dataclass
class MemoryRecord:
    path: Path
    meta: dict[str, Any]
    body: str

    @property
    def id(self) -> str:
        return str(self.meta["id"])

    @property
    def type(self) -> str:
        return str(self.meta["type"])

    @property
    def status(self) -> str:
        return str(self.meta["status"])

    @property
    def confidence(self) -> str:
        return str(self.meta["confidence"])

    @property
    def title(self) -> str:
        match = TITLE_RE.search(self.body)
        if match:
            return match.group(1).strip()
        first = self.body.strip().splitlines()
        return first[0].strip() if first else self.id

    def to_markdown(self) -> str:
        ordered = {k: self.meta[k] for k in REQUIRED_FIELDS if k in self.meta}
        for key in sorted(self.meta):
            if key not in ordered:
                ordered[key] = self.meta[key]
        fm = dump_yaml_subset(ordered)
        body = self.body
        if body and not body.endswith("\n"):
            body += "\n"
        return f"---\n{fm}---\n{body}"


class ParseError(ValueError):
    pass


def parse_memory_file(path: Path) -> MemoryRecord:
    text = path.read_text(encoding="utf-8")
    return parse_memory_text(text, path=path)


def parse_memory_text(text: str, *, path: Path | None = None) -> MemoryRecord:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ParseError(f"Missing or invalid frontmatter in {path or '<text>'}")
    try:
        meta = parse_yaml_subset(match.group(1))
    except YAMLParseError as exc:
        raise ParseError(str(exc)) from exc
    body = match.group(2)
    if body.startswith("\n"):
        body = body[1:]
    return MemoryRecord(path=path or Path("-"), meta=meta, body=body)


def write_memory_file(record: MemoryRecord, path: Path | None = None) -> None:
    target = path or record.path
    atomic_write(target, record.to_markdown())
