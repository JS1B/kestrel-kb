---
confidence: high
created: 2026-07-28
id: internal-ca-stage-1
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; homelab TLS/CA planning
status: superseded
supersedes: []
tags:
  - tls
  - ca
  - homelab
type: decision
updated: 2026-07-29
---
# Internal CA stage 1

**Policy (stage 1):** Run parallel HTTP and HTTPS for `*.home.lab` services.

- Redirects to HTTPS and canonical secure-cookie cutover are **deferred** until client trust for the internal CA is established.
- Do not force HTTPS-only redirects prematurely.

Revisit when internal CA trust is deployed broadly.
