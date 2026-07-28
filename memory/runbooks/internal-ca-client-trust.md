---
confidence: high
created: 2026-07-29
id: internal-ca-client-trust
review_after: 2027-01-25
sensitivity: internal
source: user-requested 2026-07-29; traefik install-home-lab-ca-trust.sh
status: active
supersedes: []
tags:
  - tls
  - ca
  - homelab
type: runbook
updated: 2026-07-29
---
# Internal CA client trust

**Runbook:** Trust the Rock Homelab Root CA for `*.home.lab` HTTPS.

On rock (user shell trust, no sudo):

```bash
cd /home/radxa/homelab/infrastructure/reverse-proxy/traefik
scripts/verify-home-lab-ca.sh
scripts/install-home-lab-ca-trust.sh
source ~/.config/kestrel/pki/home-lab/trust.env
curl https://homepage.home.lab/
```

Optional host-wide trust (privileged):

```bash
INSTALL_SYSTEM_TRUST=1 scripts/install-home-lab-ca-trust.sh
```

Other clients: install `data/certs/home-lab-root.cert.pem` as a trusted root.
After leaf renew (`generate-home-lab-ca.sh --renew-leaf`), re-run install trust.
After `--force` CA rotation, reinstall the new root on every client.

Secrets: CA private keys stay under `~/.config/kestrel/pki/home-lab/` — never commit.
