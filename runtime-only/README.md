# Runtime-Only Docker Install (No Full Repo)

Use this mode on machines that only need to run the service 24/7.

You need:

- Docker + Compose
- This `runtime-only/` folder
- A container image (`catastrophe-analyzer:latest`), loaded locally or pulled from a registry

## Folder layout on target machine

```text
catastrophe-runtime/
  docker-compose.yml
  .env.runtime
  config/
    settings.json
    alerts_config.json
  data/
  docs/
    ENTITY_VALIDATION_RUBRIC.md
```

## Option A: Use prebuilt registry image

Set image in `.env.runtime`:

```env
CATASTROPHE_IMAGE=ghcr.io/<org>/catastrophe-analyzer:latest
```

Then run:

```bash
docker compose --env-file .env.runtime up -d
```

## Option B: Load exported image tar (air-gapped / offline-friendly)

```bash
docker load -i catastrophe-analyzer-image.tar
docker images | rg catastrophe-analyzer
docker compose --env-file .env.runtime up -d
```

## Verify service

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker logs --tail 200 catastrophe-analyzer
```

## Stop / restart

```bash
docker compose stop
docker compose restart
```

## Notes

- The service path is `monitor.py` inside the container.
- You can switch strict-rule vs agent mode in `.env.runtime` via `CATASTROPHE_ENTITY_VALIDATION_MODE`.
- Keep `config/`, `data/`, and `docs/ENTITY_VALIDATION_RUBRIC.md` backed up together.
