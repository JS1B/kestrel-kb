"""Deterministic memory search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .parser import MemoryRecord, parse_memory_file
from .paths import iter_safe_memory_files

SNIPPET_RADIUS = 60
MAX_SNIPPETS = 2


@dataclass
class SearchHit:
    record: MemoryRecord
    score: int
    snippets: list[str]


def _tokenize(query: str) -> list[str]:
    return [t for t in re.split(r"\s+", query.strip().lower()) if t]


def _snippet(text: str, term: str) -> str | None:
    lower = text.lower()
    idx = lower.find(term)
    if idx < 0:
        return None
    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(text), idx + len(term) + SNIPPET_RADIUS)
    chunk = text[start:end].replace("\n", " ")
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{chunk}{suffix}"


def search_records(root: Path, query: str) -> list[SearchHit]:
    terms = _tokenize(query)
    if not terms:
        return []

    hits: list[SearchHit] = []
    for path in iter_safe_memory_files(root, include_inbox=True):
        record = parse_memory_file(path, root=root)
        hay_meta = " ".join(
            [
                record.id,
                record.type,
                record.status,
                str(record.meta.get("source", "")),
                " ".join(record.meta.get("tags", [])),
                record.title,
            ]
        ).lower()
        hay_body = record.body.lower()
        score = 0
        snippets: list[str] = []
        for term in terms:
            if term in record.id.lower():
                score += 5
            if term in record.title.lower():
                score += 4
            if term in hay_meta:
                score += 2
            if term in hay_body:
                score += 1
                sn = _snippet(record.body, term)
                if sn and sn not in snippets:
                    snippets.append(sn)
        if score > 0:
            hits.append(SearchHit(record, score, snippets[:MAX_SNIPPETS]))

    hits.sort(key=lambda h: (-h.score, h.record.type, h.record.id))
    return hits


def format_hits(hits: list[SearchHit], root: Path) -> str:
    if not hits:
        return "No matches."
    lines: list[str] = []
    for hit in hits:
        try:
            rel = hit.record.path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = hit.record.path.as_posix()
        lines.append(
            f"{hit.record.id}\t{hit.record.type}\t{hit.record.title}\t{rel}"
        )
        for sn in hit.snippets:
            lines.append(f"  … {sn}")
    return "\n".join(lines)
