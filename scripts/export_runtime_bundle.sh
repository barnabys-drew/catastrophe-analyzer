#!/usr/bin/env bash
set -euo pipefail

# Build a runtime-only deployment bundle so target machines do not need the full repo.
# Usage:
#   scripts/export_runtime_bundle.sh
#   scripts/export_runtime_bundle.sh catastrophe-analyzer:latest

IMAGE_TAG="${1:-catastrophe-analyzer:latest}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BUNDLE_DIR="${ROOT_DIR}/dist/runtime-bundle-${STAMP}"

echo "[1/5] Building image: ${IMAGE_TAG}"
docker build -t "${IMAGE_TAG}" "${ROOT_DIR}"

echo "[2/5] Creating bundle directory: ${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}/config" "${BUNDLE_DIR}/data" "${BUNDLE_DIR}/docs"

echo "[3/5] Exporting image tar"
docker save -o "${BUNDLE_DIR}/catastrophe-analyzer-image.tar" "${IMAGE_TAG}"

echo "[4/5] Copying runtime files"
cp "${ROOT_DIR}/runtime-only/docker-compose.yml" "${BUNDLE_DIR}/docker-compose.yml"
cp "${ROOT_DIR}/runtime-only/.env.runtime.example" "${BUNDLE_DIR}/.env.runtime.example"
cp "${ROOT_DIR}/runtime-only/README.md" "${BUNDLE_DIR}/README.md"
cp "${ROOT_DIR}/config/settings.json" "${BUNDLE_DIR}/config/settings.json"
cp "${ROOT_DIR}/config/alerts_config.json" "${BUNDLE_DIR}/config/alerts_config.json"
cp "${ROOT_DIR}/docs/ENTITY_VALIDATION_RUBRIC.md" "${BUNDLE_DIR}/docs/ENTITY_VALIDATION_RUBRIC.md"

echo "[5/5] Done"
echo "Runtime bundle created:"
echo "  ${BUNDLE_DIR}"
echo ""
echo "Next on target machine:"
echo "  1) docker load -i catastrophe-analyzer-image.tar"
echo "  2) cp .env.runtime.example .env.runtime"
echo "  3) docker compose --env-file .env.runtime up -d"
