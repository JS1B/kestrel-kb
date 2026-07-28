---
confidence: high
created: 2026-07-28
id: roadmap-markdown-first
review_after: 2027-01-28
sensitivity: internal
source: user-confirmed 2026-07-28; kestrel-kb initial design
status: active
supersedes: []
tags:
  - roadmap
  - graphify
  - langgraph
type: decision
updated: 2026-07-28
---
# Roadmap: Markdown and search first

**Decision:**

1. **Now:** Canonical Markdown records + deterministic `kb search` (no indexing service).
2. **Later:** Graphify or knowledge graph as a **rebuildable derivative** — never source of truth.
3. **Only when justified:** LangGraph after operational workflow needs exceed promote/supersede + search.

See `docs/DERIVED-GRAPH.md`.
