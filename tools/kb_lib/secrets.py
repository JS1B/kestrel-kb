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
    (re.compile(r"(?i)(?:password|passwd|secret|api[_-]?key)\s*[:=]\s*\S{8,}"), "inline credential"),
    (re.compile(r"AGE-SECRET-KEY-[A-Z0-9]{59}"), "Age secret key"),
    (re.compile(r"sops_age_key\.txt"), "SOPS age key file reference with content risk"),
]

TRANSCRIPT_MARKERS = [
    re.compile(r"<user_query>"),
    re.compile(r"^Assistant:\s", re.MULTILINE),
    re.compile(r"^Human:\s", re.MULTILINE),
]


def scan_secrets(text: str) -> list[str]:
    findings: list[str] = []
    for pattern, label in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            findings.append(label)
    for pattern in TRANSCRIPT_MARKERS:
        if pattern.search(text):
            findings.append("raw transcript marker")
            break
    return findings
