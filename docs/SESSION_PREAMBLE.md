# Session preamble (copy into new Cursor chats)

Copy everything in the block below into the **first message** of a new Chat or Composer session. Replace the bracketed line with **your** assigned stream.

```
You are working on Catastrophe Analyzer (multi-category shock → ticker → signals).

Read first (in order):
1. AGENTS.md
2. docs/IMPLEMENTATION_PLAN_MULTI_CATEGORY.md — use ONLY the checklist items for my stream (see below)
3. docs/MULTI_AGENT_WORKSTREAMS.md — branch and file ownership

My assignment:
- Branch: [e.g. workstream/b-db-migration]
- Stream: [A — config+scraper | B — DB+migration | C — pipeline+alerts]
- Checklist items to implement today: [paste subsection bullets or checkbox lines]

Rules:
- Use event_category / event_categories in new code; do not call them "buckets."
- Keep the scripted pipeline as source of truth; no agents-only ingestion.
- Do not commit .venv/, data/* (runtime), or __pycache__/.
- Touch only files owned by this stream unless I explicitly ask to expand scope.
```

## Short version

```
Read AGENTS.md and docs/IMPLEMENTATION_PLAN_MULTI_CATEGORY.md. I am on branch [NAME] (stream [A|B|C] per docs/MULTI_AGENT_WORKSTREAMS.md). Implement: [specific checklist items].
```
