---
confidence: high
created: 2026-07-29
id: internal-ca-stage-1-complete-on-rock
review_after: 2027-01-25
sensitivity: internal
source: user-confirmed 2026-07-29; system trust installed on rock after interactive sudo
status: active
supersedes:
  - internal-ca-stage-1-complete
tags:
  - tls
  - ca
  - homelab
type: decision
updated: 2026-07-29
---
# Internal CA stage 1 complete on rock

**Decision:** Internal CA stage 1 is complete on rock, including host system trust.

Verified 2026-07-29:
- `scripts/verify-home-lab-ca.sh` passes.
- Parallel HTTP/HTTPS live for active `*.home.lab` services.
- User trust: `~/.config/kestrel/pki/home-lab/ca-bundle.pem` + `trust.env`.
- System trust: `/usr/local/share/ca-certificates/home-lab/home-lab-root.crt` via `update-ca-certificates`.
- Unset-env curl to `https://homepage.home.lab/` (and chat/git) returns 200.
- Public root fingerprint (SHA256): ED:BA:C2:E0:21:1D:22:CC:BD:3C:B8:D7:D4:68:47:DD:12:59:C6:E2:AE:B5:6E:E8:0E:1A:B9:08:71:62:F9:D0

Still deferred (stage 2):
- HTTP→HTTPS redirects, Forgejo ROOT_URL/secure cookies, canonical HTTPS service URLs.
- Client trust on non-rock devices (Arch laptop, Android, etc.).

Do not force HTTPS-only cutover until those clients trust the root.
