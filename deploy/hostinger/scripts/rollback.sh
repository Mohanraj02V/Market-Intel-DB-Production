#!/usr/bin/env bash
# =============================================================================
# Market Intel DB Rollback Script (/usr/local/sbin/marketintel-rollback)
# Restores the previous verified Docker image and frontend release without
# modifying or deleting database rows, media, RAG documents, or volumes.
# =============================================================================
set -euo pipefail

BASE_DIR="/opt/marketintel"
COMPOSE_FILE="${BASE_DIR}/deploy/docker-compose.production.yml"
FRONTEND_RELEASES="${BASE_DIR}/frontend/releases"
FRONTEND_CURRENT="${BASE_DIR}/frontend/current"

TARGET_SHA="${1:-}"
if [[ -z "${TARGET_SHA}" ]]; then
  if [[ ! -f "${BASE_DIR}/PREVIOUS_RELEASE" ]]; then
    echo "ERROR: No PREVIOUS_RELEASE recorded. Pass a release SHA explicitly." >&2
    exit 1
  fi
  TARGET_SHA="$(cat "${BASE_DIR}/PREVIOUS_RELEASE" | tr -d '[:space:]')"
fi

if [[ ! "${TARGET_SHA}" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
  echo "ERROR: Invalid target release SHA: ${TARGET_SHA}" >&2
  exit 1
fi

IMAGE_NAME="marketintel-backend:${TARGET_SHA}"

echo "=== Rolling back Market Intel DB to release ${TARGET_SHA} ==="
if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  if [[ -f "${BASE_DIR}/releases/${TARGET_SHA}/backend-image.tar.gz" ]]; then
    gunzip -c "${BASE_DIR}/releases/${TARGET_SHA}/backend-image.tar.gz" | docker load
  else
    echo "ERROR: Image ${IMAGE_NAME} not found locally and no archive available." >&2
    exit 1
  fi
fi

if [[ -d "${FRONTEND_RELEASES}/${TARGET_SHA}" ]]; then
  ln -sfn "${FRONTEND_RELEASES}/${TARGET_SHA}" "${FRONTEND_CURRENT}"
fi

export API_IMAGE="${IMAGE_NAME}"
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

/usr/local/sbin/marketintel-health
echo "${TARGET_SHA}" > "${BASE_DIR}/CURRENT_RELEASE"
echo "Rollback to ${TARGET_SHA} completed and verified (database and media untouched)."
