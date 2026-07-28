# Derived Knowledge Graph

Future **Graphify** / knowledge-graph views of Kestrel memory are **rebuildable derivatives**, never the source of truth.

## First principle

Canonical truth lives in versioned Markdown records under `memory/` with strict YAML frontmatter (`schemas/memory.schema.json`). Any graph, embedding index, or LangGraph state is disposable and must be reconstructible from those files.

## Roadmap (decision)

1. **Now:** deterministic Markdown + `kb search` (linear scan, no indexing service).
2. **Later:** Graphify or similar — build nodes/edges from `id`, `type`, `tags`, `supersedes` links.
3. **Only when justified:** LangGraph or agentic workflows after operational needs exceed search + promote/supersede.

## Graph semantics (future)

| edge | from | to | source field |
| --- | --- | --- | --- |
| supersedes | new record | old record | `supersedes` |
| tagged | record | tag | `tags` |
| typed | record | type | `type` |

Rebuild procedure:

1. Parse all canonical `memory/**/*.md` files.
2. Emit nodes (one per record) and edges (supersedes, tags).
3. Drop and rebuild the graph store; never edit canonical files from the graph.

## What not to do

- Store secrets or transcript text in graph properties.
- Treat graph mutations as authoritative over Markdown.
- Add LangGraph complexity before workflow pain is demonstrated.

See memory record `roadmap-markdown-first` for the governing decision.
