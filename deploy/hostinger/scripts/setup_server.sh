#!/usr/bin/env bash
# =============================================================================
# Hostinger VPS KVM 2 — Idempotent Production Server Hardening & Setup Script
# Target OS: Ubuntu 24.04 LTS (2 vCPU / 8 GB RAM / 100 GB NVMe)
# Usage: sudo bash deploy/hostinger/scripts/setup_server.sh
# Optional env:
#   ADMIN_SSH_ALLOW_CIDR="x.x.x.x/32"
#   VAULT_SSH_CA_PUB_FILE="/path/to/vault_user_ca.pub"
#   CONFIRM_DISABLE_PASSWORD_AUTH="true" (only after verifying key/cert SSH!)
# =============================================================================
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run as root (sudo bash $0)." >&2
  exit 1
fi

ARCH="$(dpkg --print-architecture)"
echo "=== [1/9] Detected architecture: ${ARCH} ($(uname -a)) ==="

echo "=== [2/9] Installing base packages, Nginx, UFW, Fail2ban, Certbot, monitoring ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg lsb-release jq git ufw fail2ban \
  nginx certbot python3-certbot-nginx \
  unattended-upgrades apt-listchanges chrony logrotate \
  postgresql-client openssl htop ncdu

systemctl enable --now chrony
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "=== [3/9] Installing Docker Engine + Docker Compose plugin ==="
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

echo "=== [4/9] Configuring 2 GB swap safety net (if not already present) ==="
if ! swapon --show | grep -q '/swapfile'; then
  if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "=== [5/9] Creating isolated deployment user & application directory layout ==="
if ! id -u deploy >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash deploy
fi

mkdir -p \
  /opt/marketintel/releases \
  /opt/marketintel/incoming \
  /opt/marketintel/staticfiles \
  /opt/marketintel/media \
  /opt/marketintel/frontend \
  /opt/marketintel/backups \
  /opt/marketintel/deploy

# Container runtime user UID/GID is 10001
chown -R 10001:10001 /opt/marketintel/staticfiles /opt/marketintel/media
chown -R deploy:deploy /opt/marketintel/incoming
chown root:root /opt/marketintel /opt/marketintel/releases /opt/marketintel/backups /opt/marketintel/deploy
chmod 755 /opt/marketintel /opt/marketintel/frontend /opt/marketintel/releases
chmod 750 /opt/marketintel/incoming /opt/marketintel/backups

echo "=== [6/9] Installing root-owned deployment helpers & scoped sudoers ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -m 0750 -o root -g root "${SCRIPT_DIR}/deploy.sh" /usr/local/sbin/marketintel-deploy
install -m 0750 -o root -g root "${SCRIPT_DIR}/rollback.sh" /usr/local/sbin/marketintel-rollback
install -m 0755 -o root -g root "${SCRIPT_DIR}/health_check.sh" /usr/local/sbin/marketintel-health
install -m 0750 -o root -g root "${SCRIPT_DIR}/backup.sh" /usr/local/sbin/marketintel-backup
install -m 0750 -o root -g root "${SCRIPT_DIR}/restore.sh" /usr/local/sbin/marketintel-restore

install -m 0644 -o root -g root "${SCRIPT_DIR}/../docker-compose.production.yml" /opt/marketintel/deploy/docker-compose.production.yml

cat > /etc/sudoers.d/marketintel-deploy <<'EOF'
# Strictly scoped deployment privileges for OIDC certificate-authenticated deploy user.
# No unrestricted root shell and no direct Docker socket access.
Defaults:deploy !requiretty
deploy ALL=(root) NOPASSWD: /usr/local/sbin/marketintel-deploy [0-9a-fA-F]*, /usr/local/sbin/marketintel-rollback, /usr/local/sbin/marketintel-health
EOF
chmod 0440 /etc/sudoers.d/marketintel-deploy
visudo -cf /etc/sudoers.d/marketintel-deploy

echo "=== [7/9] Hardening OpenSSH (Vault SSH User CA + restricted deploy principal) ==="
if [[ -n "${VAULT_SSH_CA_PUB_FILE:-}" && -f "${VAULT_SSH_CA_PUB_FILE}" ]]; then
  install -m 0644 -o root -g root "${VAULT_SSH_CA_PUB_FILE}" /etc/ssh/vault_user_ca.pub
fi

cat > /etc/ssh/sshd_config.d/99-marketintel-hardening.conf <<EOF
PermitEmptyPasswords no
KbdInteractiveAuthentication no
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
MaxAuthTries 4
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
$( [[ -f /etc/ssh/vault_user_ca.pub ]] && echo "TrustedUserCAKeys /etc/ssh/vault_user_ca.pub" )
$( [[ "${CONFIRM_DISABLE_PASSWORD_AUTH:-false}" == "true" ]] && echo "PasswordAuthentication no" && echo "PermitRootLogin no" )

Match User deploy
    X11Forwarding no
    AllowAgentForwarding no
    AllowTcpForwarding no
    PermitTunnel no
EOF

sshd -t
systemctl reload ssh || systemctl reload sshd

echo "=== [8/9] Configuring UFW firewall and Fail2ban ==="
ufw default deny incoming
ufw default allow outgoing
if [[ -n "${ADMIN_SSH_ALLOW_CIDR:-}" ]]; then
  ufw allow from "${ADMIN_SSH_ALLOW_CIDR}" to any port 22 proto tcp
else
  ufw allow 22/tcp
fi
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat > /etc/fail2ban/jail.d/marketintel.conf <<'EOF'
[sshd]
enabled = true
port = ssh
maxretry = 5
bantime = 1h
findtime = 10m

[nginx-http-auth]
enabled = true
EOF
systemctl enable --now fail2ban

echo "=== [9/9] Configuring automated daily backup & certbot renewal ==="
cat > /etc/cron.d/marketintel-ops <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
# Daily encrypted DB + media backup at 02:30 UTC
30 2 * * * root /usr/local/sbin/marketintel-backup >> /var/log/marketintel-backup.log 2>&1
# Periodic health check every 10 minutes
*/10 * * * * root /usr/local/sbin/marketintel-health --quiet >> /var/log/marketintel-health.log 2>&1
EOF
chmod 0644 /etc/cron.d/marketintel-ops

cat > /etc/logrotate.d/marketintel <<'EOF'
/var/log/marketintel-*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    create 0640 root adm
}
EOF

echo "Hostinger VPS KVM 2 hardening complete."
echo "Next steps:"
echo "  1. Place production environment file at /opt/marketintel/.env (chmod 600)."
echo "  2. Install Vault SSH CA public key at /etc/ssh/vault_user_ca.pub and reload sshd."
echo "  3. Copy deploy/hostinger/nginx/marketintel.conf to /etc/nginx/sites-available/marketintel and issue TLS certs with certbot."
echo "  4. Once SSH key/cert login is verified, re-run with CONFIRM_DISABLE_PASSWORD_AUTH=true."
