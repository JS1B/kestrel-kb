"""Tests for Kestrel KB tooling."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

from kb_lib.index import generate_index  # noqa: E402
from kb_lib.parser import MemoryRecord, parse_memory_text, write_memory_file  # noqa: E402
from kb_lib.path_safety import PathSafetyError, resolve_inbox_file  # noqa: E402
from kb_lib.paths import find_root, inbox_dir  # noqa: E402
from kb_lib.search import format_hits, search_records  # noqa: E402
from kb_lib.secrets import scan_assignment_lines, scan_secrets, scan_yaml_keyed_secrets  # noqa: E402
from kb_lib.lock import atomic_write, kb_lock_path  # noqa: E402
from kb_lib.yaml_subset import dump_yaml_subset, parse_yaml_subset  # noqa: E402
from kb_lib.cli import main as cli_main  # noqa: E402
from kb_lib.session_check import (  # noqa: E402
    ENV_ALLOW_OVERRIDES,
    ENV_ROOT,
    run_session_check,
)
from kb_lib.validator import collect_overdue_review_warnings, load_all_records  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_kb(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "kb"), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
    )


def scaffold_repo(root: Path, *, with_index: bool = False) -> None:
    for rel in [
        "schemas/memory.schema.json",
        "memory/preferences",
        "memory/decisions",
        "memory/capabilities",
        "memory/runbooks",
        "memory/constraints",
        "inbox",
        "docs",
        ".cursor/rules",
    ]:
        src = REPO_ROOT / rel
        dst = root / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
        else:
            dst.mkdir(parents=True, exist_ok=True)
    rule_src = REPO_ROOT / ".cursor/rules/kestrel-memory.mdc"
    if rule_src.is_file():
        shutil.copy(rule_src, root / ".cursor/rules/kestrel-memory.mdc")
    kb_src = REPO_ROOT / "tools/kb"
    kb_dst = root / "tools/kb"
    kb_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(kb_src, kb_dst)
    kb_dst.chmod(kb_dst.stat().st_mode | 0o111)
    if with_index:
        shutil.copy(REPO_ROOT / "INDEX.md", root / "INDEX.md")


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


@contextmanager
def env_override(**values: str | None):
    saved: dict[str, str | None] = {}
    for key, value in values.items():
        saved[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


class TestYamlSubset(unittest.TestCase):
    def test_parse_scalar_and_lists(self):
        text = "id: foo-bar\nsupersedes: []\ntags:\n  - alpha\n  - beta\n"
        data = parse_yaml_subset(text)
        self.assertEqual(data["id"], "foo-bar")
        self.assertEqual(data["supersedes"], [])
        self.assertEqual(data["tags"], ["alpha", "beta"])

    def test_roundtrip(self):
        data = {"id": "x", "tags": ["a"], "supersedes": []}
        parsed = parse_yaml_subset(dump_yaml_subset(data))
        self.assertEqual(parsed, data)


class TestParser(unittest.TestCase):
    SAMPLE = """---
id: test-record
type: decision
status: active
confidence: high
source: unit test
sensitivity: internal
created: 2026-07-28
updated: 2026-07-28
review_after: 2027-01-28
supersedes: []
tags: []
---
# Test Title

Body content here.
"""

    def test_parse_memory(self):
        record = parse_memory_text(self.SAMPLE)
        self.assertEqual(record.id, "test-record")
        self.assertEqual(record.title, "Test Title")
        self.assertIn("Body content", record.body)


class TestSecrets(unittest.TestCase):
    def test_detects_private_key(self):
        findings = scan_secrets("-----BEGIN PRIVATE KEY-----\nMIIE")
        self.assertTrue(any("private key" in f for f in findings))

    def test_detects_env_assignment(self):
        findings = scan_assignment_lines("API_KEY=supersecretvalue123\n")
        self.assertTrue(findings)

    def test_ignores_placeholder_assignment(self):
        findings = scan_assignment_lines("MY_API_KEY=changeme\n")
        self.assertEqual(findings, [])

    def test_ignores_export_placeholder(self):
        findings = scan_assignment_lines("export DATABASE_URL=example\n")
        self.assertEqual(findings, [])

    def test_detects_yaml_keyed_secret(self):
        findings = scan_yaml_keyed_secrets("api_key: supersecretvalue123\n")
        self.assertTrue(findings)

    def test_ignores_yaml_keyed_placeholder(self):
        findings = scan_yaml_keyed_secrets("password: changeme\n")
        self.assertEqual(findings, [])

    def test_ignores_prose_with_colon(self):
        findings = scan_yaml_keyed_secrets("Use the password: vault for access.\n")
        self.assertEqual(findings, [])

    def test_clean_text_ok(self):
        self.assertEqual(scan_secrets("operational policy only"), [])


class TestIndex(unittest.TestCase):
    def test_deterministic_index(self):
        root = find_root(REPO_ROOT)
        idx1 = generate_index(root)
        idx2 = generate_index(root)
        self.assertEqual(idx1, idx2)
        self.assertIn("github-primary-forgejo-secondary", idx1)


class TestSearch(unittest.TestCase):
    def test_search_finds_record(self):
        root = find_root(REPO_ROOT)
        hits = search_records(root, "forgejo github")
        ids = [h.record.id for h in hits]
        self.assertIn("github-primary-forgejo-secondary", ids)

    def test_search_relative_paths(self):
        root = find_root(REPO_ROOT)
        hits = search_records(root, "forgejo")
        self.assertTrue(hits)
        output = format_hits(hits, root)
        self.assertNotIn(str(root), output)
        self.assertIn("memory/decisions/", output)

    def test_search_smoke_cli(self):
        result = run_kb("search", "sops age")
        self.assertEqual(result.returncode, 0)
        self.assertIn("secrets-policy-sops-age", result.stdout)
        self.assertIn("memory/constraints/", result.stdout)


class TestValidator(unittest.TestCase):
    def test_doctor_passes_on_repo(self):
        result = run_kb("doctor")
        self.assertEqual(result.returncode, 0, result.stderr)


class TestRememberPromote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        scaffold_repo(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_remember_creates_inbox_candidate(self):
        os.chdir(self.root)
        rc = cli_main(
            [
                "remember",
                "--type",
                "preference",
                "--title",
                "Test Preference",
                "--source",
                "unit test",
                "--confidence",
                "medium",
                "--sensitivity",
                "internal",
                "--tag",
                "test",
                "Some body text.",
            ]
        )
        self.assertEqual(rc, 0)
        inbox_files = list(inbox_dir(self.root).glob("*.md"))
        self.assertEqual(len(inbox_files), 1)
        text = inbox_files[0].read_text()
        self.assertIn("status: candidate", text)

    def test_promote_moves_to_canonical(self):
        os.chdir(self.root)
        cli_main(
            [
                "remember",
                "--type",
                "decision",
                "--title",
                "Promote Me",
                "--source",
                "unit test",
                "--confidence",
                "high",
                "--sensitivity",
                "internal",
                "Promote body.",
            ]
        )
        inbox_file = next(inbox_dir(self.root).glob("*.md"))
        rel = inbox_file.relative_to(self.root).as_posix()
        rc = cli_main(["promote", rel])
        self.assertEqual(rc, 0)
        self.assertFalse(inbox_file.exists())
        canonical = self.root / "memory/decisions/promote-me.md"
        self.assertTrue(canonical.is_file())
        self.assertIn("status: active", canonical.read_text())

    def test_promote_category_mismatch_rejected(self):
        os.chdir(self.root)
        cli_main(
            [
                "remember",
                "--type",
                "decision",
                "--title",
                "Cat Mismatch",
                "--source",
                "unit test",
                "--confidence",
                "high",
                "--sensitivity",
                "internal",
                "Body text.",
            ]
        )
        inbox_file = next(inbox_dir(self.root).glob("*.md"))
        rc = cli_main(["promote", inbox_file.name, "--category", "preferences"])
        self.assertNotEqual(rc, 0)
        self.assertTrue(inbox_file.exists())

    def test_collision_safe_slug(self):
        os.chdir(self.root)
        for _ in range(2):
            cli_main(
                [
                    "remember",
                    "--type",
                    "preference",
                    "--title",
                    "Same Title",
                    "--source",
                    "unit test",
                    "--confidence",
                    "low",
                    "--sensitivity",
                    "public",
                    "body",
                ]
            )
        files = list(inbox_dir(self.root).glob("*.md"))
        ids = set()
        for f in files:
            record = parse_memory_text(f.read_text(), path=f)
            ids.add(record.id)
        self.assertEqual(len(ids), 2)


class TestPromotePathSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        scaffold_repo(self.root)
        self.outside = Path(self.tmp) / "outside.md"
        self.outside.write_bytes(b"OUTSIDE_SECRET_CONTENT")
        os.chdir(self.root)
        cli_main(
            [
                "remember",
                "--type",
                "decision",
                "--title",
                "Safe Candidate",
                "--source",
                "unit test",
                "--confidence",
                "high",
                "--sensitivity",
                "internal",
                "Safe body.",
            ]
        )
        self.inbox_file = next(inbox_dir(self.root).glob("*.md"))
        self.inbox_bytes = self.inbox_file.read_bytes()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_reject_external_absolute(self):
        rc = cli_main(["promote", str(self.outside)])
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.outside.read_bytes(), b"OUTSIDE_SECRET_CONTENT")
        self.assertEqual(self.inbox_file.read_bytes(), self.inbox_bytes)

    def test_reject_traversal(self):
        rc = cli_main(["promote", "../../outside.md"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.outside.read_bytes(), b"OUTSIDE_SECRET_CONTENT")

    def test_reject_non_inbox_relative(self):
        canonical = self.root / "memory/decisions/fake.md"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("# Fake\n\nBody.\n")
        rc = cli_main(["promote", "memory/decisions/fake.md"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.inbox_file.read_bytes(), self.inbox_bytes)

    def test_reject_inbox_symlink_to_outside(self):
        self.inbox_file.unlink()
        link = inbox_dir(self.root) / "evil-link.md"
        link.symlink_to(self.outside)
        rc = cli_main(["promote", "evil-link.md"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.outside.read_bytes(), b"OUTSIDE_SECRET_CONTENT")
        self.assertTrue(link.is_symlink())
        self.assertFalse((self.root / "memory/decisions").joinpath("evil-link.md").exists())

    def test_reject_inbox_symlink_to_inbox_file(self):
        target = inbox_dir(self.root) / "real-target.md"
        shutil.copy(self.inbox_file, target)
        target_bytes = target.read_bytes()
        self.inbox_file.unlink()
        link = inbox_dir(self.root) / "alias-link.md"
        link.symlink_to(target)
        rc = cli_main(["promote", "alias-link.md"])
        self.assertNotEqual(rc, 0)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), target_bytes)
        self.assertFalse((self.root / "memory/decisions/alias-link.md").exists())

    def test_resolve_inbox_rejects_nested(self):
        nested = inbox_dir(self.root) / "nested"
        nested.mkdir()
        nested_file = nested / "nested.md"
        nested_file.write_text("# N\n\nBody.\n")
        with self.assertRaises(PathSafetyError):
            resolve_inbox_file(self.root, "inbox/nested/nested.md")


class TestSymlinkScanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        scaffold_repo(self.root, with_index=True)
        os.chdir(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write_canonical(self, rid: str, body_extra: str = "") -> Path:
        meta = {
            "id": rid,
            "type": "decision",
            "status": "active",
            "confidence": "high",
            "source": "test",
            "sensitivity": "internal",
            "created": "2026-07-28",
            "updated": "2026-07-28",
            "review_after": "2027-01-28",
            "supersedes": [],
            "tags": [],
        }
        path = self.root / f"memory/decisions/{rid}.md"
        write_memory_file(
            MemoryRecord(
                path=path,
                meta=meta,
                body=f"# Title\n\nVisible content. {body_extra}\n",
            )
        )
        return path

    def test_doctor_reports_canonical_symlink(self):
        real = self._write_canonical("real-record")
        link = self.root / "memory/decisions/evil-link.md"
        if link.exists():
            link.unlink()
        link.symlink_to(real)
        result = run_kb("doctor", cwd=self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr.lower())

    def test_search_ignores_symlink_outside_content(self):
        outside = self.root / "outside-secret.md"
        outside.write_text("# Outside\n\nUNIQUE_OUTSIDE_SYMLINK_TOKEN_xyz\n")
        link = self.root / "memory/decisions/outside-link.md"
        link.symlink_to(outside)
        hits = search_records(self.root, "UNIQUE_OUTSIDE_SYMLINK_TOKEN_xyz")
        self.assertEqual(hits, [])
        self.assertEqual(outside.read_text(), "# Outside\n\nUNIQUE_OUTSIDE_SYMLINK_TOKEN_xyz\n")


class TestAtomicWrite(unittest.TestCase):
    def test_fsync_parent_after_replace(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            target = tmp / "out.md"
            with patch("kb_lib.lock.os.fsync") as mock_fsync:
                atomic_write(target, "hello")
            self.assertGreaterEqual(mock_fsync.call_count, 2)
            self.assertEqual(target.read_text(), "hello")
        finally:
            shutil.rmtree(tmp)


class TestPromoteRollback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        scaffold_repo(self.root, with_index=True)
        os.chdir(self.root)
        cli_main(
            [
                "remember",
                "--type",
                "decision",
                "--title",
                "Rollback Test",
                "--source",
                "unit test",
                "--confidence",
                "high",
                "--sensitivity",
                "internal",
                "Rollback body.",
            ]
        )
        self.inbox_file = next(inbox_dir(self.root).glob("*.md"))
        self.inbox_bytes = self.inbox_file.read_bytes()
        self.index_bytes = (self.root / "INDEX.md").read_bytes()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_promote_rollback_on_cross_record_failure(self):
        rel = self.inbox_file.relative_to(self.root).as_posix()

        def fail_validate(records, report):
            report.add("error", "injected", "forced failure")

        with patch("kb_lib.cli.validate_cross_record", side_effect=fail_validate):
            rc = cli_main(["promote", rel])

        self.assertNotEqual(rc, 0)
        self.assertEqual(self.inbox_file.read_bytes(), self.inbox_bytes)
        self.assertFalse((self.root / "memory/decisions/rollback-test.md").exists())
        self.assertEqual((self.root / "INDEX.md").read_bytes(), self.index_bytes)


class TestSupersede(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        scaffold_repo(self.root, with_index=True)

        meta = {
            "id": "old-policy",
            "type": "decision",
            "status": "active",
            "confidence": "high",
            "source": "test",
            "sensitivity": "internal",
            "created": "2026-07-28",
            "updated": "2026-07-28",
            "review_after": "2027-01-28",
            "supersedes": [],
            "tags": [],
        }
        for rid, title in (("old-policy", "Old"), ("new-policy", "New")):
            m = dict(meta)
            m["id"] = rid
            write_memory_file(
                MemoryRecord(
                    path=self.root / f"memory/decisions/{rid}.md",
                    meta=m,
                    body=f"# {title}\n\nContent.\n",
                )
            )
        run_kb("index", cwd=self.root)
        self.old_bytes = (self.root / "memory/decisions/old-policy.md").read_bytes()
        self.new_bytes = (self.root / "memory/decisions/new-policy.md").read_bytes()
        self.index_bytes = (self.root / "INDEX.md").read_bytes()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_supersede_updates_status(self):
        os.chdir(self.root)
        rc = cli_main(["supersede", "old-policy", "new-policy"])
        self.assertEqual(rc, 0)
        old = (self.root / "memory/decisions/old-policy.md").read_text()
        new = (self.root / "memory/decisions/new-policy.md").read_text()
        self.assertIn("status: superseded", old)
        self.assertIn("old-policy", new)

    def test_supersede_cycle_rejected(self):
        os.chdir(self.root)
        cli_main(["supersede", "old-policy", "new-policy"])
        old_path = self.root / "memory/decisions/old-policy.md"
        old_text = old_path.read_text().replace("status: superseded", "status: active")
        old_path.write_text(old_text)
        rc = cli_main(["supersede", "new-policy", "old-policy"])
        self.assertNotEqual(rc, 0)

    def test_supersede_rollback_on_post_validation_failure(self):
        os.chdir(self.root)

        class FakeReport:
            ok = False

            @property
            def errors(self):
                return [type("E", (), {"path": "x", "message": "injected"})()]

        with patch("kb_lib.cli.validate_repository", return_value=FakeReport()):
            rc = cli_main(["supersede", "old-policy", "new-policy"])

        self.assertNotEqual(rc, 0)
        self.assertEqual(
            (self.root / "memory/decisions/old-policy.md").read_bytes(),
            self.old_bytes,
        )
        self.assertEqual(
            (self.root / "memory/decisions/new-policy.md").read_bytes(),
            self.new_bytes,
        )
        self.assertEqual((self.root / "INDEX.md").read_bytes(), self.index_bytes)


class TestConcurrentRemember(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        scaffold_repo(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_concurrent_same_title_unique_ids(self):
        os.chdir(self.root)
        errors: list[int] = []

        def worker():
            rc = cli_main(
                [
                    "remember",
                    "--type",
                    "preference",
                    "--title",
                    "Concurrent Title",
                    "--source",
                    "unit test",
                    "--confidence",
                    "low",
                    "--sensitivity",
                    "public",
                    "concurrent body",
                ]
            )
            errors.append(rc)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertTrue(all(rc == 0 for rc in errors), errors)
        ids = set()
        for f in inbox_dir(self.root).glob("*.md"):
            ids.add(parse_memory_text(f.read_text(), path=f).id)
        self.assertEqual(len(ids), 6)


class TestConcurrency(unittest.TestCase):
    def test_repo_lock_file(self):
        result = run_kb("index")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(kb_lock_path(REPO_ROOT).parent.is_dir())


class TestPyCompile(unittest.TestCase):
    def test_all_modules_compile(self):
        for path in (REPO_ROOT / "tools").rglob("*.py"):
            compile(path.read_text(), str(path), "exec")


class TestSessionCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)
        self.root = self.base / "kestrel-kb"
        self.self_model = self.base / "self-model-kb"
        self.watchline = self.base / "watchline"
        self.homelab = self.base / "homelab"
        scaffold_repo(self.root, with_index=True)
        for sibling in (self.self_model, self.watchline, self.homelab):
            sibling.mkdir()
            init_git_repo(sibling)
        run_kb("index", cwd=self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_session_check_success(self):
        result = run_session_check(
            root=self.root,
            self_model_kb=self.self_model,
            watchline=self.watchline,
            homelab=self.homelab,
        )
        self.assertTrue(result.ok, result.failures)
        self.assertIn("session-check: ok", result.lines[0])

    def test_session_check_missing_schema(self):
        (self.root / "schemas/memory.schema.json").unlink()
        result = run_session_check(
            root=self.root,
            self_model_kb=self.self_model,
            watchline=self.watchline,
            homelab=self.homelab,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("schema" in f.lower() for f in result.failures))

    def test_session_check_rejects_symlink_root(self):
        link = self.base / "kestrel-link"
        link.symlink_to(self.root)
        result = run_session_check(
            root=link,
            self_model_kb=self.self_model,
            watchline=self.watchline,
            homelab=self.homelab,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("symlink" in f.lower() for f in result.failures))

    def test_session_check_rejects_non_git_sibling(self):
        non_git = self.base / "watchline-bad"
        non_git.mkdir()
        result = run_session_check(
            root=self.root,
            self_model_kb=self.self_model,
            watchline=non_git,
            homelab=self.homelab,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("git" in f.lower() for f in result.failures))

    def test_session_check_rejects_empty_git_dir(self):
        fake = self.base / "watchline-empty-git"
        fake.mkdir()
        (fake / ".git").mkdir()
        result = run_session_check(
            root=self.root,
            self_model_kb=self.self_model,
            watchline=fake,
            homelab=self.homelab,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("git" in f.lower() for f in result.failures))

    def test_session_check_rejects_fake_git_file(self):
        fake = self.base / "watchline-fake-git"
        fake.mkdir()
        (fake / ".git").write_text("not a gitdir\n")
        result = run_session_check(
            root=self.root,
            self_model_kb=self.self_model,
            watchline=fake,
            homelab=self.homelab,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("git" in f.lower() for f in result.failures))

    def test_session_check_missing_root_reports_missing(self):
        missing = self.base / "kestrel-kb-missing"
        result = run_session_check(
            root=missing,
            self_model_kb=self.self_model,
            watchline=self.watchline,
            homelab=self.homelab,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("missing" in f.lower() for f in result.failures))
        self.assertFalse(any("must be kestrel-kb" in f for f in result.failures))

    def test_session_check_wrong_basename_after_exists(self):
        wrong = self.base / "not-kestrel-kb"
        wrong.mkdir()
        result = run_session_check(
            root=wrong,
            self_model_kb=self.self_model,
            watchline=self.watchline,
            homelab=self.homelab,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("must be kestrel-kb" in f for f in result.failures))

    def test_env_override_ignored_without_gate(self):
        fake = self.base / "env-redirect-missing"
        with env_override(**{ENV_ROOT: str(fake), ENV_ALLOW_OVERRIDES: None}):
            result = run_session_check(
                self_model_kb=self.self_model,
                watchline=self.watchline,
                homelab=self.homelab,
            )
        self.assertFalse(any(str(fake) in f for f in result.failures))

    def test_gated_env_override_works(self):
        with env_override(**{ENV_ROOT: str(self.root), ENV_ALLOW_OVERRIDES: "1"}):
            result = run_session_check(
                self_model_kb=self.self_model,
                watchline=self.watchline,
                homelab=self.homelab,
            )
        self.assertTrue(result.ok, result.failures)

    def test_cli_root_refused_without_gate(self):
        rc = cli_main(["session-check", "--root", str(self.root)])
        self.assertEqual(rc, 1)

    def test_cli_root_allowed_with_gate(self):
        with env_override(**{ENV_ALLOW_OVERRIDES: "1"}):
            buf = StringIO()
            with redirect_stderr(buf):
                rc = cli_main(["session-check", "--root", str(self.root)])
        self.assertEqual(rc, 0, buf.getvalue())

    def test_session_check_no_mutation(self):
        before = {
            p: p.read_bytes() if p.is_file() else None
            for p in self.root.rglob("*")
            if p.is_file()
        }
        run_session_check(
            root=self.root,
            self_model_kb=self.self_model,
            watchline=self.watchline,
            homelab=self.homelab,
        )
        after = {
            p: p.read_bytes() if p.is_file() else None
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_session_check_does_not_read_sibling_contents(self):
        secret = self.self_model / "SECRET_SHOULD_NOT_BE_READ.txt"
        secret.write_text("PRIVATE")
        result = run_session_check(
            root=self.root,
            self_model_kb=self.self_model,
            watchline=self.watchline,
            homelab=self.homelab,
        )
        self.assertTrue(result.ok)
        self.assertNotIn("PRIVATE", "\n".join(result.lines))

    def test_session_check_cli_smoke(self):
        result = run_kb("session-check")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


class TestReviewAfterDoctor(unittest.TestCase):
    REF_TODAY = "2026-07-28"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        scaffold_repo(self.root, with_index=True)
        os.chdir(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write_record(self, rid: str, status: str, review_after: str) -> None:
        meta = {
            "id": rid,
            "type": "decision",
            "status": status,
            "confidence": "high",
            "source": "test",
            "sensitivity": "internal",
            "created": "2026-07-28",
            "updated": "2026-07-28",
            "review_after": review_after,
            "supersedes": [],
            "tags": [],
        }
        write_memory_file(
            MemoryRecord(
                path=self.root / f"memory/decisions/{rid}.md",
                meta=meta,
                body=f"# {rid}\n\nBody.\n",
            )
        )

    def _doctor(self, *args: str) -> tuple[int, str]:
        buf = StringIO()
        with redirect_stderr(buf):
            rc = cli_main(["doctor", *args])
        return rc, buf.getvalue()

    def test_overdue_before_today_warns_default_exit_zero(self):
        self._write_record("overdue-policy", "active", "2026-07-27")
        run_kb("index", cwd=self.root)
        rc, err = self._doctor("--today", self.REF_TODAY)
        self.assertEqual(rc, 0, err)
        self.assertIn("overdue-policy", err)
        self.assertIn("WARNING", err)

    def test_equal_today_not_overdue(self):
        self._write_record("due-today", "active", self.REF_TODAY)
        run_kb("index", cwd=self.root)
        records, _ = load_all_records(self.root)
        warnings = collect_overdue_review_warnings(
            records,
            today=__import__("datetime").date.fromisoformat(self.REF_TODAY),
        )
        self.assertEqual(warnings, [])
        rc, err = self._doctor("--today", self.REF_TODAY)
        self.assertEqual(rc, 0, err)
        self.assertNotIn("due-today", err)

    def test_after_today_not_overdue(self):
        self._write_record("future-policy", "active", "2026-07-29")
        run_kb("index", cwd=self.root)
        rc, err = self._doctor("--today", self.REF_TODAY)
        self.assertEqual(rc, 0, err)
        self.assertNotIn("future-policy", err)

    def test_strict_review_exits_nonzero_when_overdue(self):
        self._write_record("overdue-strict", "active", "2026-01-01")
        run_kb("index", cwd=self.root)
        rc, err = self._doctor("--today", self.REF_TODAY, "--strict-review")
        self.assertEqual(rc, 1)
        self.assertIn("overdue-strict", err)

    def test_strict_review_exits_zero_when_none_overdue(self):
        self._write_record("fresh-policy", "active", "2026-12-31")
        run_kb("index", cwd=self.root)
        rc, err = self._doctor("--today", self.REF_TODAY, "--strict-review")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("WARNING", err)

    def test_superseded_not_warned(self):
        self._write_record("old-overdue", "superseded", "2020-01-01")
        run_kb("index", cwd=self.root)
        rc, err = self._doctor("--today", self.REF_TODAY)
        self.assertEqual(rc, 0, err)
        self.assertNotIn("old-overdue", err)


if __name__ == "__main__":
    unittest.main()
