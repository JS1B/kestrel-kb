"""Deterministic INDEX.md generation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .parser import MemoryRecord, parse_memory_file
from .path_safety import is_safe_memory_path
from .paths import TYPE_TO_CATEGORY, inbox_dir, iter_safe_memory_files


def _canonical_records(root: Path) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    for path in iter_safe_memory_files(root, include_inbox=False):
        records.append(parse_memory_file(path, root=root))
    records.sort(key=lambda r: (r.type, r.id))
    return records


def generate_index(root: Path, records: list[MemoryRecord] | None = None) -> str:
    if records is None:
        records = _canonical_records(root)

    today = date.today().isoformat()
    lines = [
        "# Kestrel Memory Index",
        "",
        f"<!-- generated: {today}; do not edit manually -->",
        "",
        "Canonical operational memory for Kestrel. Unreviewed candidates live in `inbox/`.",
        "",
        "Regenerate: `./tools/kb index`",
        "",
    ]

    by_type: dict[str, list[MemoryRecord]] = {t: [] for t in TYPE_TO_CATEGORY}
    for record in records:
        by_type.setdefault(record.type, []).append(record)

    for mem_type in sorted(TYPE_TO_CATEGORY):
        category = TYPE_TO_CATEGORY[mem_type]
        lines.append(f"## {category}")
        lines.append("")
        group = sorted(by_type.get(mem_type, []), key=lambda r: r.id)
        if not group:
            lines.append("_No records._")
            lines.append("")
            continue
        lines.append("| id | status | confidence | title | path | review_after |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for record in group:
            rel = record.path.relative_to(root).as_posix()
            title = record.title.replace("|", "\\|")
            lines.append(
                f"| {record.id} | {record.status} | {record.confidence} "
                f"| {title} | `{rel}` | {record.meta['review_after']} |"
            )
        lines.append("")

    inbox = inbox_dir(root)
    inbox_files: list[Path] = []
    if inbox.is_dir() and not inbox.is_symlink():
        inbox_files = sorted(
            p for p in inbox.iterdir() if p.suffix == ".md" and is_safe_memory_path(root, p)
        )
    lines.append("## inbox")
    lines.append("")
    if inbox_files:
        lines.append("| file |")
        lines.append("| --- |")
        for path in inbox_files:
            lines.append(f"| `{path.relative_to(root).as_posix()}` |")
    else:
        lines.append("_No inbox candidates._")
    lines.append("")
    return "\n".join(lines)
