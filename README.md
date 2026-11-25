# MarketIntel DB

A full-stack B2B CRM, outreach automation, meeting transcription, WhatsApp/RAG knowledge base, and digital marketing intelligence platform.

## Architecture (Hostinger VPS KVM 2)

```text
Browser (HTTPS)
  └─► Cloudflare DNS / Domain
        └─► Hostinger VPS KVM 2 (Ubuntu 24.04 LTS + Nginx + Certbot TLS)
              ├── Static React 19 + Vite 8 SPA (marketinteldbapp.hikasimat.com)
              ├── Django 6.1 REST API Container (127.0.0.1:8000, Gunicorn)
              ├── Email Campaign Worker Container (process_campaign_queue, 90s pacing)
              ├── RAG Ingestion Worker Container (run_rag_worker)
              ├── Managed PostgreSQL (pgvector)
              └── External Integrations (Google, Zoom, Microsoft, Meta, Twitter, WAHA, CBE, AWS Bedrock/S3)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Redux Toolkit, Tailwind CSS v4, Axios |
| Backend | Python 3.14, Django 6.1.1, Django REST Framework, Gunicorn |
| Auth | HttpOnly Cookie JWT (SimpleJWT + rotation + blacklist) + CSRF enforcement |
| Database | PostgreSQL with `pgvector` |
| Production Hosting | Hostinger VPS KVM 2 (Docker Compose + Nginx + Certbot) |
| CI/CD | GitHub Actions OIDC → HashiCorp Vault → Short-Lived SSH Certificates |

## Project Structure

```text
Market-Intel-DB/
├── backend/
│   ├── accounts/          # Auth, JWT/CSRF, UserProfile, OAuth (Google/Zoom/Microsoft), Templates, Calendar, CBE
│   ├── companies/         # Multi-company organization model
│   ├── prospects/         # Prospects, Outreach Pipeline, Bulk Campaigns (90s), PreTasks, Meetings
│   ├── market_events/     # Trade shows & market events
│   ├── whatsapp/          # WAHA WhatsApp sessions, messaging, media, webhooks, SSRF protection
│   ├── whatsapp_ai/       # AI WhatsApp auto-reply engine
│   ├── rag/               # Knowledge Base (pgvector, Amazon Bedrock / Gemini embeddings, S3/local)
│   ├── email_ai/          # AI email drafting & manager summaries
│   ├── digital_marketing/ # Instagram, Facebook, Twitter/X, CMS & Search Console
│   ├── transcriptions/    # Normalized Google Meet (CBE) & Zoom Cloud Recording transcripts
│   ├── utils/             # Fernet encryption & shared IPv4/IPv6 SSRF protection
│   └── config/            # Settings, URLs, WSGI, CI test settings
├── frontend/              # React 19 + Vite 8 SPA
├── deploy/
│   ├── hostinger/         # Production Hostinger KVM 2 Dockerfile, Compose, Nginx, scripts, Vault OIDC
│   └── aws/               # Legacy AWS deployment files (retained for rollback window)
└── docs/
    ├── SECURITY_AND_INFRASTRUCTURE_AUDIT.md
    └── HOSTINGER_VPS_DEPLOYMENT.md
```

## Local Development

### Prerequisites
- Python 3.14 (matches `backend/.python-version` and Docker runtime)
- Node.js 22+
- PostgreSQL 15+ (with `pgvector`)

### Backend

```bash
cd backend
python -m venv env
source env/bin/activate        # Windows: env\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # configure local values
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm ci
cp .env.example .env.local     # set VITE_API_BASE_URL=/api for Vite proxy
npm run dev
```

## Production Deployment (Hostinger VPS KVM 2)

See [`docs/HOSTINGER_VPS_DEPLOYMENT.md`](docs/HOSTINGER_VPS_DEPLOYMENT.md) for full server hardening, Vault OIDC SSH certificate setup, environment variable reference, automated encrypted backups, and rollback instructions.

- Active GitHub Actions workflow: [`.github/workflows/deploy-hostinger.yml`](.github/workflows/deploy-hostinger.yml)
- Security & infrastructure audit: [`docs/SECURITY_AND_INFRASTRUCTURE_AUDIT.md`](docs/SECURITY_AND_INFRASTRUCTURE_AUDIT.md)
- Legacy AWS deployment files remain in `deploy/aws/` for rollback during cutover verification.

## User Roles

| Role | Access |
|------|--------|
| **PRE** (Prospect Research Engineer) | Dashboard, Tasks, Prospects, Outreach, Email Campaigns, Calendar, Transcription, Inbox, WhatsApp, Government Entities, Key People, Market Events, Settings |
| **MANAGER** | Manager Dashboard, Daily Audit, Company-scoped Team/Transcriptions/Tasks/Email Activity & Read-only CRM visibility |
| **DM** (Digital Marketing) | Digital Marketing Workspace (Instagram, Facebook, Twitter/X, Ads Insights, Social Messages, CMS) |
| **Superuser** | Full administrative access & User Management |

## Running Tests

### Backend
```bash
cd backend
python manage.py check --settings=config.settings_test
python manage.py test accounts.test_security_hardening transcriptions.tests --settings=config.settings_test --verbosity=2
```

### Frontend
```bash
cd frontend
npm run lint
npm test
npm run build
```
