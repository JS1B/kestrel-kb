---
confidence: high
created: 2026-07-28
id: ha-notification-capability
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; homelab HA integration
status: active
supersedes: []
tags:
  - homeassistant
  - notifications
type: capability
updated: 2026-07-28
---
# HA notification capability

**Capability:** `kestrel-notify --title "Kestrel" "message"`

- Webhook URL is a local-only secret — never store in this KB.
- Use for user-requested reminders, important completions, and actionable blockers.
- No secrets or spam in message bodies.
- Delivery is uncertain; report honestly if notify fails.

See `.cursor/rules/kestrel-notifications.mdc`.
