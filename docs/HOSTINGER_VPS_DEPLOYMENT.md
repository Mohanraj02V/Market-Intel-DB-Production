# Market Intel DB — Hostinger VPS KVM 2 Production Deployment Guide

This guide covers deploying and operating **Market Intel DB** on **Hostinger VPS KVM 2** (2 vCPU, 8 GB RAM, 100 GB NVMe, Ubuntu 24.04 LTS) with Docker Compose, Nginx + Certbot HTTPS, and keyless **GitHub Actions OIDC → HashiCorp Vault → Short-Lived SSH Certificates**.

---

## 1. Production Architecture

```text
Browser (HTTPS)
   │
   ▼
Cloudflare DNS / Domain
   │  ├── marketinteldbapp.hikasimat.com (React + Vite SPA)
   │  └── marketintel.hikasimat.com      (Django REST API + Webhooks)
   ▼
Hostinger VPS KVM 2 (Ubuntu 24.04 LTS, UFW 22/80/443 only)
   ├── Nginx Reverse Proxy (TLS 1.2/1.3, rate limiting, security headers)
   │     ├── Static SPA: /opt/marketintel/frontend/current
   │     └── Proxy 127.0.0.1:8000 → marketintel-api
   ├── Docker Compose (private bridge: marketintel_internal)
   │     ├── marketintel-api             (Gunicorn 2w×6t, 2 GB cap, 1.2 CPU)
   │     ├── marketintel-campaign-worker (process_campaign_queue, 768 MB cap)
   │     └── marketintel-rag-worker      (run_rag_worker, 1 GB cap)
   ├── Persistent Storage
   │     ├── /opt/marketintel/staticfiles
   │     ├── /opt/marketintel/media
   │     └── /opt/marketintel/backups (encrypted daily pg_dump + media)
   ├── External PostgreSQL (existing managed Amazon RDS / pgvector preserved)
   └── External Integrations (Google, Zoom, Microsoft, Meta, Twitter, WAHA, CBE, AWS Bedrock/S3)
```

---

## 2. One-Time VPS Setup & Hardening

1. Provision a **Hostinger VPS KVM 2** with **Ubuntu 24.04 LTS**.
2. SSH into the server as an initial administrative user and copy the repository scripts (or clone temporarily):
   ```bash
   sudo bash deploy/hostinger/scripts/setup_server.sh
   ```
   This idempotent script installs Docker Engine, Docker Compose, Nginx, UFW, Fail2ban, Certbot, `unattended-upgrades`, `chrony`, creates the isolated `deploy` user, installs root-owned helpers under `/usr/local/sbin/marketintel-*` with narrowly scoped sudoers, creates a 2 GB swapfile, and schedules daily encrypted backups + 10-minute health checks.

3. Configure **Nginx & TLS certificates**:
   ```bash
   sudo cp deploy/hostinger/nginx/marketintel.conf /etc/nginx/sites-available/marketintel
   sudo ln -sfn /etc/nginx/sites-available/marketintel /etc/nginx/sites-enabled/marketintel
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo certbot --nginx -d marketinteldbapp.hikasimat.com -d marketintel.hikasimat.com
   sudo nginx -t && sudo systemctl reload nginx
   ```

4. **Verify key/certificate SSH login first**, then disable password & direct root SSH login:
   ```bash
   sudo CONFIRM_DISABLE_PASSWORD_AUTH=true bash deploy/hostinger/scripts/setup_server.sh
   ```

---

## 3. Environment Variables (`/opt/marketintel/.env`, `chmod 600`)

Never commit real secrets. Populate `/opt/marketintel/.env` on the VPS with:

| Variable | Purpose |
|---|---|
| `DEBUG` | Must be `False` in production |
| `SECRET_KEY` | Strong 50+ char random Django secret key |
| `ALLOWED_HOSTS` | Comma-separated hostnames (`marketintel.hikasimat.com,marketinteldbapp.hikasimat.com`) |
| `CORS_ALLOWED_ORIGINS` | Exact frontend origins (`https://marketinteldbapp.hikasimat.com`) |
| `CSRF_TRUSTED_ORIGINS` | Exact trusted HTTPS origins (`https://marketinteldbapp.hikasimat.com,https://marketintel.hikasimat.com`) |
| `DATABASE_URL` | PostgreSQL connection URI (preserve existing RDS endpoint during cutover) |
| `DB_SSL_REQUIRE` / `DB_SSL_ROOT_CERT` | Enforce TLS to PostgreSQL (`true` + optional RDS CA bundle) |
| `MAIL_CREDENTIALS_ENCRYPTION_KEY` | **CRITICAL:** Copy exact existing Fernet key from AWS SSM — never regenerate without re-encrypting stored OAuth/mail credentials |
| `JWT_ACCESS_TOKEN_MINUTES` | Default `30` (short-lived access token; refresh cookie rotates for 7 days) |
| `SESSION_COOKIE_SAMESITE` / `CSRF_COOKIE_SAMESITE` | `None` when frontend & API use separate subdomains; `Lax` if same origin |
| `FRONTEND_URL` | `https://marketinteldbapp.hikasimat.com` |
| `EMAIL_TRACKING_BASE_URL` | `https://marketintel.hikasimat.com` |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` / `*_REDIRECT_URI` | Google Login, Gmail, and Calendar OAuth |
| `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` / `ZOOM_OAUTH_REDIRECT_URI` / `ZOOM_WEBHOOK_SECRET_TOKEN` | Zoom Meetings & Cloud Recording Transcription |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` / `MICROSOFT_OAUTH_REDIRECT_URI` | Microsoft 365 / Teams OAuth |
| `META_APP_ID` / `META_APP_SECRET` / `META_WEBHOOK_VERIFY_TOKEN` | Instagram / Facebook OAuth & signed webhooks |
| `TWITTER_CLIENT_ID` / `TWITTER_CLIENT_SECRET` | Twitter/X OAuth |
| `WHATSAPP_SERVICE_URL` / `WHATSAPP_SERVICE_API_KEY` / `WHATSAPP_WEBHOOK_SECRET` | WAHA WhatsApp service & signed webhooks |
| `CBE_WEBHOOK_SECRET` / `CBE_TRIGGER_WEBHOOK_SECRET` | Custom Browser Engine HMAC secrets |
| `GEMINI_API_KEY` | Google Gemini AI features |
| `USE_OBJECT_STORAGE` / `AWS_STORAGE_BUCKET_NAME` / `AWS_S3_REGION_NAME` / `AWS_S3_ENDPOINT_URL` | S3 or Cloudflare R2 object storage |
| `RAG_STORAGE_BACKEND` / `RAG_QUEUE_BACKEND` / `BEDROCK_EMBEDDING_MODEL_ID` | RAG storage/queue/embeddings (AWS IAM Roles Anywhere or scoped least-privilege IAM credentials on Hostinger) |
| `BACKUP_ENCRYPTION_PASSPHRASE` / `BACKUP_S3_BUCKET` | Encrypted daily backup passphrase & optional offsite bucket |

---

## 4. GitHub Actions CI/CD Setup (`deploy-hostinger.yml`)

The workflow [`.github/workflows/deploy-hostinger.yml`](../.github/workflows/deploy-hostinger.yml) runs automatically on pull requests to `main` (tests + security scans only) and deploys automatically on pushes to `main` (or manual `workflow_dispatch` on `main`).

### 4.1 Generate a Dedicated `deploy` SSH Key on Hostinger VPS
1. Generate a dedicated `ed25519` keypair strictly for GitHub Actions (never use a root key):
   ```bash
   ssh-keygen -t ed25519 -N "" -C "github-actions-marketintel-deploy" -f /tmp/gha_deploy_key
   sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
   sudo tee -a /home/deploy/.ssh/authorized_keys < /tmp/gha_deploy_key.pub >/dev/null
   sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
   sudo chmod 600 /home/deploy/.ssh/authorized_keys
   cat /tmp/gha_deploy_key          # Copy into GitHub Environment Secret HOSTINGER_SSH_PRIVATE_KEY
   rm -f /tmp/gha_deploy_key /tmp/gha_deploy_key.pub
   ```
2. Export the server's SSH host fingerprint for strict host-key checking:
   ```bash
   ssh-keyscan -p 22 -H <YOUR_HOSTINGER_VPS_IP>
   ```

### 4.2 Configure GitHub Environment (`marketintel-production`)
In GitHub → **Settings → Environments → New environment → `marketintel-production`** (add optional required reviewers for approval before production deploys):

**Environment Secret:**
- `HOSTINGER_SSH_PRIVATE_KEY` — full private key from `/tmp/gha_deploy_key`

**Environment Variables:**
- `HOSTINGER_VPS_HOST` — Hostinger VPS IPv4 or hostname
- `HOSTINGER_VPS_PORT` — `22` (or custom SSH port)
- `HOSTINGER_VPS_USER` — `deploy`
- `HOSTINGER_VPS_KNOWN_HOSTS` — exact output of `ssh-keyscan -H <VPS_HOST>`
- `VITE_API_BASE_URL` — `https://marketintel.hikasimat.com/api`
- `API_HEALTH_URL` — `https://marketintel.hikasimat.com/api/health/`
- `FRONTEND_URL` — `https://marketinteldbapp.hikasimat.com/`

*(Optional enterprise upgrade: [`deploy/hostinger/vault/setup_vault_oidc.sh`](../deploy/hostinger/vault/setup_vault_oidc.sh) is retained if you later adopt HashiCorp Vault short-lived OIDC SSH certificates.)*

---

## 5. Preserving AWS Application Integrations (Bedrock / S3 / SQS)

Hostinger VPS does not have an EC2 instance metadata role. If Amazon Bedrock, S3, or SQS remain enabled:
- **Preferred:** Use **AWS IAM Roles Anywhere** (`aws_signing_helper`) on the VPS to obtain short-lived temporary AWS credentials automatically.
- **Alternative:** Provision a dedicated least-privilege IAM user restricted strictly to the specific S3 bucket prefix, Bedrock embedding model ARN, and SQS queue ARN, stored in `/opt/marketintel/.env` (`chmod 600`) with scheduled 90-day key rotation.

---

## 6. Operations Commands

- **Manual deploy of staged SHA:** `sudo /usr/local/sbin/marketintel-deploy <COMMIT_SHA>`
- **Immediate rollback (data-safe):** `sudo /usr/local/sbin/marketintel-rollback`
- **Health check:** `sudo /usr/local/sbin/marketintel-health`
- **Manual encrypted backup:** `sudo /usr/local/sbin/marketintel-backup`
- **Restore from verified backup:** `sudo /usr/local/sbin/marketintel-restore /opt/marketintel/backups/<TIMESTAMP>`
- **Container logs:** `docker logs --tail 200 -f marketintel-api` (or `marketintel-campaign-worker`, `marketintel-rag-worker`)
- **Stage C Cutover Policy:** Verify all smoke tests against Hostinger via `/etc/hosts` before updating DNS. Keep the legacy AWS EC2 environment (`deploy/aws/`) intact for **7–14 days** after cutover before retiring it.
