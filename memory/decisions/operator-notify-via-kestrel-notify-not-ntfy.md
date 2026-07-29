---
confidence: high
created: 2026-07-29
id: operator-notify-via-kestrel-notify-not-ntfy
review_after: 2027-01-25
sensitivity: internal
source: user-confirmed 2026-07-29; corrects stale homelab ntfy backlog
status: active
supersedes: []
tags:
  - notifications
  - homelab
  - homeassistant
type: decision
updated: 2026-07-29
---
# Operator notify via kestrel-notify not ntfy

**Decision:** Do not plan or deploy a separate ntfy stack for operator/agent notifications.

Mobile notifications are already provided by the Home Assistant bridge: `kestrel-notify` (capability `ha-notification-capability`).

Prometheus Alertmanager for metric-rule paging remains optional and is not the same as operator notify. Homelab FEATURES/HANDOFF should not list ntfy as planned work.
