# Market Intel DB — Security & Infrastructure Audit Report

**Audit Date:** 2026-11-25  
**Scope:** Full-stack audit of Django 6.1.1 backend, React 19 / Vite 8 frontend, Docker/Nginx/GitHub Actions deployment, dependencies, multi-tenant isolation, webhooks/OAuth, and Hostinger VPS KVM 2 migration readiness.  
**Policy:** Every finding below is verified directly against source files and line numbers. No secret values are included.

---

## 1. Existing Architecture Summary

### Backend (`backend/`)
- **Framework:** Python 3.14, Django 6.1.1, Django REST Framework, SimpleJWT (`rest_framework_simplejwt` + `token_blacklist`), Gunicorn (`gthread`, 2 workers x 6 threads).
- **10 Custom Django Apps:** `accounts`, `companies`, `prospects`, `market_events`, `whatsapp`, `whatsapp_ai`, `rag`, `email_ai`, `digital_marketing`, `transcriptions`.
- **Database:** Production uses **Amazon RDS PostgreSQL** (`pgvector`); local development uses Supabase PostgreSQL or SQLite test settings.
- **Storage & AWS Integrations:**
  - `django-storages` S3 backend (`USE_OBJECT_STORAGE=true`, supports `AWS_S3_ENDPOINT_URL`).
  - `rag/services/storage_service.py`: native `boto3` S3 client (`RAG_STORAGE_BACKEND=s3`, defaults to local `MEDIA_ROOT/rag_private`).
  - `rag/services/embedding_service.py`: Amazon Bedrock (`amazon.titan-embed-text-v2:0`) with Gemini fallback.
  - `rag/tasks.py` & `ingestion_worker.py`: optional SQS (`RAG_QUEUE_BACKEND=sqs`, defaults to local DB `IngestionJob`).
  - `rag/services/document_parser_service.py`: optional Amazon Textract OCR (`RAG_OCR_BACKEND=textract`).
- **External Integrations:** Google Login/Gmail/Calendar/Meet OAuth, Zoom OAuth + Cloud Recording Webhooks, Microsoft 365/Teams OAuth, Meta/Instagram/Facebook OAuth + Webhooks, Twitter/X OAuth, WAHA WhatsApp service + Webhooks, Custom Browser Engine (CBE) meeting webhooks, Google Gemini.

### Frontend (`frontend/`)
- **Framework:** React 19.3, Vite 8.3.5, Redux Toolkit 2.12, Tailwind CSS 4.3.3, Axios 1.20, React Router 7.18.
- **Current Hosting:** AWS Amplify at `https://marketinteldbapp.hikasimat.com`, talking to API at `https://marketintel.hikasimat.com/api`.

### Current Deployment (AWS EC2)
- `.github/workflows/deploy-production.yml` builds `deploy/aws/backend.Dockerfile`, pushes to Amazon ECR, and runs an SSM shell script on EC2 starting `marketintel-api` and `marketintel-rag-worker`.
- Three divergent deployment configurations exist (`deploy-production.yml`, `deploy/aws/docker-compose.production.yml`, and bare-metal systemd scripts `setup_ec2.sh`/`deploy.sh`/`*.service`).

---

## 2. Confirmed Security Vulnerabilities

### Critical Severity

| ID | Issue | Affected File(s) | Recommended Fix |
|---|---|---|---|
| **C-1** | **Arbitrary Local File Read / Exfiltration via Email CID Inliner**: `<img src="/media/...">` extracts `rel_path` via `urllib.parse.unquote` and joins `MEDIA_ROOT` without `os.path.realpath` containment or blocking `rag_private/`. Allows `<img src="/media/../../.env">` or `<img src="/media/rag_private/...">`. | `backend/accounts/template_utils.py:437-465` | Enforce `Path.resolve()` containment inside `MEDIA_ROOT`, reject `..`/absolute paths, and explicitly block `rag_private/` and non-image extensions. |
| **C-2** | **No CSRF Enforcement on Cookie-Authenticated JWT Requests**: `CookieJWTAuthentication` authenticates via `access_token` cookie (`SameSite=None` in prod) without calling CSRF validation; DRF wraps views in `csrf_exempt`. | `backend/accounts/authentication.py:3-25`, `frontend/src/services/api.js:29-36` | Enforce DRF `CSRFCheck` inside `CookieJWTAuthentication` whenever authentication succeeds via cookie on unsafe HTTP methods (preserving Bearer-header auth without CSRF); add `GET /api/auth/csrf/` + `X-CSRFToken` forwarding in Axios. |
| **C-3** | **Unauthenticated Meta Webhook (`X-Hub-Signature-256` Missing)**: `POST` webhook accepts unsigned payloads (`hmac`/`hashlib` imported but never called), allowing arbitrary injection of `ConversationThread`/`DirectMessage` rows; `GET` falls back to hardcoded verify token. | `backend/digital_marketing/views.py:1293-1395` | Enforce fail-closed `X-Hub-Signature-256` HMAC-SHA256 verification using `META_APP_SECRET` and remove hardcoded verify-token default in production. |
| **C-4** | **Broken Object-Level Authorization / IDOR in `OutreachEmailViewSet`, `LQPipelineViewSet.get_object`, `PreTaskViewSet`, `CallbackReminderViewSet`, `MeetingViewSet`, `EmailVerificationViewSet`, `ProspectViewSet.merge`, and `email_ai/views.py`**: Missing role/user/company scoping or unfiltered fallback queries expose cross-user/cross-company CRM data and allow unauthorized mutations (including by `DM` users). | `backend/prospects/views.py:462-484,552-560,757-821,1578-1650,2945-3006`; `backend/prospects/verification_views.py:11-161`; `backend/email_ai/views.py:38-90` | Restrict `DM` from CRM ViewSets, scope `get_queryset()` by user/company, remove unfiltered `LQPipelineViewSet.get_object` fallback, validate prospect ownership on merge/create/preview/AI generation, and scope `EmailVerificationViewSet`. |
| **C-5** | **Plaintext Meta `page_access_token` Exposed in API Response**: `InstagramCallbackView` stores `page_access_token` inside `conn.metadata` and `SocialAccountConnectionSerializer` serializes `metadata` directly. | `backend/digital_marketing/views.py:204-212`, `backend/digital_marketing/serializers.py:28-49` | Never persist raw tokens in `metadata` (or sanitize `metadata` in serializer to strip token/secret keys). |
| **C-6** | **CI Pipeline Attempts IAM Self-Escalation**: GitHub Actions runs `aws iam put-role-policy --policy-name ECRBatchGetImagePolicy --policy-document ... Resource: "*"`. | `.github/workflows/deploy-production.yml:114-117` | Remove completely and replace with OIDC-to-Vault short-lived Hostinger SSH certificate workflow. |

### High Severity

| ID | Issue | Affected File(s) | Recommended Fix |
|---|---|---|---|
| **H-1** | **Unprotected SSRF in Digital Marketing Search Console Endpoints**: `SearchConsoleIndexingAPIView` and `SearchConsoleDomainVerifyAPIView` call `urllib.request.urlopen()` on arbitrary user URLs/domains without IP/DNS/redirect filtering. | `backend/digital_marketing/cms_views.py:1207-1216,1338-1380` | Apply shared safe-URL SSRF validator (IPv4+IPv6 DNS resolution, private/loopback/link-local/metadata blocking, safe redirect handler) and never auto-mark domains verified on failed check. |
| **H-2** | **Incomplete WhatsApp SSRF Guard + API Key Leakage**: `_is_ssrf_safe_url` uses IPv4-only `gethostbyname`, omits `0.0.0.0/8`, CGNAT, IPv6 private/mapped/link-local ranges, allows redirect bypasses, and sends `X-Api-Key` to non-WAHA external hosts. | `backend/whatsapp/webhooks.py:440-474,504-538` | Create `backend/utils/url_security.py` with `socket.getaddrinfo` (IPv4+IPv6), full non-global IP checks, no-unsafe-redirect opener, and attach `X-Api-Key` ONLY when host matches configured WAHA host. |
| **H-3** | **XSS & Broken Sandbox in Frontend HTML/Signature Editors**: Unsanitized `dangerouslySetInnerHTML`, `safeUrl()` bypass when string contains `{{...}}` (e.g. `javascript:alert(1)//{{x}}`), `sandbox="allow-same-origin allow-scripts"` in `SimpleEmailEditor`, and unsandboxed `<iframe srcDoc>` in `TemplatePicker`. | `frontend/src/components/settings/CustomSignatureEditor.jsx:726`; `SignatureBuilderModal.jsx:26-32,1135`; `emailEditor/SimpleEmailEditor.jsx:1627,2265,2371,2948`; `emailEditor/emailHtmlGenerator.js:110-119`; `components/lq/TemplatePicker.jsx:471` | Add shared frontend HTML sanitizer (`utils/htmlSanitizer.js`) stripping `<script>`, event handlers, `javascript:`/`vbscript:`/`data:text/html` URIs; fix `safeUrl()` to allow `{{...}}` ONLY as full placeholder `^\{\{[a-zA-Z0-9_]+\}\}$`; fix iframe sandboxes. |
| **H-4** | **Stored SVG / Arbitrary File Upload XSS**: `template_views.py` allows `image/svg+xml` and preserves arbitrary extensions; `WhatsAppProfilePicView` serves `data:image/svg+xml`; `WhatsAppCallRecordingStreamView` serves arbitrary client `content_type` inline. | `backend/accounts/template_views.py:62-94`; `backend/whatsapp/views.py:2107-2114,2684-2687,3577-3678` | Block SVG uploads (`image/svg+xml`), enforce strict extension allowlists, validate audio/image types, and set `X-Content-Type-Options: nosniff` / safe MIME types on media streaming. |
| **H-5** | **JWT `accessToken` Persisted in `sessionStorage` + Broken Server Logout**: `store.js` dumps entire Redux state (including `accessToken`) to `sessionStorage`; `Layout.jsx` never calls `POST /auth/logout/` because `auth.refreshToken` is undefined, and never deletes `api.defaults.headers.common['Authorization']`. | `frontend/src/app/store.js:43-71`; `frontend/src/components/layout/Layout.jsx:58-69`; `frontend/src/pages/LoginPage.jsx:99,149` | Exclude `auth` from `sessionStorage` persistence in `store.js`; always call `POST /auth/logout/` on logout and idle timeout; clear `Authorization` header cleanly; allow `LogoutView` to accept cookie refresh token even if access token is expired. |
| **H-6** | **Google Login OAuth Login-CSRF & Replay**: `verify_state` skips cookie comparison when cookie is absent and does not consume a single-use nonce. | `backend/accounts/oauth_services.py:70-86` | Consume single-use nonce via `cache.add` and require matching state cookie when issued. |
| **H-7** | **Permissive Production `ALLOWED_HOSTS`, `CORS`, `CSRF` & `load_dotenv(override=True)`**: `settings.py` overwrites container env vars with `.env`, hardcodes stale `trycloudflare.com` host, wildcard `*.hikasimat.com` CORS regex with `CORS_ALLOW_CREDENTIALS=True`, and `localhost`/`127.0.0.1` in production CORS/CSRF. | `backend/config/settings.py:7,19-33,189-228` | Use `load_dotenv(override=False)`, remove stale `trycloudflare.com`, remove wildcard CORS regex, keep localhost origins strictly under `if DEBUG:`, enforce explicit production allowlists, and add `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`. |
| **H-8** | **24-Hour Non-Revocable Access Token**: Access token remains valid 24h after logout/compromise. | `backend/config/settings.py:178` | Shorten default `ACCESS_TOKEN_LIFETIME` to 30 minutes (configurable via env) since Axios automatically refreshes via HttpOnly refresh cookie (`ROTATE_REFRESH_TOKENS=True`). |
| **H-9** | **Destructive `docker volume prune -f` & Missing Campaign Worker in Prod Deploy**: Every deploy prunes volumes and deletes rollback images before verifying startup, and omits `marketintel-campaign-worker`. | `.github/workflows/deploy-production.yml:201-205,241-256` | Replace with Compose-based Hostinger deployment running API + Campaign Worker + RAG Worker, zero `volume prune`, health-check gating, and release retention for rollback. |

### Medium Severity

| ID | Issue | Affected File(s) | Recommended Fix |
|---|---|---|---|
| **M-1** | **Unauthenticated DB Write Flooding / Amplification**: `GoogleAnalyticsCollectAPIView` (`AllowAny`) and `EmailVerificationViewSet.bulk_verify` lack throttling/size caps. | `backend/digital_marketing/cms_views.py:823-914`; `backend/prospects/verification_views.py:38-62` | Add dedicated DRF throttles and batch size limit (e.g., max 100 emails per `bulk_verify`). |
| **M-2** | **`GoogleCalendarSyncRecordingView` & `MeetingAutomationPollView` Scope Gaps**: `google_calendar_owner_id not in (None, request.user.id)` fails open when owner is `None`; `MeetingAutomationPollView` triggers global cross-user processing for any PRE user. | `backend/accounts/calendar_views.py:716-740,853-862` | Check owner strictly and restrict `MeetingAutomationPollView` to Manager/Superuser. |
| **M-3** | **`UserViewSet` Cross-Company Manager Scope**: Managers can view/edit users across all companies. | `backend/accounts/views.py:555-640` | Scope Manager queryset in `UserViewSet` to `profile__company_id=manager_company_id` when manager has a company assigned. |
| **M-4** | **Open Redirects & Unvalidated OAuth `returnUrl`**: `EmailLinkClickTrackingView` redirects to arbitrary `?url=`, `WhatsAppProfilePicView` redirects to unvalidated `custom_avatar_url`, and frontend OAuth callback pages navigate to unvalidated `localStorage` return URLs. | `backend/prospects/views.py:2314-2346`; `frontend/src/pages/*CallbackPage.jsx` | Restrict frontend `returnUrl` to safe relative paths (`/^\/(?!\/)/`); validate/restrict `custom_avatar_url` and `EmailLinkClickTrackingView` URL scheme/host safety. |
| **M-5** | **CBE Nonce Replay & WhatsApp Timestamp Optionality**: CBE checks nonce length without deduplicating it; WhatsApp allows omitting timestamp header. | `backend/accounts/meeting_automation_service.py:162-204`; `backend/whatsapp/webhooks.py:647-695` | Cache/deduplicate CBE nonce for 300s; enforce timestamp skew when present. |
| **M-6** | **Meta/Twitter OAuth Redirect Fallback to Raw `Origin`/`Referer` + Missing Nonce Consumption**. | `backend/digital_marketing/services/meta_service.py:94-113`; `twitter_service.py:91-104` | Validate fallback redirect origin against `FRONTEND_URL` / `CORS_ALLOWED_ORIGINS` and consume state nonce via `cache.add`. |
| **M-7** | **Broad `test_*.py` Rule in `.gitignore` & `.dockerignore` Missing `backend/env`**: 16 active backend test files are untracked/ignored by Git; local virtualenvs and 230 MB REA dump are not excluded from Docker build context. | `.gitignore:158`; `backend/.gitignore:158`; `.dockerignore` | Remove `test_*.py` from `.gitignore`, remove redundant `backend/.gitignore`, and harden `.dockerignore`. |
| **M-8** | **`pre_dashboard_stats` Missing Explicit `@permission_classes([IsAuthenticated])`**. | `backend/prospects/views.py:2349` | Add explicit `@permission_classes([IsAuthenticated])` and rely on DRF global default `IsAuthenticated`. |

### Low Severity

| ID | Issue | Affected File(s) | Recommended Fix |
|---|---|---|---|
| **L-1** | **`Content-Disposition` filename not sanitized** in attachment library download. | `backend/accounts/attachment_library_views.py:91` | Strip control chars/quotes/path separators from filename. |
| **L-2** | **Unpinned GitHub Actions & floating `python:3.14-slim` tag**. | `.github/workflows/deploy-production.yml`; `deploy/aws/backend.Dockerfile` | Pin third-party GitHub Actions to full 40-char commit SHAs in `deploy-hostinger.yml`. |
| **L-3** | **Broken `/health` check in CI** (no `/health` route in Django, `|| true` masks failures). | `.github/workflows/deploy-production.yml:266`; `backend/config/urls.py` | Add lightweight, secret-free `/api/health/` endpoint verifying DB connectivity (without leaking config/hostnames) + Docker `HEALTHCHECK`. |
| **L-4** | **`target="_blank"` inconsistency** (`rel="noreferrer"` vs `rel="noopener noreferrer"`) and `InboxPage.jsx:949` `data:` fallback. | Multiple frontend pages | Standardize `rel="noopener noreferrer"` and avoid unsafe `data:` HTML/SVG `window.open`. |

---

## 3. Dependencies & Codebase Cleanup Findings

- **Backend (`backend/requirements.txt` vs root `requirements.txt`):**
  - Root `requirements.txt` is stale (missing `pgvector`, `pypdf`, `python-docx`, `lxml`). Make `backend/requirements.txt` the single authoritative manifest (remove stale root duplicate).
  - Duplicate PostgreSQL drivers: both `psycopg`/`psycopg-binary` (v3) and `psycopg2-binary` (v2) are listed; Django 6.1 uses `psycopg` v3 cleanly.
  - `Pillow>=10.4.0` is unpinned and completely unused in backend code (0 `PIL` imports, 0 `ImageField`s).
- **Frontend (`frontend/package.json`):**
  - Missing `"test"` script for existing `.test.mjs` files.
  - Unused starter files: `frontend/src/App.css`, `frontend/public/icons.svg`, unused `LqPipelinePage` lazy declaration in `AppRouter.jsx`, dead `handleSimulateOpen` handlers.
- **Stray/Dangerous Backend Files:**
  - `backend/cleanup_whatsapp_data.py` — dangerous ad-hoc script that hard-deletes all WhatsApp data; superseded by `python manage.py purge_whatsapp_chats`. Safe to remove.
  - `backend/.gitignore` — redundant stale copy of root `.gitignore` duplicating `test_*.py`. Safe to remove.
- **Backend Dead Code:**
  - `prospects/views.py:679`: unreachable `filter_backends` indented inside `partial_update` after `return`.
- **Frontend Performance & UX:**
  - Axios retries `AbortController`-cancelled (`ERR_CANCELED`) GET requests.
  - `CallContext` polls `/whatsapp/calls/status/` for `MANAGER`/`DM` roles and duplicates ringtone playback with `NotificationCenter`.
  - Multiple polling intervals run even when `document.hidden` is true or modals are closed.
  - `TemplatePicker` listener leak; unrevoked `URL.createObjectURL` in `WhatsappPage` and `ImportPreviewPage`; unthrottled `mousemove` in `Layout.jsx`.
  - Non-functional `<Mic>`, `<Plus>`, `<MoreVertical>` sidebar buttons; `Apps` sidebar section shown to `DM` users; missing mobile sidebar drawer; global `zoom: 0.9`; missing ARIA attributes on modals and icon buttons; developer jargon (`META_REDIRECT_URI=...`, `TWITTER_REDIRECT_URI=...`, hardcoded internal emails/domains).

---

## 4. Migration Risks & Preservation Checklist

1. **`MAIL_CREDENTIALS_ENCRYPTION_KEY` MUST BE PRESERVED**: Replacing it renders all encrypted Gmail/Calendar/Zoom/Microsoft/Meta/Twitter credentials unrecoverable.
2. **Production Database Policy**: Keep the existing production PostgreSQL database (Amazon RDS / verified `DATABASE_URL`) connected during Stage B cutover; provide a verified backup/restore/migration script if migrating off RDS later.
3. **AWS Application Dependencies to Preserve**: Amazon Bedrock embeddings, S3 storage (add optional `AWS_S3_ENDPOINT_URL` support to `rag/services/storage_service.py` as well so both AWS S3 and R2 work seamlessly), optional SQS/Textract — document AWS IAM Roles Anywhere / scoped IAM credentials for Hostinger VPS since EC2 instance metadata roles do not exist on Hostinger.
4. **Preserve 100% of Business Functionality**: All 10 Django apps, all migrations, all 384+ backend tests, all frontend pages/routes/roles (`PRE`, `LQ`, `MANAGER`, `DM`, Superuser), 90-second campaign pacing, WAHA WhatsApp integration, CBE + Zoom transcription workflows, and RAG pipelines.
