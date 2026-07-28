---
confidence: high
created: 2026-07-28
id: secrets-policy-sops-age
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; homelab Phase D secrets policy
status: active
supersedes: []
tags:
  - secrets
  - sops
  - age
type: constraint
updated: 2026-07-28
---
# Secrets policy (SOPS + Age)

**Policy:**

- Encrypt secrets with SOPS + Age; commit `.env.enc` only.
- Plaintext `.env` stays local and untracked.
- Provide `.env.example` (no real secrets) when a service needs env vars.

**This KB never stores secrets, credentials, tokens, or webhook URLs.**
