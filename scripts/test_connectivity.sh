#!/usr/bin/env bash
# Quick checks for Ollama (LLM), ntfy (phone push), and optional Tiingo.
# Run from repo root: bash scripts/test_connectivity.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Ollama (entity validation LLM) =="
if curl -sS -m 3 -o /dev/null -w "127.0.0.1:11434 -> HTTP %{http_code}\n" http://127.0.0.1:11434/api/tags; then
  :
else
  echo "  Ollama not reachable on localhost:11434. Start Ollama or keep CATASTROPHE_ENTITY_VALIDATION_MODE=strict_rules"
fi

echo ""
echo "== ntfy (alerts channel) =="
NTFY_SERVER=$(python3 -c "import json; c=json.load(open('config/alerts_config.json')); print(c.get('alert_channels',{}).get('ntfy',{}).get('server','https://ntfy.sh').rstrip('/'))" 2>/dev/null || echo "https://ntfy.sh")
NTFY_TOPIC=$(python3 -c "import json; c=json.load(open('config/alerts_config.json')); print(c.get('alert_channels',{}).get('ntfy',{}).get('topic',''))" 2>/dev/null || echo "")
if [[ -z "$NTFY_TOPIC" ]]; then
  echo "  No ntfy.topic in config/alerts_config.json"
else
  echo "  Server: $NTFY_SERVER  Topic: $NTFY_TOPIC"
  MSG="Catastrophe Analyzer connectivity test ($(date -u +%Y-%m-%dT%H:%MZ))"
  if code=$(curl -sS -m 15 -o /tmp/ntfy-test.json -w "%{http_code}" -d "$MSG" "$NTFY_SERVER/$NTFY_TOPIC"); then
    echo "  POST -> HTTP $code"
    if [[ "$code" == "200" ]]; then
      echo "  OK — check your phone (ntfy app subscribed to this topic)."
    else
      cat /tmp/ntfy-test.json 2>/dev/null || true
    fi
  fi
  rm -f /tmp/ntfy-test.json
fi

echo ""
echo "== Tiingo (optional; uses TIINGO_API_TOKEN from environment) =="
if [[ -n "${TIINGO_API_TOKEN:-}" ]]; then
  out=$(curl -sS -m 10 -H "Authorization: Token ${TIINGO_API_TOKEN}" "https://api.tiingo.com/tiingo/meta/AAPL" | head -c 300) || true
  if echo "$out" | grep -q '"ticker"'; then
    echo "  OK — token accepted (sample meta for AAPL)."
  else
    echo "  Response: ${out:0:200}"
  fi
else
  echo "  Skip: export TIINGO_API_TOKEN=... or: TIINGO_API_TOKEN=\$(grep ^TIINGO_API_TOKEN= .env.agent 2>/dev/null | cut -d= -f2-) $0"
fi

echo ""
echo "== Docker → host Ollama (only meaningful from inside the app container) =="
echo "  Run: docker compose --env-file .env.agent run --rm --entrypoint curl catastrophe-analyzer -sS -m 3 -o /dev/null -w '%{http_code}' http://host.docker.internal:11434/api/tags"
echo "  Expect 200 if Ollama runs on the host and Docker provides host.docker.internal."
