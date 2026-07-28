"""CLI command implementations."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from .index import generate_index
from .lock import LockTimeout, atomic_write, backup_file, repo_lock, restore_backups
from .parser import MemoryRecord, parse_memory_file, write_memory_file
from .path_safety import PathSafetyError, resolve_inbox_file
from .paths import (
    INBOX_STATUS,
    TYPE_TO_CATEGORY,
    category_dir,
    find_root,
    inbox_dir,
    index_path,
)
from .search import format_hits, search_records
from .validator import (
    ValidationReport,
    collect_overdue_review_warnings,
    load_all_records,
    validate_cross_record,
    validate_record_meta,
    validate_repository,
)

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "untitled"


def _regenerate_index(root: Path) -> None:
    records, _ = load_all_records(root)
    canonical = [r for r in records if not r.path.is_relative_to(inbox_dir(root))]
    atomic_write(index_path(root), generate_index(root, canonical))


def _parse_reference_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return date.fromisoformat(raw)


def cmd_doctor(args: argparse.Namespace) -> int:
    root = find_root()
    report = validate_repository(root, check_index=True)
    records, _ = load_all_records(root)
    today = _parse_reference_date(getattr(args, "today", None))
    review_warnings = collect_overdue_review_warnings(records, today=today)
    for issue in report.issues:
        print(f"{issue.level.upper()}: {issue.path}: {issue.message}", file=sys.stderr)
    for issue in review_warnings:
        print(f"WARNING: {issue.path}: {issue.message}", file=sys.stderr)
    if report.ok:
        print("ok: repository healthy")
        if review_warnings and args.strict_review:
            return 1
        return 0
    return 1


def cmd_session_check(args: argparse.Namespace) -> int:
    from .session_check import emit_session_check, overrides_allowed, run_session_check

    root = None
    if args.root:
        if not overrides_allowed():
            print(
                "refuse: --root requires KESTREL_KB_SESSION_CHECK_ALLOW_OVERRIDES=1 (test-only)",
                file=sys.stderr,
            )
            return 1
        root = Path(args.root).resolve()
    result = run_session_check(root=root)
    return emit_session_check(result)


def cmd_index(_args: argparse.Namespace) -> int:
    root = find_root()
    try:
        with repo_lock(root):
            _regenerate_index(root)
    except LockTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote {index_path(root)}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = find_root()
    hits = search_records(root, args.query)
    print(format_hits(hits, root))
    return 0


def cmd_remember(args: argparse.Namespace) -> int:
    root = find_root()
    today = date.today().isoformat()
    review = (date.today() + timedelta(days=180)).isoformat()

    try:
        with repo_lock(root):
            base_slug = _slugify(args.title)
            existing, _ = load_all_records(root)
            existing_ids = {r.id for r in existing}
            record_id = base_slug
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

            if target.exists():
                print(f"refuse: inbox file exists: {target}", file=sys.stderr)
                return 1

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
    backups: list = []

    try:
        with repo_lock(root):
            try:
                inbox_path = resolve_inbox_file(root, args.inbox_file)
            except PathSafetyError as exc:
                print(f"refuse: {exc}", file=sys.stderr)
                return 1

            inbox_backup = backup_file(inbox_path)
            index_backup = backup_file(index_path(root))
            backups = [inbox_backup, index_backup]

            record = parse_memory_file(inbox_path)
            category = TYPE_TO_CATEGORY[record.type]

            if args.category and args.category != category:
                print(
                    f"refuse: --category {args.category!r} does not match "
                    f"record type {record.type!r} (expected {category!r})",
                    file=sys.stderr,
                )
                return 1

            dest = category_dir(root, category) / f"{record.id}.md"
            if dest.exists():
                print(f"refuse overwrite: {dest}", file=sys.stderr)
                return 1

            today = date.today().isoformat()
            record.meta["status"] = "active"
            record.meta["updated"] = today
            record.path = dest

            report = ValidationReport()
            validate_record_meta(record, report, inbox=False)
            if report.errors:
                for issue in report.errors:
                    print(f"ERROR: {issue.path}: {issue.message}", file=sys.stderr)
                return 1

            write_memory_file(record, dest)
            inbox_path.unlink()

            records, _ = load_all_records(root)
            validate_cross_record(records, report)
            if report.errors:
                restore_backups(backups)
                if dest.exists():
                    dest.unlink(missing_ok=True)
                for issue in report.errors:
                    print(f"ROLLBACK: {issue.path}: {issue.message}", file=sys.stderr)
                return 1

            try:
                _regenerate_index(root)
            except Exception as exc:  # noqa: BLE001
                restore_backups(backups)
                if dest.exists():
                    dest.unlink(missing_ok=True)
                print(f"ROLLBACK: index: {exc}", file=sys.stderr)
                return 1
    except LockTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Promoted to {dest.relative_to(root)}")
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    root = find_root()
    old_id, new_id = args.old_id, args.new_id

    try:
        with repo_lock(root):
            records, _ = load_all_records(root)
            by_id = {r.id: r for r in records}
            if old_id not in by_id:
                print(f"unknown old id: {old_id}", file=sys.stderr)
                return 1
            if new_id not in by_id:
                print(f"unknown new id: {new_id}", file=sys.stderr)
                return 1
            old_record = by_id[old_id]
            new_record = by_id[new_id]

            backups = [
                backup_file(old_record.path),
                backup_file(new_record.path),
                backup_file(index_path(root)),
            ]

            today = date.today().isoformat()
            old_record.meta["status"] = "superseded"
            old_record.meta["updated"] = today
            supersedes = list(new_record.meta.get("supersedes", []))
            if old_id not in supersedes:
                supersedes.append(old_id)
            new_record.meta["supersedes"] = sorted(supersedes)
            new_record.meta["updated"] = today

            check = ValidationReport()
            validate_record_meta(
                old_record,
                check,
                inbox=old_record.path.is_relative_to(inbox_dir(root)),
            )
            validate_record_meta(
                new_record,
                check,
                inbox=new_record.path.is_relative_to(inbox_dir(root)),
            )
            validate_cross_record(records, check)

            if check.errors:
                for issue in check.errors:
                    print(f"ERROR: {issue.path}: {issue.message}", file=sys.stderr)
                return 1

            write_memory_file(old_record)
            write_memory_file(new_record)

            try:
                _regenerate_index(root)
                post_report = validate_repository(root, check_index=True)
                if not post_report.ok:
                    restore_backups(backups)
                    for issue in post_report.errors:
                        print(f"ROLLBACK: {issue.path}: {issue.message}", file=sys.stderr)
                    return 1
            except Exception as exc:  # noqa: BLE001
                restore_backups(backups)
                print(f"ROLLBACK: {exc}", file=sys.stderr)
                return 1
    except LockTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Superseded {old_id} -> {new_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb", description="Kestrel operational memory CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="Validate repository health")
    p_doctor.add_argument(
        "--strict-review",
        action="store_true",
        help="Exit nonzero when active records are past review_after",
    )
    p_doctor.add_argument(
        "--today",
        metavar="YYYY-MM-DD",
        help=argparse.SUPPRESS,
    )
    p_session = sub.add_parser("session-check", help="Validate session-start workspace readiness")
    p_session.add_argument(
        "--root",
        help=argparse.SUPPRESS,
    )
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
        "session-check": cmd_session_check,
        "index": cmd_index,
        "search": cmd_search,
        "remember": cmd_remember,
        "promote": cmd_promote,
        "supersede": cmd_supersede,
    }
    return handlers[args.command](args)
