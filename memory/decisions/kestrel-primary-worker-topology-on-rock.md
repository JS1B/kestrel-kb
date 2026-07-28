---
confidence: high
created: 2026-07-28
id: kestrel-primary-worker-topology-on-rock
review_after: 2027-01-24
sensitivity: internal
source: user-approved and live-verified 2026-07-28; homelab infrastructure/cursor-worker/
status: active
supersedes:
  - worker-topology-on-rock-with-kestrel-kb
tags:
  - topology
  - rock
  - kestrel-kb
  - self-model-kb
  - watchline
type: decision
updated: 2026-07-28
---
# Kestrel-primary worker topology on rock

State: host rock runs two Cursor My Machines workers.

- rock anchors /home/radxa/homelab.
- rock-ai uses /home/radxa/ai-workspace/kestrel-kb as WorkingDirectory and first assignment/routing identity so new sessions load Kestrel operational-memory rules.
- rock-ai explicitly exposes self-model-kb second and watchline third.
- Repo-targeted triggers for self-model-kb or watchline do not automatically match rock-ai; sessions can still access them and Git operations remain repository-specific.
