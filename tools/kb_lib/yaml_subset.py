"""Minimal YAML subset parser for frontmatter (stdlib only)."""

from __future__ import annotations

import re
from typing import Any

_SCALAR_RE = re.compile(r"^([^:\s#][^:]*?):\s*(.*)$")
_LIST_ITEM_RE = re.compile(r"^-\s+(.+)$")
_INLINE_LIST_RE = re.compile(r"^\[(.*)\]$")


class YAMLParseError(ValueError):
    pass


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _parse_inline_list(value: str) -> list[str]:
    match = _INLINE_LIST_RE.match(value.strip())
    if not match:
        raise YAMLParseError(f"Invalid inline list: {value!r}")
    inner = match.group(1).strip()
    if not inner:
        return []
    parts = [p.strip() for p in inner.split(",")]
    return [_strip_quotes(p) for p in parts if p]


def parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse a restricted YAML mapping: scalars and lists only."""
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _SCALAR_RE.match(line)
        if not match:
            raise YAMLParseError(f"Invalid line: {line!r}")
        key = match.group(1).strip()
        rest = match.group(2).strip()
        if rest == "":
            items: list[str] = []
            while i < len(lines):
                next_line = lines[i]
                if not next_line.strip():
                    i += 1
                    continue
                if not next_line.startswith("  "):
                    break
                item_match = _LIST_ITEM_RE.match(next_line.strip())
                if not item_match:
                    raise YAMLParseError(f"Expected list item: {next_line!r}")
                items.append(_strip_quotes(item_match.group(1).strip()))
                i += 1
            result[key] = items
        elif rest.startswith("[") and rest.endswith("]"):
            result[key] = _parse_inline_list(rest)
        else:
            result[key] = _strip_quotes(rest)
    return result


def dump_yaml_subset(data: dict[str, Any]) -> str:
    """Serialize mapping to restricted YAML subset."""
    lines: list[str] = []
    for key in sorted(data.keys()):
        value = data[key]
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        else:
            scalar = str(value)
            if any(c in scalar for c in (":", "#", "\n")):
                lines.append(f'{key}: "{scalar}"')
            else:
                lines.append(f"{key}: {scalar}")
    return "\n".join(lines) + "\n"
