# Local Production Runbook (Docker)

Use this when running Catastrophe Analyzer on an always-on local machine.

## Start / update service

From repo root:

```bash
docker compose up -d --build
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
2. Restore desired backup tarball into repo root
3. Start service: `docker compose up -d --build`
4. Verify health and logs

## Local testing mode (no phone dependency)

Set environment in `docker-compose.yml` if desired:

- `CATASTROPHE_LOCAL_ALERT_PREVIEW=1`
- `CATASTROPHE_ALERTS_LOCAL_ONLY=1`

This writes alert previews to `data/alert_previews/` and avoids ntfy HTTP sends.
