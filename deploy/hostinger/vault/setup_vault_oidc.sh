#!/usr/bin/env bash
# =============================================================================
# HashiCorp Vault OIDC -> Short-Lived SSH Certificate Setup
# Run on an independently hosted HashiCorp Vault instance (NOT on the target VPS).
#
# Prerequisites:
#   export VAULT_ADDR="https://vault.example.com"
#   export VAULT_TOKEN="<admin-bootstrap-token>"
#   export GITHUB_OWNER="<your-github-org-or-user>"
#   export GITHUB_REPO="<your-repo-name>"
#   export GITHUB_ENV="marketintel-production"
# =============================================================================
set -euo pipefail

: "${VAULT_ADDR:?Set VAULT_ADDR}"
: "${GITHUB_OWNER:?Set GITHUB_OWNER}"
: "${GITHUB_REPO:?Set GITHUB_REPO}"
GITHUB_ENV="${GITHUB_ENV:-marketintel-production}"

echo "=== [1/4] Enabling Vault SSH Client Signer engine ==="
vault secrets enable -path=ssh-client-signer ssh || true
vault write ssh-client-signer/config/ca generate_signing_key=true

echo "=== [2/4] Creating least-privilege 5-minute SSH cert role for 'deploy' ==="
vault write ssh-client-signer/roles/marketintel-deploy - <<'EOF'
{
  "algorithm_signer": "rsa-sha2-512",
  "allow_user_certificates": true,
  "allowed_users": "deploy",
  "default_user": "deploy",
  "default_extensions": {
    "permit-pty": ""
  },
  "allowed_extensions": "permit-pty",
  "key_type": "ca",
  "ttl": "5m",
  "max_ttl": "10m"
}
EOF

echo "=== [3/4] Writing minimal Vault policy (SSH sign only) ==="
vault policy write marketintel-github-deploy - <<'EOF'
path "ssh-client-signer/sign/marketintel-deploy" {
  capabilities = ["create", "update"]
}
EOF

echo "=== [4/4] Configuring GitHub Actions OIDC JWT Auth Role ==="
vault auth enable jwt || true
vault write auth/jwt/config \
  oidc_discovery_url="https://token.actions.githubusercontent.com" \
  bound_issuer="https://token.actions.githubusercontent.com"

# Uses repository + repository_owner + environment claims (works regardless of
# GitHub's customizable/immutable sub claim format).
vault write auth/jwt/role/marketintel-production-deploy - <<EOF
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["https://vault.marketintel"],
  "bound_claims_type": "glob",
  "bound_claims": {
    "repository_owner": "${GITHUB_OWNER}",
    "repository": "${GITHUB_OWNER}/${GITHUB_REPO}",
    "environment": "${GITHUB_ENV}",
    "ref": "refs/heads/main"
  },
  "token_policies": ["marketintel-github-deploy"],
  "token_ttl": "5m",
  "token_max_ttl": "10m"
}
EOF

echo "=== Export the SSH CA public key below and install it on Hostinger VPS at /etc/ssh/vault_user_ca.pub ==="
vault read -field=public_key ssh-client-signer/config/ca
