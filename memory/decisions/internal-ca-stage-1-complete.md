---
confidence: high
created: 2026-07-29
id: internal-ca-stage-1-complete
review_after: 2027-01-25
sensitivity: internal
source: user-requested 2026-07-29; verified live HTTPS + user trust on rock
status: superseded
supersedes:
  - internal-ca-stage-1
tags:
  - tls
  - ca
  - homelab
type: decision
updated: 2026-07-29
---
# Internal CA stage 1 complete

**Decision:** Internal CA stage 1 is complete on rock.

Verified 2026-07-29:
- `scripts/verify-home-lab-ca.sh` passes (P-256 root/intermediate/leaf, name constraints, SANs).
- Parallel HTTP/HTTPS live for homepage, chat, grafana, prometheus, git, sure, homeassistant, traefik dashboard.
- User trust via combined CA bundle at `~/.config/kestrel/pki/home-lab/ca-bundle.pem` and `trust.env` (sourced from shell zprofile/zshrc).
- Public root fingerprint (SHA256): ED:BA:C2:E0:21:1D:22:CC:BD:3C:B8:D7:D4:68:47:DD:12:59:C6:E2:AE:B5:6E:E8:0E:1A:B9:08:71:62:F9:D0

Still deferred (stage 2):
- Host-wide `update-ca-certificates` (needs sudo / INSTALL_SYSTEM_TRUST=1).
- HTTP→HTTPS redirects, Forgejo ROOT_URL/secure cookies, canonical HTTPS service URLs.
- Broad client trust beyond rock user shell.

Do not force HTTPS-only cutover until stage-2 gates pass.
