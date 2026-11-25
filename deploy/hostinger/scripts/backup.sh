#!/usr/bin/env bash
# =============================================================================
# Market Intel DB Automated Encrypted Backup Script (/usr/local/sbin/marketintel-backup)
# Backs up PostgreSQL (custom format) + persistent media with SHA-256 checksums.
# Optional offsite upload to S3/R2 when BACKUP_S3_BUCKET is set.
# =============================================================================
set -euo pipefail

BASE_DIR="/opt/marketintel"
ENV_FILE="${BASE_DIR}/.env"
BACKUP_ROOT="${BASE_DIR}/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_DIR="${BACKUP_ROOT}/${STAMP}"

mkdir -p "${WORK_DIR}"
chmod 700 "${WORK_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found." >&2
  exit 1
fi

# Safely load DATABASE_URL and optional BACKUP_ENCRYPTION_PASSPHRASE without printing them
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set in ${ENV_FILE}." >&2
  exit 1
fi

echo "[${STAMP}] Starting PostgreSQL backup..."
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'marketintel-db'; then
  docker exec marketintel-db pg_dump -U "${POSTGRES_USER:-marketintel}" -d "${POSTGRES_DB:-marketintel}" \
    --format=custom --no-owner --no-privileges > "${WORK_DIR}/postgres.dump"
else
  HOST_DATABASE_URL="${DATABASE_URL/@db:/@127.0.0.1:}"
  pg_dump --format=custom --no-owner --no-privileges "${HOST_DATABASE_URL}" -f "${WORK_DIR}/postgres.dump"
fi

echo "[${STAMP}] Archiving persistent media..."
if [[ -d "${BASE_DIR}/media" ]]; then
  tar -czf "${WORK_DIR}/media.tar.gz" -C "${BASE_DIR}" media
fi

# Encrypt backup files if BACKUP_ENCRYPTION_PASSPHRASE is configured
if [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
  echo "[${STAMP}] Encrypting backup artifacts with AES-256-CBC + PBKDF2..."
  for f in "${WORK_DIR}"/postgres.dump "${WORK_DIR}"/media.tar.gz; do
    if [[ -f "${f}" ]]; then
      openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
        -pass env:BACKUP_ENCRYPTION_PASSPHRASE \
        -in "${f}" -out "${f}.enc"
      rm -f "${f}"
    fi
  done
fi

(cd "${WORK_DIR}" && sha256sum * > SHA256SUMS)
chmod -R 600 "${WORK_DIR}"/*

# Optional offsite S3/R2 upload
if [[ -n "${BACKUP_S3_BUCKET:-}" ]] && command -v aws >/dev/null 2>&1; then
  echo "[${STAMP}] Uploading encrypted backup to offsite bucket..."
  ENDPOINT_ARGS=()
  if [[ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]]; then
    ENDPOINT_ARGS=(--endpoint-url "${BACKUP_S3_ENDPOINT_URL}")
  fi
  aws s3 sync "${WORK_DIR}" "s3://${BACKUP_S3_BUCKET}/marketintel-backups/${STAMP}/" "${ENDPOINT_ARGS[@]}" --only-show-errors
fi

# Enforce local retention policy
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} +

echo "[${STAMP}] Backup completed successfully in ${WORK_DIR}."
