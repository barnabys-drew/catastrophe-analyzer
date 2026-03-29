# Quickstart

Choose one path:

- **Path A: Repo + CLI/Dev mode** (full repo)
- **Path B: Runtime-only Docker mode** (no full repo on target host)

---

## Path A - Repo + CLI/Dev mode

### 1) Setup

```bash
cd catastrophe-analyzer
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 2) Configure

- Edit `config/settings.json` for categories, thresholds, and validation mode.
- Edit `config/alerts_config.json` for ntfy/email/Twilio alerts.

### 3) Test CLI (interactive)

```bash
cd src
python3 main.py
```

### 4) Test service path once

```bash
cd src
python3 monitor.py --once --quiet
```

### 5) Run Docker from repo

```bash
docker compose up -d --build
docker logs -f catastrophe-analyzer
```

Stop:

```bash
docker compose stop
```

---

## Path B - Runtime-only Docker mode (no repo clone)

Use this on production hosts that should only run the service.

### 1) Prepare runtime folder

Copy the contents from `runtime-only/` to your host folder, then add:

- `config/settings.json`
- `config/alerts_config.json`
- `docs/ENTITY_VALIDATION_RUBRIC.md`

Or generate a ready bundle from a dev machine:

```bash
scripts/export_runtime_bundle.sh
```

### 2) Configure env file

```bash
cp .env.runtime.example .env.runtime
```

Set image:

- local loaded image: `CATASTROPHE_IMAGE=catastrophe-analyzer:latest`
- registry image: `CATASTROPHE_IMAGE=ghcr.io/<org>/catastrophe-analyzer:latest`

### 3) Start service

```bash
docker compose --env-file .env.runtime up -d
```

### 4) Verify

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker logs --tail 200 catastrophe-analyzer
```

---

## Additional docs

- `docs/LOCAL_PRODUCTION_RUNBOOK.md`
- `docs/PRODUCTION_SETUP_WINDOWS_MAC_LINUX.md`
- `runtime-only/README.md`
