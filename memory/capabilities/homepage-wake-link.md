---
confidence: high
created: 2026-07-28
id: homepage-wake-link
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; homelab homepage service
status: active
supersedes: []
tags:
  - homepage
  - wake-on-lan
  - homeassistant
type: capability
updated: 2026-07-28
---
# Homepage Wake Link

**State:** Homepage exposes a fixed wake-only button via Home Assistant relay.

- 2 second rate limit between wake actions.
- No off/shutdown action exposed through this control.

Do not add an off action without explicit user decision and superseding this record.
