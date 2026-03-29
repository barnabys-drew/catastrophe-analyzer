# Production Setup From Scratch (Windows / macOS / Linux)

This guide gets Catastrophe Analyzer running as a 24/7 local Docker service.

It is OS-specific where needed, but the runtime behavior is the same across all platforms.

## 1) Prerequisites

Install the following:

- Git
- Docker (Docker Desktop on Windows/macOS, Docker Engine + Compose plugin on Linux)

Verify:

```bash
docker --version
docker compose version
git --version
```

## 2) Clone repository

```bash
git clone https://github.com/barnabys-drew/catastrophe-analyzer.git
cd catastrophe-analyzer
```

## 3) Configure alerts and strategy

Edit:

- `config/settings.json`
- `config/alerts_config.json`

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

## 4) Start production container

From repo root:

```bash
docker compose up -d --build
```

This uses:

- `docker-compose.yml`
- `restart: unless-stopped`
- persistent mounts for `config/` and `data/`
- heartbeat-based container healthcheck

## 5) Verify health

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker logs --tail 200 catastrophe-analyzer
```

Expected health state: `healthy` after startup cycles complete.

## 6) OS-specific notes

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

## 7) Operations

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

## 8) Backups (recommended)

Back up `config/` and `data/` daily:

```bash
mkdir -p backups
tar -czf "backups/catastrophe-analyzer-$(date +%Y%m%d-%H%M%S).tgz" config data
```

For more operational detail, see:

- `docs/LOCAL_PRODUCTION_RUNBOOK.md`
