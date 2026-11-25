#!/usr/bin/env bash
# =============================================================================
# Market Intel DB Disaster Recovery Restore Script (/usr/local/sbin/marketintel-restore)
# Usage: sudo /usr/local/sbin/marketintel-restore /opt/marketintel/backups/<STAMP>
# Verifies SHA-256 checksums before restoring database and media.
# =============================================================================
set -euo pipefail

BACKUP_DIR="${1:-}"
if [[ -z "${BACKUP_DIR}" || ! -d "${BACKUP_DIR}" ]]; then
  echo "Usage: sudo $0 /opt/marketintel/backups/<TIMESTAMP>" >&2
  exit 1
fi

BASE_DIR="/opt/marketintel"
ENV_FILE="${BASE_DIR}/.env"
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

echo "=== [1/4] Verifying backup SHA-256 integrity ==="
(cd "${BACKUP_DIR}" && sha256sum -c SHA256SUMS)

TMP_RESTORE="$(mktemp -d)"
trap 'rm -rf "${TMP_RESTORE}"' EXIT

if [[ -f "${BACKUP_DIR}/postgres.dump.enc" ]]; then
  if [[ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
    echo "ERROR: BACKUP_ENCRYPTION_PASSPHRASE is required to decrypt postgres.dump.enc" >&2
    exit 1
  fi
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
    -pass env:BACKUP_ENCRYPTION_PASSPHRASE \
    -in "${BACKUP_DIR}/postgres.dump.enc" -out "${TMP_RESTORE}/postgres.dump"
else
  cp "${BACKUP_DIR}/postgres.dump" "${TMP_RESTORE}/postgres.dump"
fi

echo "=== [2/4] Restoring PostgreSQL database into TARGET DATABASE_URL ==="
pg_restore --clean --if-exists --no-owner --no-privileges -d "${DATABASE_URL}" "${TMP_RESTORE}/postgres.dump"

echo "=== [3/4] Restoring persistent media (if present) ==="
if [[ -f "${BACKUP_DIR}/media.tar.gz.enc" ]]; then
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
    -pass env:BACKUP_ENCRYPTION_PASSPHRASE \
    -in "${BACKUP_DIR}/media.tar.gz.enc" -out "${TMP_RESTORE}/media.tar.gz"
  tar -xzf "${TMP_RESTORE}/media.tar.gz" -C "${BASE_DIR}"
elif [[ -f "${BACKUP_DIR}/media.tar.gz" ]]; then
  tar -xzf "${BACKUP_DIR}/media.tar.gz" -C "${BASE_DIR}"
fi
chown -R 10001:10001 "${BASE_DIR}/media"

echo "=== [4/4] Verifying row counts and connectivity ==="
psql "${DATABASE_URL}" -c "SELECT count(*) AS users FROM auth_user; SELECT count(*) AS prospects FROM prospects_prospect;"
echo "Restore complete."
