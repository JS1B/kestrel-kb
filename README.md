# Kestrel Operational Knowledge Base

Kestrel's **operational memory** — confirmed preferences, decisions, capabilities, constraints, and runbooks. Separate from Piotr's `self-model-kb` (evidence/profile/claims).

## Security boundary

- **In scope:** operational facts, policies, runbooks, capabilities.
- **Never store:** secrets, credentials, raw transcripts, notification payloads, or private file dumps.
- Secrets live in SOPS+Age `.env.enc` per service; plaintext `.env` stays local and untracked.

## Workflow

1. Session start: read `INDEX.md`, then `./tools/kb search <query>` for task relevance.
2. New facts: `./tools/kb remember ...` → `inbox/` (candidate).
3. Validate and promote: `./tools/kb promote inbox/<file>.md`.
4. Updates: `./tools/kb supersede OLD_ID NEW_ID` — never silently rewrite canonical records.
5. Before commit handoff: `./tools/kb index && ./tools/kb doctor`.

Mutating commands share a repo-wide lock at `.lock/kb.lock`. `promote` accepts only direct `inbox/*.md` files inside this repo.

See [docs/WORKFLOW.md](docs/WORKFLOW.md) and [docs/DERIVED-GRAPH.md](docs/DERIVED-GRAPH.md).

## Commands

```bash
./tools/kb doctor                         # validate all records + index freshness
./tools/kb index                          # regenerate INDEX.md
./tools/kb search QUERY                   # deterministic metadata/body search
./tools/kb remember --type ... --title ... --source ... \
  --confidence high --sensitivity internal [--tag TAG] "body text"
./tools/kb promote inbox/<file>.md        # move candidate to canonical memory
./tools/kb supersede OLD_ID NEW_ID        # mark old superseded, link in new record
```

## Layout

- `memory/{preferences,decisions,capabilities,runbooks,constraints}/` — canonical records
- `inbox/` — unreviewed candidates
- `schemas/memory.schema.json` — metadata contract
- `tools/kb` — stdlib-only CLI
