---
confidence: high
created: 2026-07-28
id: live-host-caution
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; homelab planning rules
status: active
supersedes: []
tags:
  - docker
  - rollout
  - safety
type: runbook
updated: 2026-07-28
---
# Live-host caution

**Runbook:** Workers on the live homelab host are unsandboxed.

- Docker access is effectively privileged — treat container changes as host-impactful.
- Do not fight `sudo` or bypass host policy; surface blockers instead.
- Serial rollouts: one consequential live change at a time.
- Define rollback boundaries before cutover; verify after each step.

Call out downtime, data risk, and reversibility before irreversible changes.
