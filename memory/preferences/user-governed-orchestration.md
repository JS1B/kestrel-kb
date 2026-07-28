---
confidence: high
created: 2026-07-28
id: user-governed-orchestration
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; homelab hierarchical orchestration rules
status: active
supersedes: []
tags:
  - orchestration
  - workflow
type: preference
updated: 2026-07-28
---
# User-governed orchestration

**Policy:** Substantial work follows an explicit execution contract:

- Explicit model role assignments (main, orchestrator, worker).
- Independent verification for consequential changes.
- Concise reports with trade-offs and rollback boundaries.
- User stays in the loop on meaningful direction choices.

Prefer small, testable steps before broad refactors or live cutovers.
