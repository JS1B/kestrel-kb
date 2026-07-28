"""Tests for Kestrel KB tooling."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

from kb_lib.index import generate_index  # noqa: E402
from kb_lib.parser import MemoryRecord, parse_memory_text, write_memory_file  # noqa: E402
from kb_lib.paths import find_root, inbox_dir  # noqa: E402
from kb_lib.search import search_records  # noqa: E402
from kb_lib.secrets import scan_secrets  # noqa: E402
from kb_lib.validator import validate_repository  # noqa: E402
from kb_lib.yaml_subset import dump_yaml_subset, parse_yaml_subset  # noqa: E402
from kb_lib.cli import main as cli_main  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_kb(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "kb"), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
    )


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

    def test_detects_inline_credential(self):
        findings = scan_secrets("api_key: supersecretvalue123")
        self.assertTrue(findings)

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

    def test_search_smoke_cli(self):
        result = run_kb("search", "sops age")
        self.assertEqual(result.returncode, 0)
        self.assertIn("secrets-policy-sops-age", result.stdout)


class TestValidator(unittest.TestCase):
    def test_doctor_passes_on_repo(self):
        result = run_kb("doctor")
        self.assertEqual(result.returncode, 0, result.stderr)


class TestRememberPromote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        for rel in [
            "schemas/memory.schema.json",
            "memory/preferences",
            "memory/decisions",
            "memory/capabilities",
            "memory/runbooks",
            "memory/constraints",
            "inbox",
        ]:
            src = REPO_ROOT / rel
            dst = self.root / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
            else:
                dst.mkdir(parents=True, exist_ok=True)

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
        rc = cli_main(["promote", str(inbox_file)])
        self.assertEqual(rc, 0)
        self.assertFalse(inbox_file.exists())
        canonical = self.root / "memory/decisions/promote-me.md"
        self.assertTrue(canonical.is_file())
        self.assertIn("status: active", canonical.read_text())

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


class TestSupersede(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        for rel in [
            "schemas/memory.schema.json",
            "memory/decisions",
            "inbox",
            "INDEX.md",
        ]:
            src = REPO_ROOT / rel
            dst = self.root / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
            else:
                dst.mkdir(parents=True, exist_ok=True)

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
        # new already exists; make new supersede old first
        cli_main(["supersede", "old-policy", "new-policy"])
        # Attempt to supersede new with old (would cycle)
        old_path = self.root / "memory/decisions/old-policy.md"
        new_path = self.root / "memory/decisions/new-policy.md"
        # Manually set old to active and add new to its supersedes to force cycle
        old_text = old_path.read_text().replace("status: superseded", "status: active")
        old_path.write_text(old_text)
        rc = cli_main(["supersede", "new-policy", "old-policy"])
        self.assertNotEqual(rc, 0)


class TestConcurrency(unittest.TestCase):
    def test_lock_file_used_by_index(self):
        result = run_kb("index")
        self.assertEqual(result.returncode, 0)
        lock_dir = REPO_ROOT / ".lock"
        self.assertTrue(lock_dir.is_dir())


class TestPyCompile(unittest.TestCase):
    def test_all_modules_compile(self):
        for path in (REPO_ROOT / "tools").rglob("*.py"):
            compile(path.read_text(), str(path), "exec")


if __name__ == "__main__":
    unittest.main()
