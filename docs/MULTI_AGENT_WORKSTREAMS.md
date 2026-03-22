# Multi-agent workstreams (Cursor)

Use **separate Chat or Composer sessions** as parallel “agents.” Each stream owns **non-overlapping files** to reduce merge conflicts. This doc is the **single source of truth** for stream boundaries and **git branch names**.

## Branch names and merge order

Create each branch from `main` (or rebase onto latest `main` before starting):

| Order | Branch | Stream |
|-------|--------|--------|
| 1 (merge first) | `workstream/b-db-migration` | B — Database + CSV migration |
| 2 | `workstream/a-config-scraper` | A — Config + news scraper |
| 3 | `workstream/c-pipeline-rename` | C — Main pipeline + analyzers + alerts |

**Why this order:** Stream **B** introduces neutral CSV files/columns and `DatabaseManager` APIs. Stream **A** adds `event_categories` in config and scraper tags (can land after or in parallel with B if you avoid touching `database_manager.py` in A). Stream **C** renames call sites and threads `event_category` through `main`, `stock_analyzer`, `signal_generator`, `alert_manager`—it should follow **B** (and ideally **A**) so types and column names exist.

If **A** and **B** both touch only their own files, they can merge in either order; **C** must align with whatever `DatabaseManager` and config export after A+B merge.

## Stream definitions

### Stream A — Config + scraper

| | |
|--|--|
| **Git branch** | `workstream/a-config-scraper` |
| **Owns** | [config/settings.json](../config/settings.json), [src/news_scraper.py](../src/news_scraper.py) |
| **Checklist** (from [IMPLEMENTATION_PLAN_MULTI_CATEGORY.md](IMPLEMENTATION_PLAN_MULTI_CATEGORY.md)) | `event_categories` stubs; move cyber keywords from Python to JSON; `event_category` per `news_sources` entry; `event_watch` (+ legacy `breach_watch` fallback); scraper loads keywords and tags articles |

**Do not** change `database_manager.py` or `main.py` in this stream unless unavoidable—hand off to B/C.

### Stream B — Database + migration

| | |
|--|--|
| **Git branch** | `workstream/b-db-migration` |
| **Owns** | [src/database_manager.py](../src/database_manager.py), runtime paths under `data/` (via code + `.gitignore`) |
| **Checklist** | New CSV names and columns; one-time migration from `breach*.csv`; `add_event` / `get_events`; watchlist key `(ticker, event_date, event_category)` |

**Do not** change `news_scraper.py` or large rewrites of `main.py` here—only DB API and files the DB touches.

### Stream C — Pipeline rename + orchestration

| | |
|--|--|
| **Git branch** | `workstream/c-pipeline-rename` |
| **Owns** | [src/main.py](../src/main.py), [src/stock_analyzer.py](../src/stock_analyzer.py), [src/signal_generator.py](../src/signal_generator.py), [src/alert_manager.py](../src/alert_manager.py), [src/entity_extractor.py](../src/entity_extractor.py) (optional `event_category` param) |
| **Checklist** | Thread `event_category`; `event_date` / `analyze_event_impact`; signal dict keys; CLI strings; alerts include category |

Depends on **B** (and **A** for config shape) being merged or rebased in.

## Creating branches (one-time)

```bash
git checkout main
git pull origin main   # if you use a remote
git checkout -b workstream/b-db-migration
git push -u origin workstream/b-db-migration
git checkout main
git checkout -b workstream/a-config-scraper
git push -u origin workstream/a-config-scraper
git checkout main
git checkout -b workstream/c-pipeline-rename
git push -u origin workstream/c-pipeline-rename
```

Work in **one branch per session**; merge to `main` in the order above when each stream is done.

## Coordination

- Use the **checkboxes** in [IMPLEMENTATION_PLAN_MULTI_CATEGORY.md](IMPLEMENTATION_PLAN_MULTI_CATEGORY.md) to avoid duplicate work.
- After a stream merges, other sessions: `git checkout <branch> && git merge main` (or rebase).
- Paste [SESSION_PREAMBLE.md](SESSION_PREAMBLE.md) at the start of each new Cursor chat.

## Related

- [AGENTS.md](../AGENTS.md) — read order and conventions  
- [SESSION_PREAMBLE.md](SESSION_PREAMBLE.md) — copy-paste opening prompt  
