# Quickstart

## 1) Setup

```bash
cd catastrophe-analyzer
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## 2) Configure

- Edit `config/settings.json` for categories, sources, and thresholds.
- Edit `config/alerts_config.json` for ntfy/email/Twilio alerts.

For ntfy, set:

```json
"ntfy": {
  "enabled": true,
  "server": "https://ntfy.sh",
  "topic": "your-secret-topic",
  "token": "",
  "priority": "high"
}
```

## 3) Test with CLI (manual)

```bash
cd src
python3 main.py
```

Use this path to inspect scan/analyze/signal steps interactively.

## 4) Test service path once

```bash
cd src
python3 monitor.py --once --quiet
```

## 5) Run as live Docker service

From repo root:

```bash
docker build -t catastrophe-analyzer .
docker run -d --name catastrophe-analyzer \
  --restart unless-stopped \
  -v "$(pwd)/config:/app/config" \
  -v "$(pwd)/data:/app/data" \
  catastrophe-analyzer --quiet
```

## 6) Observe logs

```bash
docker logs -f catastrophe-analyzer
```

## 7) Stop service

```bash
docker stop catastrophe-analyzer
```

## Notes

- Production path is `monitor.py` (Docker), not the interactive menu.
- Current category depth is strongest for `cybersecurity` and `clinical_regulatory_binary`.
- Future category expansion targets are in `docs/EVENT_CATEGORIES_AND_IMPACT.md`.
