# Local infrastructure roadmap (homelab)

This note captures the **intended deployment story** for this project and related containers under `~/code` (**catastrophe-analyzer**, **concentration-manager**, **zeromouse-monitor**). The same file (with repo-specific links) lives in each of those repositories. It is **not** a hard requirement to run Catastrophe Analyzer.

## Goals (in order)

1. **Signals and behavior are correct locally** — RSS ingestion, entity validation mode (strict rules vs agent/LLM), and alerts behave as expected before investing in heavier hosting.
2. **Run everything on a dedicated spare PC** — quiet, always-on machine that can host Docker workloads, cron schedules, and logs.
3. **Hardware profile** — NVIDIA **RTX 3060 Ti**, a **capable AMD CPU**, and **plenty of RAM** so the same box can comfortably run:
   - scheduled **one-shot** containers (e.g. `monitor.py --once`) or **long-running** compose stacks,
   - optional **local LLM** workloads (Ollama, vLLM, etc.) when **agent** validation or similar paths need inference *without* locking the design to a specific cloud vendor yet.
4. **Observability later** — if desired, add **Grafana** and/or **ELK/OpenSearch** (or cloud equivalents) for centralized dashboards and log search; whether that stays on the spare PC or moves to **GCP/AWS** is a separate decision and may depend on cost, uptime, and whether a given workflow needs GPU-backed LLMs on-prem.

## Design implication

- **LLM-optional paths** (e.g. strict rule validation) can stay simple: cron + `docker run`, file logs, email/ntfy.
- **LLM-dependent paths** need a clear **inference target** (local GPU vs remote API); that choice drives where compute lives more than the choice of log stack.

## Related files in this repo

- [README.md](../README.md) — install modes, Docker, WSL  
- [claude.md](../claude.md) — quick commands for development  
- Shared hourly cron template (sibling path): `~/code/hourly-checks.crontab.example`

## Homelab handoff over Tailscale (ntfy topics + env)

Use **`tailscale file cp`** from your dev PC to the homelab so you do not need SSH or port 22. Destination is your tailnet node name (example: **`chewbacca-1`**). Tailscale IP for reference: **`100.112.54.107`**.

### Files that carry ntfy topics or alert config

| Repo | What to copy | Notes |
|------|----------------|--------|
| `catastrophe-analyzer` | `.env` (if you use it), `.env.agent` | Compose: `docker compose --env-file .env.agent …`. **ntfy topic** is in `config/alerts_config.json` (`alert_channels.ntfy.topic`). |
| `concentration-manager` | `.env` | `CM_NTFY_TOPIC` (see `.env.example`). |
| `portfolio-analyzer` | `.env` | `PA_NTFY_TOPIC` (see `.env.example`). |
| `zeromouse-monitor` | `.env` | `NTFY_TOPIC` (see README). |

### Example: `tailscale file cp` from this PC (WSL)

Run on the machine that has the source files (adjust paths if your home directory differs):

```bash
tailscale file cp "/home/drewpweiner/code/catastrophe-analyzer/.env" chewbacca-1:
tailscale file cp "/home/drewpweiner/code/catastrophe-analyzer/.env.agent" chewbacca-1:
tailscale file cp "/home/drewpweiner/code/catastrophe-analyzer/config/alerts_config.json" chewbacca-1:

tailscale file cp "/home/drewpweiner/code/concentration-manager/.env" chewbacca-1:
tailscale file cp "/home/drewpweiner/code/portfolio-analyzer/.env" chewbacca-1:
tailscale file cp "/home/drewpweiner/code/zeromouse-monitor/.env" chewbacca-1:
```

On **chewbacca-1**, move each received file from the Tailscale **file inbox** into the matching path under `~/code/...` (same layout as this PC). If you do not use a given file (e.g. no `.env` for catastrophe-analyzer), skip that line.

Confirm the **ntfy** app is still subscribed to the **same topic names** as in those files.

### After files are in place

On **chewbacca-1**, from each repo: `docker compose --env-file … up -d` as usual. Catastrophe Analyzer: `docker compose --env-file .env.agent up -d` from `~/code/catastrophe-analyzer`.

Update this file when the homelab hostname, IP, or “single compose stack” layout stabilizes.
