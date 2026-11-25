git commit -m "Add local PostgreSQL 16 pgvector service to Hostinger stack"#!/usr/bin/env bash
# =============================================================================
# Root-owned Market Intel DB Deployment Helper (/usr/local/sbin/marketintel-deploy)
# Usage: sudo /usr/local/sbin/marketintel-deploy <commit_sha>
# Reads release artifacts from /opt/marketintel/incoming/<commit_sha>/
# Never runs docker volume prune; preserves previous releases for rollback.
# =============================================================================
set -euo pipefail

RELEASE_SHA="${1:-}"
if [[ ! "${RELEASE_SHA}" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
  echo "ERROR: Valid commit SHA required as argument 1." >&2
  exit 1
fi

BASE_DIR="/opt/marketintel"
INCOMING_DIR="${BASE_DIR}/incoming/${RELEASE_SHA}"
RELEASE_DIR="${BASE_DIR}/releases/${RELEASE_SHA}"
FRONTEND_RELEASES="${BASE_DIR}/frontend/releases"
FRONTEND_CURRENT="${BASE_DIR}/frontend/current"
COMPOSE_FILE="${BASE_DIR}/deploy/docker-compose.production.yml"
ENV_FILE="${BASE_DIR}/.env"
IMAGE_NAME="marketintel-backend:${RELEASE_SHA}"

echo "=== [1/8] Pre-deployment validation for release ${RELEASE_SHA} ==="
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} is missing." >&2
  exit 1
fi
chmod 600 "${ENV_FILE}"

# Require at least 5 GB free disk space on /
AVAIL_KB="$(df --output=avail / | tail -n1 | tr -d ' ')"
if (( AVAIL_KB < 5 * 1024 * 1024 )); then
  echo "ERROR: Less than 5 GB free disk space available on / (${AVAIL_KB} KB)." >&2
  exit 1
fi

if [[ ! -f "${INCOMING_DIR}/backend-image.tar.gz" || ! -f "${INCOMING_DIR}/frontend-dist.tar.gz" ]]; then
  echo "ERROR: Expected backend-image.tar.gz and frontend-dist.tar.gz in ${INCOMING_DIR}." >&2
  exit 1
fi

# Record current release for automatic rollback
PREV_SHA=""
if [[ -f "${BASE_DIR}/CURRENT_RELEASE" ]]; then
  PREV_SHA="$(cat "${BASE_DIR}/CURRENT_RELEASE" | tr -d '[:space:]')"
fi

echo "=== [2/8] Staging release artifacts ==="
mkdir -p "${RELEASE_DIR}" "${FRONTEND_RELEASES}/${RELEASE_SHA}"
cp "${INCOMING_DIR}/backend-image.tar.gz" "${RELEASE_DIR}/"
cp "${INCOMING_DIR}/frontend-dist.tar.gz" "${RELEASE_DIR}/"
if [[ -f "${INCOMING_DIR}/docker-compose.production.yml" ]]; then
  install -m 0644 -o root -g root "${INCOMING_DIR}/docker-compose.production.yml" "${COMPOSE_FILE}"
fi

echo "=== [3/8] Loading immutable backend Docker image (${IMAGE_NAME}) ==="
gunzip -c "${RELEASE_DIR}/backend-image.tar.gz" | docker load

echo "=== [4/8] Ensuring PostgreSQL (pgvector) is healthy & optional pre-migration backup ==="
export API_IMAGE="${IMAGE_NAME}"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --wait db

if [[ "${BACKUP_BEFORE_DEPLOY:-true}" == "true" && -x /usr/local/sbin/marketintel-backup ]]; then
  /usr/local/sbin/marketintel-backup || echo "WARN: Pre-deploy backup exited non-zero; continuing with caution."
fi

echo "=== [5/8] Running Django deploy checks, migrations, and collectstatic ==="
chown -R 10001:10001 "${BASE_DIR}/staticfiles" "${BASE_DIR}/media"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm --no-deps api python manage.py check --deploy
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm --no-deps api python manage.py migrate --noinput
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm --no-deps api python manage.py collectstatic --noinput

echo "=== [6/8] Deploying static frontend build ==="
tar -xzf "${RELEASE_DIR}/frontend-dist.tar.gz" -C "${FRONTEND_RELEASES}/${RELEASE_SHA}"
ln -sfn "${FRONTEND_RELEASES}/${RELEASE_SHA}" "${FRONTEND_CURRENT}"

echo "=== [7/8] Starting DB, API, Campaign Worker, and RAG Worker via Docker Compose ==="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans

echo "=== [8/8] Verifying service health ==="
if ! /usr/local/sbin/marketintel-health; then
  echo "ERROR: Health check failed for ${RELEASE_SHA}. Triggering rollback..." >&2
  if [[ -n "${PREV_SHA}" && "${PREV_SHA}" != "${RELEASE_SHA}" ]]; then
    /usr/local/sbin/marketintel-rollback || true
  fi
  exit 1
fi

if [[ -n "${PREV_SHA}" && "${PREV_SHA}" != "${RELEASE_SHA}" ]]; then
  echo "${PREV_SHA}" > "${BASE_DIR}/PREVIOUS_RELEASE"
fi
echo "${RELEASE_SHA}" > "${BASE_DIR}/CURRENT_RELEASE"

# Cleanup incoming tarball staging and retain last 3 releases safely (NEVER prune volumes)
rm -rf "${INCOMING_DIR}"
ls -1dt "${FRONTEND_RELEASES}"/* 2>/dev/null | tail -n +4 | xargs -r rm -rf
ls -1dt "${BASE_DIR}/releases"/* 2>/dev/null | tail -n +4 | xargs -r rm -rf

echo "Deployment of ${RELEASE_SHA} succeeded and passed health verification."
