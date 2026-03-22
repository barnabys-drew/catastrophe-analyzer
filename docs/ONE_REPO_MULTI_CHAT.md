# One repo, multiple Cursor chats (playbook)

Use **one clone** of this repository. To avoid mixed edits (Stream B + Stream A in the same `git status`), treat **coding as serial**: only **one** chat applies patches at a time. Other chats can stay open for **reading / planning**.

## Before each coding session

```bash
cd ~/code/catastrophe-analyzer   # your path
git fetch origin
git checkout workstream/<branch-for-this-chat>
git merge origin/main
```

| Stream | Branch |
|--------|--------|
| B — DB + migration | `workstream/b-db-migration` |
| A — config + scraper | `workstream/a-config-scraper` |
| C — pipeline + analyzers | `workstream/c-pipeline-rename` |

## When you finish that stream

```bash
git status
git add <only files that stream owns — see MULTI_AGENT_WORKSTREAMS.md>
git commit -m "feat: … (Stream X)"
git push -u origin HEAD
```

Then merge to `main` (pull request or local merge) in the order in [MULTI_AGENT_WORKSTREAMS.md](MULTI_AGENT_WORKSTREAMS.md).

## When you need to stop (pause)

**Save on the branch (best):**

```bash
git add -A
git commit -m "wip: stream X partial"
git push -u origin HEAD
```

**Not ready to commit:**

```bash
git stash push -m "wip stream X"
```

Switch branches only when the tree is **clean** or you’ve stashed.

## If two streams already mixed files in one folder

Stash **only** the files that belong to the **other** stream, then commit the rest on the correct branch. Example: stash `config/settings.json` and `src/news_scraper.py` (Stream A), then commit `src/database_manager.py` on `workstream/b-db-migration`, then check out A’s branch and `git stash pop`.

## Golden rule

**Do not let two chats apply code changes in the same folder at the same time.** Rotate: finish B → commit/push → then A → commit/push → then C.

## Related

- [MULTI_AGENT_WORKSTREAMS.md](MULTI_AGENT_WORKSTREAMS.md) — branch names, merge order, file ownership  
- [SESSION_PREAMBLE.md](SESSION_PREAMBLE.md) — first message template for a new chat  
- [AGENTS.md](../AGENTS.md) — project conventions  
