---
confidence: high
created: 2026-07-28
id: worker-topology-on-rock-with-kestrel-kb
review_after: 2027-01-24
sensitivity: internal
source: user-confirmed and live-verified 2026-07-28; homelab infrastructure/cursor-worker/
status: superseded
supersedes:
  - worker-topology-rock
tags:
  - topology
  - rock
  - self-model-kb
  - watchline
  - kestrel-kb
type: decision
updated: 2026-07-28
---
# Worker topology on rock with Kestrel KB

State: host rock runs two Cursor My Machines workers.

- rock anchors /home/radxa/homelab.
- rock-ai keeps /home/radxa/ai-workspace/self-model-kb as its first assignment/routing identity.
- rock-ai explicitly exposes self-model-kb, watchline, and kestrel-kb as three repository roots.
- Sessions choose project goals; Git operations remain repository-specific.
