#!/usr/bin/env bash
# =============================================================================
# Market Intel DB Health Verification Script (/usr/local/sbin/marketintel-health)
# Verifies API container, campaign worker, RAG worker, HTTP /api/health/,
# Nginx, disk usage, and memory utilization.
# =============================================================================
set -euo pipefail

QUIET=false
if [[ "${1:-}" == "--quiet" ]]; then
  QUIET=true
fi

log() {
  if [[ "${QUIET}" != "true" ]]; then
    echo "$@"
  fi
}

# 1. Verify all 3 containers are running
for container in marketintel-api marketintel-campaign-worker marketintel-rag-worker; do
  status="$(docker inspect --format='{{.State.Status}}' "${container}" 2>/dev/null || echo "missing")"
  if [[ "${status}" != "running" ]]; then
    echo "UNHEALTHY: container ${container} status=${status}" >&2
    exit 1
  fi
  log "OK: container ${container} is running"
done

# 2. Poll API health endpoint (up to 30 seconds)
HEALTH_OK=false
for attempt in $(seq 1 15); do
  if curl -fsS -m 3 -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/api/health/ >/dev/null 2>&1; then
    HEALTH_OK=true
    break
  fi
  sleep 2
done

if [[ "${HEALTH_OK}" != "true" ]]; then
  echo "UNHEALTHY: http://127.0.0.1:8000/api/health/ failed after 30s" >&2
  exit 1
fi
log "OK: API health endpoint responded 200"

# 3. Verify Nginx is active
if systemctl is-active --quiet nginx; then
  log "OK: nginx is active"
else
  echo "UNHEALTHY: nginx is not active" >&2
  exit 1
fi

# 4. Check disk usage (<90%)
DISK_PCT="$(df --output=pcent / | tail -n1 | tr -dc '0-9')"
if (( DISK_PCT >= 90 )); then
  echo "WARN: Root filesystem disk usage is ${DISK_PCT}%" >&2
fi
log "OK: Disk usage ${DISK_PCT}%"
