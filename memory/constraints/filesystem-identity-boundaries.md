---
confidence: high
created: 2026-07-28
id: filesystem-identity-boundaries
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; ~/homelab orchestration context
status: active
supersedes: []
tags:
  - identity
  - filesystem
  - git
type: constraint
updated: 2026-07-28
---
# Filesystem identity boundaries

**State/policy:**

| path | identity |
| --- | --- |
| `~/projects` | Piotr personal |
| `~/homelab` | Kestrel Git identity |
| `~/ai-workspace` | Kestrel Git identity |

Unix user remains `radxa` under minimal setup. Do not conflate personal and Kestrel paths when choosing commit identity or operational context.
