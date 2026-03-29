# Production Setup From Scratch (Windows / macOS / Linux)

This guide gets Catastrophe Analyzer running as a 24/7 local Docker service.

It is OS-specific where needed, but the runtime behavior is the same across all platforms.

## 1) Choose install mode

- `Mode A (repo-based)`: full repository on host.
- `Mode B (runtime-only)`: no full repository, only runtime folder + image.

Use Mode B for lightweight production hosts.

## 2) Prerequisites

Install the following:

- Docker (Docker Desktop on Windows/macOS, Docker Engine + Compose plugin on Linux)
- Git (Mode A only)

Verify:

```bash
docker --version
docker compose version
git --version
```

## 3A) Mode A - Clone repository

```bash
git clone https://github.com/barnabys-drew/catastrophe-analyzer.git
cd catastrophe-analyzer
```

## 4A) Mode A - Configure alerts and strategy

Edit:

- `config/settings.json`
- `config/alerts_config.json`
- optionally `docs/ENTITY_VALIDATION_RUBRIC.md` (shared markdown rubric for agent validation)

At minimum for phone push via ntfy:

```json
"ntfy": {
  "enabled": true,
  "server": "https://ntfy.sh",
  "topic": "your-secret-topic",
  "token": "",
  "priority": "high"
}
```

For agent validation portability (different providers/models), either set in
`config/settings.json` under `entity_extraction.agent_validation` or as container env vars:

- `CATASTROPHE_ENTITY_VALIDATION_MODE` (`agent` or `strict_rules`)
- `CATASTROPHE_ENTITY_AGENT_ENDPOINT`
- `CATASTROPHE_ENTITY_AGENT_API_KEY`
- `CATASTROPHE_ENTITY_AGENT_PROVIDER`
- `CATASTROPHE_ENTITY_AGENT_MODEL`
- `CATASTROPHE_ENTITY_VALIDATION_RUBRIC_FILE` (default: `docs/ENTITY_VALIDATION_RUBRIC.md`)

Sample env profiles for major model families (plus local Ollama) are documented in:

- `docs/AGENT_VALIDATION_MODEL_PROFILES.md`

## 5A) Mode A - Start production container

From repo root:

```bash
docker compose up -d --build
```

This uses:

- `docker-compose.yml`
- `restart: unless-stopped`
- persistent mounts for `config/` and `data/`
- heartbeat-based container healthcheck

## 6A) Mode A - Verify health

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker logs --tail 200 catastrophe-analyzer
```

Expected health state: `healthy` after startup cycles complete.

## 3B) Mode B - Runtime-only folder (no repo clone)

Create a runtime folder and place:

- `docker-compose.yml` (from `runtime-only/docker-compose.yml`)
- `.env.runtime.example` (rename to `.env.runtime`)
- `config/settings.json`
- `config/alerts_config.json`
- `docs/ENTITY_VALIDATION_RUBRIC.md`

Image options:

- Pull from a registry (`CATASTROPHE_IMAGE=ghcr.io/<org>/catastrophe-analyzer:latest`)
- Load local tar (`docker load -i catastrophe-analyzer-image.tar`)

Start runtime-only mode:

```bash
docker compose --env-file .env.runtime up -d
```

You can create this runtime package from a dev machine via:

```bash
scripts/export_runtime_bundle.sh
```

## 7) OS-specific notes

### Windows

- Use Docker Desktop + WSL2 backend (recommended).
- Run commands in PowerShell, Windows Terminal, or WSL shell.
- If using PowerShell, same `docker compose ...` commands work.
- Keep project in a local filesystem path with good Docker performance (WSL filesystem recommended).

### macOS

- Use Docker Desktop.
- On Apple Silicon (M1/M2/M3), default image build works without changes.
- Keep Docker Desktop running after login if host is unattended.

### Linux

- Install Docker Engine and Compose plugin.
- Optional: run Docker without sudo by adding your user to the `docker` group.
- Optional: enable Docker on boot:

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

## 8) Operations

Restart service:

```bash
docker compose restart
```

Stop service:

```bash
docker compose stop
```

Rebuild after repo update:

```bash
git pull
docker compose up -d --build
```

Runtime-only update (new image only):

```bash
docker load -i catastrophe-analyzer-image.tar
docker compose --env-file .env.runtime up -d
```

## 9) Backups (recommended)

Back up `config/` and `data/` daily:

```bash
mkdir -p backups
tar -czf "backups/catastrophe-analyzer-$(date +%Y%m%d-%H%M%S).tgz" config data
```

For more operational detail, see:

- `docs/LOCAL_PRODUCTION_RUNBOOK.md`
