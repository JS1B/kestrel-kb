"""Memory record and repository validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .parser import REQUIRED_FIELDS, MemoryRecord, parse_memory_file
from .paths import (
    CANONICAL_STATUSES,
    CATEGORY_TO_TYPE,
    CONFIDENCE_LEVELS,
    INBOX_STATUS,
    SENSITIVITY_LEVELS,
    STATUSES,
    TYPES,
    TYPE_TO_CATEGORY,
    inbox_dir,
    index_path,
    iter_memory_files,
    schema_path,
)
from .secrets import scan_secrets

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
H1_LINE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass
class ValidationIssue:
    level: str  # error | warning
    path: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, level: str, path: str, message: str) -> None:
        self.issues.append(ValidationIssue(level, path, message))


def _parse_iso_date(value: str, field_name: str, path: str, report: ValidationReport) -> date | None:
    if not DATE_RE.match(value):
        report.add("error", path, f"{field_name} must be YYYY-MM-DD, got {value!r}")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        report.add("error", path, f"{field_name} is not a valid date: {value!r}")
        return None


def validate_record_body(record: MemoryRecord, report: ValidationReport) -> None:
    path = str(record.path)
    h1_matches = H1_LINE_RE.findall(record.body)
    if not h1_matches:
        report.add("error", path, "body must include one Markdown H1 title (# ...)")
    elif len(h1_matches) > 1:
        report.add("error", path, "body must have exactly one H1 title")
    else:
        title_text = h1_matches[0].strip()
        if not title_text:
            report.add("error", path, "H1 title must not be empty")

    remainder_lines: list[str] = []
    for line in record.body.splitlines():
        if H1_LINE_RE.match(line):
            continue
        remainder_lines.append(line)
    remainder = "\n".join(remainder_lines).strip()
    if not remainder or len(remainder) < 3:
        report.add("error", path, "body must have non-empty meaningful content after H1")


def validate_record_meta(record: MemoryRecord, report: ValidationReport, *, inbox: bool) -> None:
    path = str(record.path)
    meta = record.meta

    for field_name in REQUIRED_FIELDS:
        if field_name not in meta:
            report.add("error", path, f"Missing required field: {field_name}")

    extra = set(meta) - set(REQUIRED_FIELDS)
    if extra:
        report.add("error", path, f"Unknown fields: {sorted(extra)}")

    record_id = meta.get("id")
    if record_id is not None:
        if not isinstance(record_id, str) or not SLUG_RE.match(record_id):
            report.add("error", path, f"id must be a slug, got {record_id!r}")

    for enum_field, allowed in (
        ("type", TYPES),
        ("status", STATUSES),
        ("confidence", CONFIDENCE_LEVELS),
        ("sensitivity", SENSITIVITY_LEVELS),
    ):
        val = meta.get(enum_field)
        if val is not None and val not in allowed:
            report.add("error", path, f"{enum_field} must be one of {allowed}, got {val!r}")

    status = meta.get("status")
    if inbox:
        if status != INBOX_STATUS:
            report.add("error", path, f"inbox records must have status={INBOX_STATUS!r}")
    else:
        if status not in CANONICAL_STATUSES:
            report.add("error", path, f"canonical records must have status in {CANONICAL_STATUSES}")

    source = meta.get("source")
    if source is not None and (not isinstance(source, str) or not source.strip()):
        report.add("error", path, "source must be a non-empty string")

    for date_field in ("created", "updated", "review_after"):
        val = meta.get(date_field)
        if val is not None:
            _parse_iso_date(str(val), date_field, path, report)

    created = meta.get("created")
    updated = meta.get("updated")
    if isinstance(created, str) and isinstance(updated, str):
        c = _parse_iso_date(created, "created", path, report)
        u = _parse_iso_date(updated, "updated", path, report)
        if c and u and u < c:
            report.add("error", path, "updated must be >= created")

    for list_field in ("supersedes", "tags"):
        val = meta.get(list_field)
        if val is None:
            continue
        if not isinstance(val, list):
            report.add("error", path, f"{list_field} must be a list")
            continue
        seen: set[str] = set()
        for item in val:
            if not isinstance(item, str) or not SLUG_RE.match(item):
                report.add("error", path, f"{list_field} items must be slugs, got {item!r}")
            elif item in seen:
                report.add("error", path, f"duplicate {list_field} entry: {item}")
            else:
                seen.add(item)

    if record_id and record_id in meta.get("supersedes", []):
        report.add("error", path, "record cannot supersede itself")

    # Type/category path consistency for canonical files
    if not inbox and record.path and record.path.suffix == ".md":
        parent = record.path.parent.name
        expected_type = CATEGORY_TO_TYPE.get(parent)
        if expected_type and meta.get("type") != expected_type:
            report.add(
                "error",
                path,
                f"type {meta.get('type')!r} does not match directory {parent!r}",
            )
        if record_id and record.path.stem != record_id:
            report.add(
                "error",
                path,
                f"canonical filename stem must match id ({record.path.stem!r} != {record_id!r})",
            )

    validate_record_body(record, report)

    secrets = scan_secrets(record.to_markdown())
    for finding in secrets:
        report.add("error", path, f"forbidden content pattern: {finding}")


def load_all_records(root: Path) -> tuple[list[MemoryRecord], ValidationReport]:
    report = ValidationReport()
    records: list[MemoryRecord] = []
    for path in iter_memory_files(root, include_inbox=True):
        try:
            record = parse_memory_file(path)
        except Exception as exc:  # noqa: BLE001 - collect all parse errors
            report.add("error", str(path), f"parse error: {exc}")
            continue
        inbox = path.is_relative_to(inbox_dir(root))
        validate_record_meta(record, report, inbox=inbox)
        records.append(record)
    return records, report


def validate_cross_record(records: list[MemoryRecord], report: ValidationReport) -> None:
    by_id: dict[str, MemoryRecord] = {}
    for record in records:
        rid = record.id
        if rid in by_id:
            report.add(
                "error",
                str(record.path),
                f"duplicate id {rid!r} also at {by_id[rid].path}",
            )
        else:
            by_id[rid] = record

    for record in records:
        for old_id in record.meta.get("supersedes", []):
            if old_id not in by_id:
                report.add("error", str(record.path), f"supersedes unknown id: {old_id!r}")
                continue
            old = by_id[old_id]
            if record.status == "active" and old.status != "superseded":
                report.add(
                    "error",
                    str(record.path),
                    f"active record supersedes {old_id!r} which is not superseded",
                )

    # Cycle detection: edges from record -> each id in supersedes (newer -> older)
    graph: dict[str, list[str]] = {r.id: list(r.meta.get("supersedes", [])) for r in records}

    def find_cycle() -> bool:
        visited: set[str] = set()
        stack: set[str] = set()

        def dfs(node: str) -> bool:
            if node in stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            stack.add(node)
            for nxt in graph.get(node, []):
                if dfs(nxt):
                    return True
            stack.remove(node)
            return False

        return any(dfs(n) for n in graph)

    if find_cycle():
        report.add("error", "supersedes-graph", "supersedes graph contains a cycle")


def validate_schema_file(root: Path, report: ValidationReport) -> None:
    sp = schema_path(root)
    if not sp.is_file():
        report.add("error", str(sp), "schema file missing")
        return
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.add("error", str(sp), f"invalid JSON: {exc}")
        return
    for field_name in REQUIRED_FIELDS:
        if field_name not in data.get("properties", {}):
            report.add("error", str(sp), f"schema missing property: {field_name}")


def validate_index_freshness(root: Path, records: list[MemoryRecord], report: ValidationReport) -> None:
    ip = index_path(root)
    if not ip.is_file():
        report.add("error", str(ip), "INDEX.md missing; run kb index")
        return
    from .index import generate_index

    canonical = [r for r in records if not r.path.is_relative_to(inbox_dir(root))]
    expected = generate_index(root, canonical)
    actual = ip.read_text(encoding="utf-8")
    if actual != expected:
        report.add("error", str(ip), "INDEX.md is stale; run kb index")


def validate_repository(root: Path, *, check_index: bool = True) -> ValidationReport:
    validate_schema_file(root, report := ValidationReport())
    records, parse_report = load_all_records(root)
    report.issues.extend(parse_report.issues)
    validate_cross_record(records, report)
    if check_index:
        validate_index_freshness(root, records, report)
    return report
