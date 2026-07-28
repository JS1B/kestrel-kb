"""CLI command implementations."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from .index import generate_index
from .lock import LockTimeout, atomic_write, file_lock
from .parser import MemoryRecord, parse_memory_file, write_memory_file
from .paths import (
    INBOX_STATUS,
    TYPE_TO_CATEGORY,
    category_dir,
    find_root,
    inbox_dir,
    index_path,
    lock_dir,
)
from .search import format_hits, search_records
from .validator import load_all_records, validate_repository

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "untitled"


def cmd_doctor(_args: argparse.Namespace) -> int:
    root = find_root()
    report = validate_repository(root, check_index=True)
    for issue in report.issues:
        print(f"{issue.level.upper()}: {issue.path}: {issue.message}", file=sys.stderr)
    if report.ok:
        print("ok: repository healthy")
        return 0
    return 1


def cmd_index(_args: argparse.Namespace) -> int:
    root = find_root()
    lock = lock_dir(root) / "index.lock"
    try:
        with file_lock(lock):
            records, _ = load_all_records(root)
            canonical = [r for r in records if not r.path.is_relative_to(inbox_dir(root))]
            content = generate_index(root, canonical)
            atomic_write(index_path(root), content)
    except LockTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote {index_path(root)}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = find_root()
    hits = search_records(root, args.query)
    print(format_hits(hits))
    return 0


def cmd_remember(args: argparse.Namespace) -> int:
    root = find_root()
    lock = lock_dir(root) / "inbox.lock"
    today = date.today().isoformat()
    review = (date.today() + timedelta(days=180)).isoformat()
    base_slug = _slugify(args.title)
    record_id = base_slug
    existing, _ = load_all_records(root)
    existing_ids = {r.id for r in existing}
    suffix = 0
    while record_id in existing_ids:
        suffix += 1
        record_id = f"{base_slug}-{suffix}"

    filename = f"{today}-{record_id}.md"
    target = inbox_dir(root) / filename

    meta = {
        "id": record_id,
        "type": args.type,
        "status": INBOX_STATUS,
        "confidence": args.confidence,
        "source": args.source,
        "sensitivity": args.sensitivity,
        "created": today,
        "updated": today,
        "review_after": review,
        "supersedes": [],
        "tags": list(args.tag or []),
    }
    body = f"# {args.title}\n\n{args.text}\n"
    record = MemoryRecord(path=target, meta=meta, body=body)

    try:
        with file_lock(lock):
            if target.exists():
                print(f"refuse: inbox file exists: {target}", file=sys.stderr)
                return 1
            from .validator import validate_record_meta, ValidationReport

            report = ValidationReport()
            validate_record_meta(record, report, inbox=True)
            if report.errors:
                for issue in report.errors:
                    print(f"ERROR: {issue.message}", file=sys.stderr)
                return 1
            write_memory_file(record)
    except LockTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Created inbox candidate: {target.relative_to(root)}")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    root = find_root()
    inbox_path = Path(args.inbox_file)
    if not inbox_path.is_absolute():
        inbox_path = root / inbox_path
    if not inbox_path.is_file():
        print(f"not found: {inbox_path}", file=sys.stderr)
        return 1

    lock = lock_dir(root) / "promote.lock"
    try:
        with file_lock(lock):
            record = parse_memory_file(inbox_path)
            category = args.category or TYPE_TO_CATEGORY[record.type]
            if category not in TYPE_TO_CATEGORY.values():
                print(f"invalid category: {category}", file=sys.stderr)
                return 1
            expected_type = record.type
            if args.category:
                from .paths import CATEGORY_TO_TYPE

                expected_type = CATEGORY_TO_TYPE.get(category, record.type)
                record.meta["type"] = expected_type

            dest = category_dir(root, category) / f"{record.id}.md"
            if dest.exists():
                print(f"refuse overwrite: {dest}", file=sys.stderr)
                return 1

            today = date.today().isoformat()
            record.meta["status"] = "active"
            record.meta["updated"] = today
            record.path = dest

            from .validator import ValidationReport, validate_record_meta, validate_cross_record

            report = ValidationReport()
            validate_record_meta(record, report, inbox=False)
            if report.errors:
                for issue in report.errors:
                    print(f"ERROR: {issue.path}: {issue.message}", file=sys.stderr)
                return 1

            # Write dest then remove inbox atomically-ish
            write_memory_file(record, dest)
            inbox_path.unlink()

            records, _ = load_all_records(root)
            validate_cross_record(records, report)
            if report.errors:
                dest.unlink(missing_ok=True)
                # restore inbox
                record.meta["status"] = INBOX_STATUS
                record.path = inbox_path
                write_memory_file(record, inbox_path)
                for issue in report.errors:
                    print(f"ROLLBACK: {issue.path}: {issue.message}", file=sys.stderr)
                return 1

            atomic_write(index_path(root), generate_index(root))
    except LockTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Promoted to {dest.relative_to(root)}")
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    root = find_root()
    old_id, new_id = args.old_id, args.new_id
    lock = lock_dir(root) / "supersede.lock"

    try:
        with file_lock(lock):
            records, report = load_all_records(root)
            by_id = {r.id: r for r in records}
            if old_id not in by_id:
                print(f"unknown old id: {old_id}", file=sys.stderr)
                return 1
            if new_id not in by_id:
                print(f"unknown new id: {new_id}", file=sys.stderr)
                return 1
            old_record = by_id[old_id]
            new_record = by_id[new_id]

            # Backup for rollback
            old_backup = old_record.meta.copy()
            new_backup = new_record.meta.copy()

            today = date.today().isoformat()
            old_record.meta["status"] = "superseded"
            old_record.meta["updated"] = today
            supersedes = list(new_record.meta.get("supersedes", []))
            if old_id not in supersedes:
                supersedes.append(old_id)
            new_record.meta["supersedes"] = sorted(supersedes)
            new_record.meta["updated"] = today

            from .validator import ValidationReport, validate_cross_record, validate_record_meta

            check = ValidationReport()
            inbox = old_record.path.is_relative_to(inbox_dir(root))
            validate_record_meta(old_record, check, inbox=inbox)
            validate_record_meta(new_record, check, inbox=new_record.path.is_relative_to(inbox_dir(root)))
            validate_cross_record(records, check)

            # cycle check with updated graph
            if any(i.level == "error" and "cycle" in i.message for i in check.issues):
                for issue in check.errors:
                    print(f"ERROR: {issue.path}: {issue.message}", file=sys.stderr)
                return 1

            if check.errors:
                old_record.meta = old_backup
                new_record.meta = new_backup
                for issue in check.errors:
                    print(f"ROLLBACK: {issue.path}: {issue.message}", file=sys.stderr)
                return 1

            write_memory_file(old_record)
            write_memory_file(new_record)
            atomic_write(index_path(root), generate_index(root))
    except LockTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Superseded {old_id} -> {new_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb", description="Kestrel operational memory CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Validate repository health")
    sub.add_parser("index", help="Regenerate INDEX.md")

    p_search = sub.add_parser("search", help="Search memory records")
    p_search.add_argument("query", help="Search query")

    p_remember = sub.add_parser("remember", help="Create inbox candidate")
    p_remember.add_argument("--type", required=True, choices=list(TYPE_TO_CATEGORY))
    p_remember.add_argument("--title", required=True)
    p_remember.add_argument("--source", required=True)
    p_remember.add_argument("--confidence", required=True, choices=["high", "medium", "low"])
    p_remember.add_argument("--sensitivity", required=True, choices=["public", "internal", "restricted"])
    p_remember.add_argument("--tag", action="append", default=[])
    p_remember.add_argument("text", help="Record body text")

    p_promote = sub.add_parser("promote", help="Promote inbox candidate to canonical")
    p_promote.add_argument("inbox_file")
    p_promote.add_argument("--category", choices=list(TYPE_TO_CATEGORY.values()))

    p_supersede = sub.add_parser("supersede", help="Mark old record superseded by new")
    p_supersede.add_argument("old_id")
    p_supersede.add_argument("new_id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "doctor": cmd_doctor,
        "index": cmd_index,
        "search": cmd_search,
        "remember": cmd_remember,
        "promote": cmd_promote,
        "supersede": cmd_supersede,
    }
    return handlers[args.command](args)
