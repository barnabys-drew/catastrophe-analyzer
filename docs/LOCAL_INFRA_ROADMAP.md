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

Update this file when the homelab hostname, IP, or “single compose stack” layout stabilizes.
