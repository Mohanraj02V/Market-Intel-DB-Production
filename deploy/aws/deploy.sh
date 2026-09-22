#!/usr/bin/env bash
# =============================================================================
# deploy/aws/deploy.sh
# Idempotent deployment script. Run on every code update.
#
# Usage (from anywhere on the EC2 instance):
#   sudo -u marketintel bash /opt/marketintel/repo/deploy/aws/deploy.sh
# =============================================================================
set -euo pipefail

APP_USER="marketintel"
APP_DIR="/opt/marketintel"
REPO_DIR="$APP_DIR/repo"
VENV="$APP_DIR/venv"
BACKEND="$REPO_DIR/backend"

echo "=== [1/7] Pull latest code ==="
cd "$REPO_DIR"
git pull origin main

echo "=== [2/7] Activate venv and update dependencies ==="
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$BACKEND/requirements.txt"

echo "=== [3/7] Run Django system checks ==="
cd "$BACKEND"
"$VENV/bin/python" manage.py check --deploy

echo "=== [4/7] Database migrations ==="
# Migrations are run explicitly — will fail loudly if something is wrong.
# Never runs destructive commands automatically.
"$VENV/bin/python" manage.py migrate --noinput

echo "=== [5/7] Collect static files ==="
"$VENV/bin/python" manage.py collectstatic --noinput

echo "=== [6/7] Restart Gunicorn ==="
systemctl restart marketintel
systemctl is-active marketintel && echo "Gunicorn: RUNNING" || echo "Gunicorn: FAILED — check journalctl -u marketintel"

echo "=== [7/7] Reload Nginx ==="
nginx -t && systemctl reload nginx
echo "Nginx: reloaded"

echo ""
echo "=== Deployment complete ==="
echo "Run diagnostics: cd $BACKEND && $VENV/bin/python manage.py check_mail_configuration"
