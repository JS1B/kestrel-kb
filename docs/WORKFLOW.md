# Memory Workflow

Lifecycle for Kestrel operational memory: **candidate → validate → promote → supersede**.

## States

| status | location | meaning |
| --- | --- | --- |
| `candidate` | `inbox/` | Unreviewed; may be inferred or awaiting confirmation |
| `active` | `memory/<category>/` | Canonical, current operational truth |
| `superseded` | `memory/<category>/` | Replaced; retained for history |

## Candidate

Create with `kb remember`. Always lands in `inbox/` with `status: candidate`.

- Explicit user statements may become candidates immediately.
- Inferred or ambiguous memories stay in inbox until confirmed.
- `remember` never writes directly to canonical directories.

## Validate

`kb doctor` checks:

- Required YAML frontmatter and allowed enum values
- ISO dates, slug IDs, list syntax
- Duplicate IDs, supersession references, cycles
- Active records with impossible supersession links
- Secret/transcript pattern guardrails
- `INDEX.md` freshness

## Promote

`kb promote inbox/<file>.md [--category <dir>]`

1. **Path safety:** accepts only a direct `inbox/*.md` file inside this repo (no `..`, no paths outside `inbox/`, no symlinks). Bare filenames (`inbox/foo.md` or `foo.md`) are allowed when they resolve to a direct inbox child.
2. `--category` must match the record metadata `type` mapping; the CLI never rewrites `type`.
3. Validates the candidate against schema invariants.
2. Atomically moves to `memory/<category>/<id>.md` (filename stem must equal `id`).
3. Sets `status: active`, updates `updated` date.
4. Regenerates `INDEX.md` under the repo-wide `.lock/kb.lock`.
5. Refuses overwrite if canonical file exists; rolls back all record/index changes on validation failure.

## Supersede

`kb supersede OLD_ID NEW_ID`

1. Sets `OLD_ID` to `status: superseded`.
2. Appends `OLD_ID` to `NEW_ID` `supersedes` list.
3. Validates no cycles or broken links; rolls back on failure.
4. Regenerates `INDEX.md`.

**Never silently rewrite canonical records.** Correct errors or policy changes by superseding.

## Session discipline

1. Read `INDEX.md` only at session start.
2. `kb search` for task-relevant records.
3. Do not load the entire KB reflexively.

## Review

Every record has `review_after` (ISO date). Stale policies should be reconfirmed or superseded.

## Pre-commit handoff

```bash
./tools/kb index && ./tools/kb doctor
```

Both must pass before committing changes to this repo.
