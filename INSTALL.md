# Install Guide

This project supports two install modes.

## Mode A: Repo + CLI/Dev (full checkout)

Use this when you want to develop, tune rules, run tests, and use the interactive CLI.

```bash
git clone https://github.com/barnabys-drew/catastrophe-analyzer.git
cd catastrophe-analyzer
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Run interactive CLI:

```bash
cd src
python3 main.py
```

Run one service cycle:

```bash
cd src
python3 monitor.py --once --quiet
```

Run Docker from repo:

```bash
docker compose up -d --build
```

---

## Mode B: Runtime-Only Docker (no full repo on host)

Use this for always-on hosts where you only want to run the service.

### 1) Build runtime bundle (from a dev machine)

```bash
scripts/export_runtime_bundle.sh
```

This creates `dist/runtime-bundle-<timestamp>/` with:

- `catastrophe-analyzer-image.tar`
- `docker-compose.yml`
- `.env.runtime.example`
- `config/settings.json`
- `config/alerts_config.json`
- `docs/ENTITY_VALIDATION_RUBRIC.md`
- `README.md`

### 2) Move bundle to target host and start

```bash
docker load -i catastrophe-analyzer-image.tar
cp .env.runtime.example .env.runtime
docker compose --env-file .env.runtime up -d
```

### 3) Verify

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker logs --tail 200 catastrophe-analyzer
```

---

## Where to read next

- `QUICKSTART.md` (both paths in one place)
- `runtime-only/README.md` (runtime-only details)
- `docs/LOCAL_PRODUCTION_RUNBOOK.md` (operations, backup/recovery)
- `docs/PRODUCTION_SETUP_WINDOWS_MAC_LINUX.md` (cross-platform setup)
