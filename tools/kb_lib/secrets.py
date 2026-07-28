"""Secret-pattern guardrails for memory content."""

from __future__ import annotations

import re

# Patterns that should never appear in KB records
FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "GitHub personal access token"),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"), "GitHub OAuth token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "JWT"),
    (re.compile(r"AGE-SECRET-KEY-[A-Z0-9]{59}"), "Age secret key"),
]

# Line-start shell/env assignments (NAME=value or export NAME=value)
ASSIGNMENT_LINE_RE = re.compile(
    r"^(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=\s*(\S+)\s*$",
    re.MULTILINE,
)

# YAML-style keyed secrets at line start (frontmatter or body)
YAML_KEYED_SECRET_RE = re.compile(
    r"^(?!#)(?:-\s+)?"
    r"(?P<key>api[_-]?key|password|passwd|secret|token|webhook[_-]?url)"
    r"\s*:\s*(?P<val>\S+)",
    re.MULTILINE | re.IGNORECASE,
)

PLACEHOLDER_VALUE_RE = re.compile(
    r"^(?:"
    r"changeme|example|redacted|placeholder|none|null|undefined|"
    r"xxx+|your[_-]?|my[_-]?|insert[_-]?|replace[_-]?|"
    r"<\s*(?:secret|token|key|password|value)\s*>|"
    r"\.\.\.|xxx|\*+"
    r")$",
    re.IGNORECASE,
)

DOCUMENTED_ENV_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "PWD",
        "LANG",
        "TERM",
        "HOSTNAME",
        "EDITOR",
        "PYTHONPATH",
    }
)

TRANSCRIPT_MARKERS = [
    re.compile(r"<user_query>"),
    re.compile(r"^Assistant:\s", re.MULTILINE),
    re.compile(r"^Human:\s", re.MULTILINE),
]


def _is_placeholder_value(value: str) -> bool:
    stripped = value.strip().strip("'\"")
    if PLACEHOLDER_VALUE_RE.match(stripped):
        return True
    if stripped.startswith("${") and stripped.endswith("}"):
        return True
    if stripped in (".env", ".env.example", "your-api-key", "your_api_key"):
        return True
    return False


def scan_assignment_lines(text: str) -> list[str]:
    findings: list[str] = []
    for match in ASSIGNMENT_LINE_RE.finditer(text):
        name, value = match.group(1), match.group(2)
        if name in DOCUMENTED_ENV_NAMES:
            continue
        if _is_placeholder_value(value):
            continue
        if len(value) < 4:
            continue
        findings.append(f"env assignment {name}=")
    return findings


def scan_yaml_keyed_secrets(text: str) -> list[str]:
    findings: list[str] = []
    for match in YAML_KEYED_SECRET_RE.finditer(text):
        key = match.group("key").lower()
        val = match.group("val").strip().strip("'\"")
        if _is_placeholder_value(val):
            continue
        if len(val) < 4:
            continue
        findings.append(f"yaml keyed secret {key}")
    return findings


def scan_secrets(text: str) -> list[str]:
    findings: list[str] = []
    for pattern, label in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            findings.append(label)
    findings.extend(scan_assignment_lines(text))
    findings.extend(scan_yaml_keyed_secrets(text))
    for pattern in TRANSCRIPT_MARKERS:
        if pattern.search(text):
            findings.append("raw transcript marker")
            break
    return findings
