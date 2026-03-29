# Local Production Runbook (Docker)

Use this when running Catastrophe Analyzer on an always-on local machine.

## Deployment choice

- `Repo-based deploy`: run from the full repository checkout.
- `Runtime-only deploy`: run from a lightweight folder with only compose/config/data/docs and an image.

Runtime-only instructions: `runtime-only/README.md`.

## Start / update service

From repo root (repo-based deploy):

```bash
docker compose up -d --build
```

From runtime-only folder:

```bash
docker compose --env-file .env.runtime up -d
```

## Verify runtime health

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker logs --tail 200 catastrophe-analyzer
```

Health status is based on `data/runtime_heartbeat.json`, written each cycle.

## Stop / restart

```bash
docker compose stop
docker compose restart
```

## Backup strategy (daily)

Back up `config/` and `data/` together so settings and state stay in sync.

Example manual backup:

```bash
mkdir -p backups
tar -czf "backups/catastrophe-analyzer-$(date +%Y%m%d-%H%M%S).tgz" config data
```

Recommended retention:

- Keep last 14 daily backups
- Keep last 8 weekly backups

## Recovery

1. Stop service: `docker compose stop`
2. Restore desired backup tarball into the active runtime folder
3. Start service:
   - repo-based: `docker compose up -d --build`
   - runtime-only: `docker compose --env-file .env.runtime up -d`
4. Verify health and logs

## Local testing mode (no phone dependency)

Set environment in `docker-compose.yml` if desired:

- `CATASTROPHE_LOCAL_ALERT_PREVIEW=1`
- `CATASTROPHE_ALERTS_LOCAL_ONLY=1`

This writes alert previews to `data/alert_previews/` and avoids ntfy HTTP sends.

## Agent validation in Docker (portable across machines/models)

Use environment overrides in `docker-compose.yml` for model/provider portability:

- `CATASTROPHE_ENTITY_VALIDATION_MODE=agent` or `strict_rules`
- `CATASTROPHE_ENTITY_AGENT_ENDPOINT=...`
- `CATASTROPHE_ENTITY_AGENT_API_KEY=...`
- `CATASTROPHE_ENTITY_AGENT_PROVIDER=...` (for example `openai_compatible`)
- `CATASTROPHE_ENTITY_AGENT_MODEL=...` (model id for your endpoint)
- `CATASTROPHE_ENTITY_VALIDATION_RUBRIC_FILE=docs/ENTITY_VALIDATION_RUBRIC.md`

The same rubric markdown file is shipped in the image at `docs/ENTITY_VALIDATION_RUBRIC.md`,
so validation behavior stays consistent on new machines.

Use ready-made model profiles (cloud + Ollama local):

- `docs/AGENT_VALIDATION_MODEL_PROFILES.md`
