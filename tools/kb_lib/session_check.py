"""Session-start validation for Kestrel operational memory workspace."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .paths import TYPE_TO_CATEGORY, find_root, inbox_dir, index_path, memory_dir, schema_path
from .validator import validate_repository

DEFAULT_ROOT = Path("/home/radxa/ai-workspace/kestrel-kb")
DEFAULT_SELF_MODEL_KB = Path("/home/radxa/ai-workspace/self-model-kb")
DEFAULT_WATCHLINE = Path("/home/radxa/ai-workspace/watchline")
DEFAULT_HOMELAB = Path("/home/radxa/homelab")

# Test-only overrides; ignored in production unless ALLOW_OVERRIDES gate is set.
ENV_ALLOW_OVERRIDES = "KESTREL_KB_SESSION_CHECK_ALLOW_OVERRIDES"
ENV_ROOT = "KESTREL_KB_SESSION_CHECK_ROOT"
ENV_SELF_MODEL_KB = "KESTREL_KB_SESSION_CHECK_SELF_MODEL_KB"
ENV_WATCHLINE = "KESTREL_KB_SESSION_CHECK_WATCHLINE"
ENV_HOMELAB = "KESTREL_KB_SESSION_CHECK_HOMELAB"

GIT_PROBE_TIMEOUT_SEC = 5

REQUIRED_RULE = Path(".cursor/rules/kestrel-memory.mdc")
KB_EXECUTABLE = Path("tools/kb")


@dataclass
class SessionCheckResult:
    ok: bool = True
    lines: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.failures.append(message)
        self.lines.append(f"FAIL: {message}")

    def info(self, message: str) -> None:
        self.lines.append(f"ok: {message}")


def overrides_allowed() -> bool:
    return os.environ.get(ENV_ALLOW_OVERRIDES) == "1"


def _env_path(name: str) -> Path | None:
    if not overrides_allowed():
        return None
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw)


def resolve_session_paths(
    *,
    root: Path | None = None,
    self_model_kb: Path | None = None,
    watchline: Path | None = None,
    homelab: Path | None = None,
) -> dict[str, Path]:
    """Resolve paths; explicit kwargs override gated env overrides override production defaults."""
    return {
        "root": root if root is not None else (_env_path(ENV_ROOT) or DEFAULT_ROOT),
        "self_model_kb": (
            self_model_kb if self_model_kb is not None else (_env_path(ENV_SELF_MODEL_KB) or DEFAULT_SELF_MODEL_KB)
        ),
        "watchline": watchline if watchline is not None else (_env_path(ENV_WATCHLINE) or DEFAULT_WATCHLINE),
        "homelab": homelab if homelab is not None else (_env_path(ENV_HOMELAB) or DEFAULT_HOMELAB),
    }


def _reject_symlink(path: Path, label: str, result: SessionCheckResult) -> bool:
    try:
        if path.is_symlink():
            result.fail(f"{label} must not be a symlink: {path}")
            return False
    except OSError as exc:
        result.fail(f"{label} inaccessible: {path} ({exc})")
        return False
    return True


def _require_exists(path: Path, label: str, result: SessionCheckResult) -> bool:
    if not _reject_symlink(path, label, result):
        return False
    if not path.exists():
        result.fail(f"{label} missing: {path}")
        return False
    return True


def _require_directory(path: Path, label: str, result: SessionCheckResult) -> bool:
    if not _require_exists(path, label, result):
        return False
    if not path.is_dir():
        result.fail(f"{label} must be a directory: {path}")
        return False
    return True


def _require_regular_file(path: Path, label: str, result: SessionCheckResult) -> bool:
    if not _require_exists(path, label, result):
        return False
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            result.fail(f"{label} must be a regular file: {path}")
            return False
    except OSError as exc:
        result.fail(f"{label} inaccessible: {path} ({exc})")
        return False
    return True


def _require_executable(path: Path, label: str, result: SessionCheckResult) -> bool:
    if not _require_regular_file(path, label, result):
        return False
    if not os.access(path, os.X_OK):
        result.fail(f"{label} must be executable: {path}")
        return False
    return True


def _probe_git_worktree(path: Path, label: str, result: SessionCheckResult) -> bool:
    """Bounded local git metadata probe; does not read sibling working-tree files."""
    if shutil.which("git") is None:
        result.fail("git executable not found")
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=GIT_PROBE_TIMEOUT_SEC,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        result.fail(f"{label} git probe timed out after {GIT_PROBE_TIMEOUT_SEC}s: {path}")
        return False
    except OSError as exc:
        result.fail(f"{label} git probe failed: {path} ({exc})")
        return False

    if proc.returncode != 0 or proc.stdout != "true\n":
        result.fail(f"{label} must be a Git worktree: {path}")
        return False
    return True


def _validate_root_identity(root_input: Path, result: SessionCheckResult) -> Path | None:
    if not _reject_symlink(root_input, "root", result):
        return None
    if not _require_exists(root_input, "root", result):
        return None
    if not _require_directory(root_input, "root", result):
        return None

    resolved = root_input.resolve()
    if resolved.name != "kestrel-kb":
        result.fail(f"root must be kestrel-kb, got {resolved.name!r} at {resolved}")
        return None
    result.info(f"root is kestrel-kb ({resolved})")
    return resolved


def _validate_layout(root: Path, result: SessionCheckResult) -> None:
    for rel, label, checker in (
        (schema_path(root), "schema", _require_regular_file),
        (index_path(root), "INDEX.md", _require_regular_file),
        (root / KB_EXECUTABLE, "tools/kb", _require_executable),
        (root / REQUIRED_RULE, "kestrel-memory rule", _require_regular_file),
        (inbox_dir(root), "inbox/", _require_directory),
        (root / "docs", "docs/", _require_directory),
    ):
        checker(rel, label, result)

    mem = memory_dir(root)
    if not _require_directory(mem, "memory/", result):
        return
    for category in TYPE_TO_CATEGORY.values():
        _require_directory(mem / category, f"memory/{category}/", result)


def _validate_kb_structure(root: Path, result: SessionCheckResult) -> None:
    try:
        found = find_root(root)
    except FileNotFoundError as exc:
        result.fail(str(exc))
        return
    if found.resolve() != root.resolve():
        result.fail(f"schema marker resolves outside expected root: {found}")
        return

    report = validate_repository(root, check_index=True)
    for issue in report.issues:
        if issue.level == "error":
            result.fail(f"{issue.path}: {issue.message}")
        else:
            result.lines.append(f"WARN: {issue.path}: {issue.message}")
    if report.ok:
        result.info("repository structure and index freshness")


def _validate_sibling_repo(path: Path, name: str, result: SessionCheckResult) -> None:
    if not _require_directory(path, name, result):
        return
    if not _probe_git_worktree(path, name, result):
        return
    result.info(f"{name} present ({path})")


def _validate_homelab(path: Path, result: SessionCheckResult) -> None:
    if not _require_directory(path, "homelab", result):
        return
    if not _probe_git_worktree(path, "homelab", result):
        return
    result.info(f"homelab present ({path}); separate rock worker — not rock-ai primary")


def run_session_check(
    *,
    root: Path | None = None,
    self_model_kb: Path | None = None,
    watchline: Path | None = None,
    homelab: Path | None = None,
) -> SessionCheckResult:
    paths = resolve_session_paths(
        root=root,
        self_model_kb=self_model_kb,
        watchline=watchline,
        homelab=homelab,
    )
    result = SessionCheckResult()

    root_path = _validate_root_identity(paths["root"], result)
    if root_path is None:
        result.lines.insert(0, "session-check: failed")
        return result

    _validate_layout(root_path, result)
    if result.ok:
        _validate_kb_structure(root_path, result)

    for key, name in (
        ("self_model_kb", "self-model-kb"),
        ("watchline", "watchline"),
    ):
        sibling = paths[key]
        if not _reject_symlink(sibling, name, result):
            continue
        _validate_sibling_repo(sibling.resolve(), name, result)

    homelab_input = paths["homelab"]
    if _reject_symlink(homelab_input, "homelab", result):
        _validate_homelab(homelab_input.resolve(), result)

    if result.ok:
        result.lines.insert(0, "session-check: ok")
    else:
        result.lines.insert(0, "session-check: failed")
    return result


def emit_session_check(result: SessionCheckResult, stream=None) -> int:
    stream = stream or sys.stdout
    for line in result.lines:
        print(line, file=stream)
    return 0 if result.ok else 1
